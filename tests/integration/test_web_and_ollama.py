"""Integration tests for the WebCheck-AI Flask workflow and local Ollama verification."""

from __future__ import annotations

import time

import pytest

from qa_agent.config import OutputFormat, TestConfig
from qa_agent.llm_client import LLMProvider, get_ollama_status
from qa_agent.web import server as srv


@pytest.mark.integration
class TestWebWorkflowIntegration:
    """End-to-end scan submission through the Flask API against a local fixture site."""

    def test_web_scan_end_to_end_creates_verified_session(self, tmp_path, monkeypatch):
        import threading
        from http.server import HTTPServer, SimpleHTTPRequestHandler

        from tests.integration.test_smoke import FIXTURES_DIR

        class Handler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(FIXTURES_DIR), **kwargs)

            def log_message(self, format, *args):  # noqa: A002
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        monkeypatch.setattr(srv, "OUTPUT_DIR", tmp_path)
        srv._invalidate_session_cache()
        srv.app.config["TESTING"] = True

        try:
            with srv.app.test_client() as client:
                resp = client.post(
                    "/api/run",
                    json={
                        "urls": [f"http://127.0.0.1:{port}/index.html"],
                        "mode": "focused",
                        "llm_provider": "anthropic",  # no key in test env -> deterministic rule-based fallback
                        "test_keyboard": False,
                        "test_mouse": False,
                        "output_dir": str(tmp_path),
                    },
                )
                assert resp.status_code == 202
                job_id = resp.get_json()["job_id"]

                deadline = time.time() + 30
                status_data = {}
                while time.time() < deadline:
                    st = client.get(f"/api/status/{job_id}")
                    assert st.status_code == 200
                    status_data = st.get_json()
                    if status_data["status"] in ("completed", "failed", "stopped"):
                        break
                    time.sleep(0.25)

                assert status_data["status"] == "completed", f"Job did not complete: {status_data}"
                assert status_data["total_findings"] >= 1
                session_id = status_data["session_id"]
                domain = status_data["domain"]

                sessions_resp = client.get("/api/sessions")
                assert sessions_resp.status_code == 200
                sessions = sessions_resp.get_json()["sessions"]
                assert any(s["session_id"] == session_id for s in sessions)

                detail_resp = client.get(f"/api/session/{domain}/{session_id}")
                assert detail_resp.status_code == 200
                detail = detail_resp.get_json()
                assert detail["findings"]
                for finding in detail["findings"]:
                    ver = finding["metadata"].get("verification")
                    assert ver is not None
                    assert ver["status"] in ("verified", "needs_review", "likely_false_positive")
                    assert isinstance(ver["confidence_score"], int)
                    assert ver["reason"]
        finally:
            server.shutdown()


@pytest.mark.integration
def test_ollama_qwen_live_verification(tmp_path):
    """Verify real local Ollama (qwen2.5:3b) verifies findings end-to-end."""
    ollama = get_ollama_status(timeout=2.0)
    if not ollama["available"] or not ollama["has_default_model"]:
        pytest.skip("Local Ollama with qwen2.5:3b is not available")

    import threading
    from http.server import HTTPServer, SimpleHTTPRequestHandler

    from qa_agent.agent import QAAgent
    from tests.integration.test_smoke import FIXTURES_DIR

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(FIXTURES_DIR), **kwargs)

        def log_message(self, format, *args):  # noqa: A002
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        config = TestConfig(
            urls=[f"http://127.0.0.1:{port}/index.html"],
            output_formats=[OutputFormat.JSON],
            output_dir=str(tmp_path),
            headless=True,
            test_keyboard=False,
            test_mouse=False,
            llm_provider=LLMProvider.OLLAMA,
            ai_model="qwen2.5:3b",
        )
        session = QAAgent(config).run()
        findings = session.get_all_findings()
        assert len(findings) >= 1

        ollama_verified = [
            f for f in findings
            if f.metadata.get("verification", {}).get("verification_method") == "ollama"
        ]
        assert len(ollama_verified) >= 1, (
            f"Expected Ollama verification on findings, got: {[f.metadata for f in findings]}"
        )
        for f in ollama_verified:
            ver = f.metadata["verification"]
            assert ver["status"] in ("verified", "needs_review", "likely_false_positive")
            assert 0 <= ver["confidence_score"] <= 100
            assert len(ver["reason"].strip()) > 0
            assert ver["model"] == "qwen2.5:3b"
    finally:
        server.shutdown()
