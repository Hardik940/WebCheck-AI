import json
from types import SimpleNamespace

from qa_agent.finding_verifier import apply_verification


class FakeLLMClient:
    def __init__(self, text):
        self.text = text

    def complete(self, **kwargs):
        return SimpleNamespace(text=self.text)


def make_finding():
    return SimpleNamespace(
        title="Broken link",
        description="A link returned HTTP 404.",
        url="https://example.com",
        category="network_error",
        severity="medium",
        element_selector="a[href]",
        element_text="Continue",
        expected_behavior="The link should open a valid page.",
        actual_behavior="The link returned HTTP 404.",
        raw_error="HTTP 404",
        steps_to_reproduce=["Open the page", "Click Continue"],
        metadata={},
    )


def test_llm_verification_is_attached_to_finding():
    finding = make_finding()
    client = FakeLLMClient(json.dumps({
        "status": "verified",
        "confidence_score": 92,
        "issue_source": "website",
        "reason": "The supplied evidence reports an HTTP 404 response.",
    }))

    result = apply_verification([finding], llm_client=client)

    verification = result[0].metadata["verification"]
    assert verification["status"] == "verified"
    assert verification["confidence_score"] == 92
    assert verification["verification_method"] == "ollama"


def test_invalid_llm_response_uses_rule_based_fallback():
    finding = make_finding()
    result = apply_verification(
        [finding],
        llm_client=FakeLLMClient("not valid JSON"),
    )

    verification = result[0].metadata["verification"]
    assert verification["status"] == "needs_review"
    assert verification["verification_method"] == "rule_based_fallback"
    assert "llm_error" in verification


def test_without_llm_client_uses_rule_based_verification():
    finding = make_finding()
    result = apply_verification([finding])

    verification = result[0].metadata["verification"]
    assert verification["status"] == "needs_review"
    assert "verification_method" not in verification


def test_prose_wrapped_json_is_parsed():
    finding = make_finding()
    client = FakeLLMClient(
        "Here is my assessment:\n```json\n"
        + json.dumps({
            "status": "verified",
            "confidence_score": 88,
            "issue_source": "first_party_or_page",
            "reason": "Evidence shows HTTP 404 for the Continue link.",
        })
        + "\n```"
    )
    result = apply_verification([finding], llm_client=client)
    v = result[0].metadata["verification"]
    assert v["status"] == "verified"
    assert v["confidence_score"] == 88
    assert v["issue_source"] == "first_party_or_page"


def test_low_confidence_verified_downgraded_to_needs_review():
    finding = make_finding()
    client = FakeLLMClient(json.dumps({
        "status": "verified",
        "confidence_score": 30,
        "issue_source": "unknown",
        "reason": "Weak signal.",
    }))
    result = apply_verification([finding], llm_client=client)
    v = result[0].metadata["verification"]
    assert v["status"] == "needs_review"


def test_minimal_evidence_cannot_be_verified():
    minimal = SimpleNamespace(title="Unknown issue", url="", metadata={})
    client = FakeLLMClient(json.dumps({
        "status": "verified",
        "confidence_score": 95,
        "issue_source": "unknown",
        "reason": "Assumed broken.",
    }))
    result = apply_verification([minimal], llm_client=client)
    v = result[0].metadata["verification"]
    assert v["status"] == "needs_review"
    assert v["confidence_score"] <= 60


def test_summarize_verifications_aggregates_counts():
    from qa_agent.finding_verifier import summarize_verifications

    f1 = SimpleNamespace(metadata={"verification": {"status": "verified", "confidence_score": 90, "verification_method": "ollama"}})
    f2 = SimpleNamespace(metadata={"verification": {"status": "needs_review", "confidence_score": 60, "verification_method": "rule_based_fallback"}})
    f3 = SimpleNamespace(metadata={})
    summary = summarize_verifications([f1, f2, f3])
    assert summary["verified"] == 1
    assert summary["needs_review"] == 1
    assert summary["unverified"] == 1
    assert summary["average_confidence"] == 75.0
    assert summary["methods"]["ollama"] == 1

