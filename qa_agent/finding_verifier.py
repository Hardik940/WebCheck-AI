
"""Evidence-based verification for automated QA findings."""

import re
from urllib.parse import urlparse


def _get_text(finding) -> str:
    parts = [
        getattr(finding, "title", ""),
        getattr(finding, "description", ""),
        getattr(finding, "raw_error", "") or "",
        str(getattr(finding, "metadata", {}) or {}),
    ]
    return " ".join(str(part) for part in parts).lower()


def _extract_hosts(text: str) -> list[str]:
    urls = re.findall(r"https?://[^\s'\"<>]+", text)
    hosts = []

    for url in urls:
        try:
            host = urlparse(url.rstrip(".,);]")).hostname
            if host:
                hosts.append(host.lower())
        except ValueError:
            continue

    return list(dict.fromkeys(hosts))


def verify_finding(finding) -> dict:
    """Apply conservative, rule-based verification to a finding."""

    text = _get_text(finding)
    page_host = urlparse(getattr(finding, "url", "") or "").hostname
    page_host = page_host.lower() if page_host else None

    result = {
        "status": "needs_review",
        "confidence_score": 50,
        "issue_source": "unknown",
        "reason": "Insufficient evidence for an automatic decision.",
    }

    if "permissions policy" in text and "unload" in text:
        result.update({
            "confidence_score": 90,
            "issue_source": "browser_or_policy",
            "reason": (
                "This resembles a browser permissions-policy warning. "
                "Check whether it causes a user-visible problem."
            ),
        })

    else:
        hosts = _extract_hosts(text)
        external_hosts = [
            host for host in hosts
            if page_host
            and host != page_host
            and not host.endswith("." + page_host)
            and not page_host.endswith("." + host)
        ]

        if external_hosts:
            result.update({
                "confidence_score": 85,
                "issue_source": "third_party",
                "reason": (
                    "Evidence contains requests to another host: "
                    + ", ".join(external_hosts)
                    + ". Review whether this affects functionality."
                ),
            })

        elif "focus indicator" in text or "visible focus" in text:
            result.update({
                "confidence_score": 70,
                "issue_source": "website_accessibility",
                "reason": (
                    "A focus-indicator issue was reported. "
                    "Verify keyboard focus visibility."
                ),
            })

        elif "missing h1" in text or "no h1" in text:
            result.update({
                "confidence_score": 70,
                "issue_source": "website_accessibility",
                "reason": (
                    "No H1 heading was reported. Inspect the page "
                    "heading structure before confirming."
                ),
            })

        elif page_host:
            result["issue_source"] = "first_party_or_page"

    return result


def apply_verification(findings: list) -> list:
    """Attach verification results to findings using existing metadata."""

    for finding in findings:
        if finding.metadata is None:
            finding.metadata = {}

        finding.metadata["verification"] = verify_finding(finding)

    return findings

