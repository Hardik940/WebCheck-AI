"""Evidence-based and optional LLM-assisted verification of QA findings."""

from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

ALLOWED_STATUSES = frozenset({"verified", "likely_false_positive", "needs_review"})


def _get_text(finding: Any) -> str:
    parts = [
        getattr(finding, "title", ""),
        getattr(finding, "description", ""),
        getattr(finding, "raw_error", "") or "",
        getattr(finding, "actual_behavior", "") or "",
        str(getattr(finding, "metadata", {}) or {}),
    ]
    return " ".join(str(part) for part in parts).lower()


def _extract_hosts(text: str) -> list[str]:
    urls = re.findall(r"https?://\S+", text)
    hosts: list[str] = []
    for url in urls:
        try:
            host = urlparse(url.rstrip(".,);]\"'")).hostname
            if host:
                hosts.append(host.lower())
        except ValueError:
            continue
    return list(dict.fromkeys(hosts))


def _has_concrete_evidence(finding: Any) -> bool:
    """Return True if the finding includes concrete observed details beyond a bare title."""
    fields = (
        getattr(finding, "description", None),
        getattr(finding, "raw_error", None),
        getattr(finding, "actual_behavior", None),
        getattr(finding, "element_selector", None),
        getattr(finding, "steps_to_reproduce", None),
    )
    for val in fields:
        if isinstance(val, str) and val.strip():
            return True
        if isinstance(val, (list, tuple)) and len(val) > 0:
            return True
    meta = getattr(finding, "metadata", None)
    if isinstance(meta, dict) and any(k != "verification" for k in meta):
        return True
    return False


def verify_finding(finding: Any) -> dict[str, Any]:
    """Apply conservative, rule-based verification without fabricating evidence."""
    text = _get_text(finding)
    category = str(getattr(finding, "category", "") or "").lower()
    page_host = urlparse(getattr(finding, "url", "") or "").hostname
    page_host = page_host.lower() if page_host else None

    result: dict[str, Any] = {
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
        return result

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
        return result

    if "focus indicator" in text or "visible focus" in text or "outline" in text:
        result.update({
            "confidence_score": 70,
            "issue_source": "website_accessibility",
            "reason": (
                "A focus-indicator issue was reported. "
                "Verify keyboard focus visibility."
            ),
        })
    elif "missing h1" in text or "no h1" in text or "missing alt" in text or "alt attribute" in text:
        result.update({
            "confidence_score": 70,
            "issue_source": "website_accessibility",
            "reason": (
                "An accessibility structure issue was reported from DOM inspection. "
                "Confirm the element semantics and page structure."
            ),
        })
    elif any(kw in text for kw in ("color contrast", "aria", "landmark", "skip link", "lang attribute")) or "accessibility" in category:
        result.update({
            "confidence_score": 72,
            "issue_source": "website_accessibility",
            "reason": (
                "An accessibility check flagged this element or page attribute. "
                "Review against WCAG guidelines."
            ),
        })
    elif any(kw in text for kw in ("http 5", "500 ", "502 ", "503 ", "504 ")):
        result.update({
            "confidence_score": 85,
            "issue_source": "first_party_or_page",
            "reason": (
                "A server-side 5xx HTTP response was observed during navigation or resource loading. "
                "Confirm server logs and endpoint availability."
            ),
        })
    elif any(kw in text for kw in ("http 4", "404", "broken image", "broken link")) or "network_error" in category:
        result.update({
            "confidence_score": 78,
            "issue_source": "first_party_or_page" if page_host else "unknown",
            "reason": (
                "A failing HTTP response or broken resource was observed. "
                "Confirm whether the target resource is missing or restricted."
            ),
        })
    elif any(kw in text for kw in ("uncaught", "typeerror", "referenceerror", "syntaxerror", "js exception")) or "console_error" in category:
        result.update({
            "confidence_score": 75,
            "issue_source": "first_party_or_page" if page_host else "unknown",
            "reason": (
                "A runtime console or JavaScript error was captured on the page. "
                "Check whether it breaks interactive functionality."
            ),
        })
    elif "form_handling" in category or any(kw in text for kw in ("missing label", "autocomplete", "required field", "validation")):
        result.update({
            "confidence_score": 70,
            "issue_source": "website_forms",
            "reason": (
                "A form usability or labeling issue was detected in the DOM. "
                "Verify form submission and assistive-tech behavior."
            ),
        })
    elif "keyboard" in category or "mouse" in category or any(kw in text for kw in ("keyboard trap", "click target", "overlapping")):
        result.update({
            "confidence_score": 68,
            "issue_source": "website_interaction",
            "reason": (
                "An interaction check reported unexpected keyboard or pointer behavior. "
                "Reproduce manually to confirm user impact."
            ),
        })
    elif page_host:
        result["issue_source"] = "first_party_or_page"

    return result


def _extract_json_object(raw_text: str) -> dict[str, Any]:
    """Parse a JSON object from LLM output, stripping optional code fences."""
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.I).strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end > start:
            data = json.loads(cleaned[start : end + 1])
        else:
            raise

    if not isinstance(data, dict):
        raise ValueError("LLM verification response is not a JSON object")
    return data


def _verify_with_llm(finding: Any, client: Any, fallback: dict[str, Any]) -> dict[str, Any]:
    """Ask an LLM to assess a finding, without inventing evidence."""
    payload = {
        "title": getattr(finding, "title", ""),
        "description": getattr(finding, "description", ""),
        "url": getattr(finding, "url", ""),
        "category": str(getattr(finding, "category", "")),
        "severity": str(getattr(finding, "severity", "")),
        "element_selector": getattr(finding, "element_selector", None),
        "element_text": getattr(finding, "element_text", None),
        "expected_behavior": getattr(finding, "expected_behavior", None),
        "actual_behavior": getattr(finding, "actual_behavior", None),
        "raw_error": getattr(finding, "raw_error", None),
        "steps_to_reproduce": getattr(finding, "steps_to_reproduce", []),
        "rule_based_assessment": fallback,
    }

    system = (
        "You are a cautious software QA finding reviewer. Assess ONLY the "
        "provided evidence. Do NOT invent browser observations, URLs, selectors, "
        "or claim you retested the website. A third-party request alone does not "
        "prove a bug. Return ONLY valid JSON with keys: status, confidence_score, "
        "issue_source, reason. "
        "status must be one of: verified, likely_false_positive, needs_review. "
        "confidence_score must be an integer from 0 to 100. "
        "issue_source should be a short snake_case label such as "
        "first_party_or_page, third_party, browser_or_policy, "
        "website_accessibility, website_forms, website_interaction, or unknown. "
        "reason must be a fresh, finding-specific 1-2 sentence explanation "
        "referencing the actual finding title/description/behavior (do not copy "
        "rule_based_assessment.reason verbatim). "
        "Use needs_review when evidence is weak or ambiguous."
    )

    kwargs: dict[str, Any] = {
        "system": system,
        "user": json.dumps(payload, ensure_ascii=False, default=str),
        "max_tokens": 350,
        "timeout": 45,
    }
    if hasattr(client, "_base_url"):
        kwargs["json_mode"] = True

    response = client.complete(**kwargs)
    data = _extract_json_object(response.text)

    status = data.get("status")
    if status not in ALLOWED_STATUSES:
        raise ValueError("Invalid verification status from LLM")

    score = data.get("confidence_score")
    if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score):
        raise ValueError("Invalid confidence score from LLM")
    normalized_score = max(0, min(100, int(round(score))))

    reason = data.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("Missing verification reason from LLM")
    cleaned_reason = reason.strip()[:1000]

    raw_source = data.get("issue_source")
    issue_source = (
        raw_source.strip()[:80]
        if isinstance(raw_source, str) and raw_source.strip()
        else fallback["issue_source"]
    )

    # Anti-hallucination guardrails:
    # 1. Never allow "verified" if confidence is below 50.
    if status == "verified" and normalized_score < 50:
        status = "needs_review"

    # 2. Never mark a finding with almost no concrete evidence as high-confidence verified.
    if status == "verified" and not _has_concrete_evidence(finding):
        status = "needs_review"
        normalized_score = min(normalized_score, 60)
        cleaned_reason = (
            f"{cleaned_reason} (Downgraded to needs_review because supplied evidence is minimal.)"
        )[:1000]

    provider_obj = getattr(response, "provider", None)
    if provider_obj is not None and hasattr(provider_obj, "value"):
        provider_name = str(provider_obj.value)
    elif provider_obj is not None:
        provider_name = str(provider_obj)
    else:
        provider_name = "ollama"
    model_name = getattr(response, "model", None) or getattr(client, "model", None)

    result = dict(fallback)
    result.update({
        "status": status,
        "confidence_score": normalized_score,
        "issue_source": issue_source,
        "reason": cleaned_reason,
        "verification_method": provider_name,
        "verified_at": datetime.now(timezone.utc).isoformat(),
    })
    if model_name:
        result["model"] = str(model_name)
    return result


def apply_verification(findings: list[Any], llm_client: Any = None) -> list[Any]:
    """Attach rule-based results and optionally refine them with an LLM."""
    for finding in findings:
        if finding.metadata is None:
            finding.metadata = {}

        fallback = verify_finding(finding)
        result = fallback

        if llm_client is not None:
            try:
                result = _verify_with_llm(finding, llm_client, fallback)
            except Exception as exc:
                result = dict(fallback)
                result["verification_method"] = "rule_based_fallback"
                result["llm_error"] = str(exc)[:300]
                result["verified_at"] = datetime.now(timezone.utc).isoformat()

        finding.metadata["verification"] = result

    return findings


def summarize_verifications(findings: list[Any]) -> dict[str, Any]:
    """Aggregate verification counts and average confidence across findings."""
    counts = {
        "verified": 0,
        "needs_review": 0,
        "likely_false_positive": 0,
        "unverified": 0,
    }
    methods: dict[str, int] = {}
    scores: list[int] = []

    for finding in findings:
        meta = finding.get("metadata") if isinstance(finding, dict) else getattr(finding, "metadata", None)
        v = meta.get("verification") if isinstance(meta, dict) else None
        if not isinstance(v, dict):
            counts["unverified"] += 1
            continue
        status = v.get("status", "needs_review")
        if status in counts:
            counts[status] += 1
        else:
            counts["needs_review"] += 1
        score = v.get("confidence_score")
        if isinstance(score, (int, float)) and not isinstance(score, bool):
            scores.append(int(score))
        method = v.get("verification_method") or "rule_based"
        methods[method] = methods.get(method, 0) + 1

    return {
        **counts,
        "average_confidence": round(sum(scores) / len(scores), 1) if scores else None,
        "methods": methods,
    }
