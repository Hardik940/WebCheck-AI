from types import SimpleNamespace

from qa_agent.finding_verifier import (
    apply_verification,
    verify_finding,
)


def make_finding(title="", description="", url="https://example.com",
                 raw_error=None, metadata=None):
    return SimpleNamespace(
        title=title,
        description=description,
        url=url,
        raw_error=raw_error,
        metadata=metadata or {},
    )


def test_unknown_finding_needs_review():
    finding = make_finding(title="Something unusual", url="")

    result = verify_finding(finding)

    assert result["status"] == "needs_review"
    assert result["confidence_score"] == 50
    assert result["issue_source"] == "unknown"


def test_permissions_policy_warning():
    finding = make_finding(
        title="Console error",
        description="Permissions policy violation: unload is not allowed",
    )

    result = verify_finding(finding)

    assert result["issue_source"] == "browser_or_policy"
    assert result["confidence_score"] == 90


def test_third_party_request():
    finding = make_finding(
        title="HTTP 401 errors",
        metadata={"url": "https://events.example.net/api/submit"},
    )

    result = verify_finding(finding)

    assert result["issue_source"] == "third_party"
    assert result["confidence_score"] == 85


def test_missing_h1():
    finding = make_finding(
        title="Page missing h1 heading",
        description="No h1 element found on the page",
    )

    result = verify_finding(finding)

    assert result["issue_source"] == "website_accessibility"
    assert result["confidence_score"] == 70


def test_apply_verification_attaches_metadata():
    finding = make_finding(title="Missing focus indicators")

    findings = apply_verification([finding])

    assert len(findings) == 1
    assert "verification" in finding.metadata
    assert finding.metadata["verification"]["issue_source"] == (
        "website_accessibility"
    )
