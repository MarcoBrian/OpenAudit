from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

import requests


def _normalize_finding(
    finding: Dict[str, Any],
    source: str | None,
    severity: str | None = None,
) -> Dict[str, Any]:
    return {
        "title": finding.get("title") or finding.get("check") or finding.get("name"),
        "impact": finding.get("impact") or finding.get("severity") or severity,
        "severity": finding.get("severity") or severity,
        "confidence": finding.get("confidence") or finding.get("certainty"),
        "description": finding.get("description") or finding.get("details"),
        "elements": finding.get("elements", []),
        "source": source,
        "raw": finding,
    }


def _extract_list(report_json: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []

    for key in ("findings", "issues", "vulnerabilities", "detectors"):
        value = report_json.get(key)
        if isinstance(value, list):
            candidates = value
            break

    if not candidates:
        results = report_json.get("results", {})
        for key in ("findings", "issues", "vulnerabilities", "detectors"):
            value = results.get(key)
            if isinstance(value, list):
                candidates = value
                break

    return candidates


def extract_findings(report_json: Dict[str, Any], source: str | None = None) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []

    for item in _extract_list(report_json):
        findings.append(_normalize_finding(item, source))

    aderyn_sections = (
        ("high_issues", "HIGH"),
        ("medium_issues", "MEDIUM"),
        ("low_issues", "LOW"),
        ("informational_issues", "LOW"),
    )

    for section_key, severity in aderyn_sections:
        section = report_json.get(section_key)
        if not isinstance(section, dict):
            continue
        issues = section.get("issues", [])
        if not isinstance(issues, list):
            continue
        for issue in issues:
            findings.append(_normalize_finding(issue, source, severity))

    return findings


def heuristic_rank(detectors: List[Dict[str, Any]], max_issues: int) -> List[Dict[str, Any]]:
    impact_weight = {"High": 3, "Medium": 2, "Low": 1, "Informational": 0}
    confidence_weight = {"High": 3, "Medium": 2, "Low": 1}

    def score(detector: Dict[str, Any]) -> int:
        impact = impact_weight.get(detector.get("impact", "Low"), 1)
        confidence = confidence_weight.get(detector.get("confidence", "Low"), 1)
        return impact * 3 + confidence

    sorted_detectors = sorted(detectors, key=score, reverse=True)
    return sorted_detectors[:max_issues]


def call_llm(
    detectors: List[Dict[str, Any]],
    *,
    max_issues: int,
    api_key: str,
    base_url: str,
    model: str,
    timeout: int = 60,
) -> List[Dict[str, Any]]:
    prompt = (
        "You are a smart-contract security triage agent. "
        "Given static analysis findings, pick the top vulnerabilities that are likely real "
        "and produce a JSON array of objects with fields: title, severity, confidence, "
        "description, impact, remediation, repro.\n\n"
        f"Limit to top {max_issues} issues. "
        "Use severity in [LOW, MEDIUM, HIGH, CRITICAL]. Confidence is 0-1.\n\n"
        "Findings:\n"
        f"{json.dumps(detectors, indent=2)}"
    )

    response = requests.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        },
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    content = payload["choices"][0]["message"]["content"]
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM response was not valid JSON: {content}") from exc


def triage_findings(
    detectors: List[Dict[str, Any]],
    *,
    max_issues: int = 2,
    use_llm: bool = True,
) -> List[Dict[str, Any]]:
    if not detectors:
        return []

    if not use_llm:
        return heuristic_rank(detectors, max_issues)

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return heuristic_rank(detectors, max_issues)

    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    try:
        return call_llm(
            detectors,
            max_issues=max_issues,
            api_key=api_key,
            base_url=base_url,
            model=model,
        )
    except (requests.RequestException, ValueError):
        return heuristic_rank(detectors, max_issues)

