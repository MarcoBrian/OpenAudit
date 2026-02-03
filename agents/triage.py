from __future__ import annotations

import json
import os
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests

from agents.ollama_client import call_ollama

SEVERITY_ALIASES = {
    "CRIT": "CRITICAL",
    "CRITICAL": "CRITICAL",
    "SEVERE": "CRITICAL",
    "HIGH": "HIGH",
    "MAJOR": "HIGH",
    "MEDIUM": "MEDIUM",
    "MED": "MEDIUM",
    "MODERATE": "MEDIUM",
    "LOW": "LOW",
    "MINOR": "LOW",
    "INFO": "INFORMATIONAL",
    "INFORMATIONAL": "INFORMATIONAL",
    "NONE": "INFORMATIONAL",
}

CONFIDENCE_ALIASES = {
    "LOW": 0.3,
    "MEDIUM": 0.6,
    "HIGH": 0.85,
    "CERTAIN": 0.95,
}

SEVERITY_SCORES = {
    "CRITICAL": 4,
    "HIGH": 3,
    "MEDIUM": 2,
    "LOW": 1,
    "INFORMATIONAL": 0,
}


def _normalize_severity(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        normalized = SEVERITY_ALIASES.get(value.strip().upper())
        return normalized or None
    return None


def _normalize_confidence(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        normalized = float(value)
        if normalized > 1.0 and normalized <= 100.0:
            normalized /= 100.0
        return max(0.0, min(1.0, normalized))
    if isinstance(value, str):
        text = value.strip().upper()
        if text in CONFIDENCE_ALIASES:
            return CONFIDENCE_ALIASES[text]
        try:
            normalized = float(text)
        except ValueError:
            return None
        if normalized > 1.0 and normalized <= 100.0:
            normalized /= 100.0
        return max(0.0, min(1.0, normalized))
    return None


def _add_location(
    locations: List[Dict[str, Any]],
    *,
    file_path: Optional[str] = None,
    line: Optional[int] = None,
    span: Optional[str] = None,
) -> None:
    if file_path is None and line is None and span is None:
        return
    location: Dict[str, Any] = {}
    if file_path:
        location["file"] = file_path
    if line is not None:
        location["line"] = line
    if span:
        location["span"] = span
    locations.append(location)


def _extract_locations_from_mapping(
    locations: List[Dict[str, Any]],
    mapping: Dict[str, Any],
) -> None:
    file_path = (
        mapping.get("filename_relative")
        or mapping.get("filename")
        or mapping.get("file")
        or mapping.get("contract_path")
    )
    lines = mapping.get("lines") or mapping.get("line")
    span = mapping.get("src") or mapping.get("source")
    if isinstance(lines, list):
        for line in lines:
            if isinstance(line, str) and line.isdigit():
                line = int(line)
            if isinstance(line, int):
                _add_location(locations, file_path=file_path, line=line, span=span)
    elif isinstance(lines, int):
        _add_location(locations, file_path=file_path, line=lines, span=span)
    elif isinstance(lines, str) and lines.isdigit():
        _add_location(locations, file_path=file_path, line=int(lines), span=span)
    else:
        _add_location(locations, file_path=file_path, span=span)


def _extract_locations(finding: Dict[str, Any]) -> List[Dict[str, Any]]:
    locations: List[Dict[str, Any]] = []
    raw = finding.get("raw") or {}

    instances = raw.get("instances")
    if isinstance(instances, list):
        for instance in instances:
            if not isinstance(instance, dict):
                continue
            file_path = instance.get("contract_path") or instance.get("file")
            line = instance.get("line_no") or instance.get("line")
            if isinstance(line, str) and line.isdigit():
                line = int(line)
            span = instance.get("src") or instance.get("src_char")
            _add_location(locations, file_path=file_path, line=line, span=span)

    source_mapping = raw.get("source_mapping") or raw.get("sourceMapping")
    if isinstance(source_mapping, dict):
        _extract_locations_from_mapping(locations, source_mapping)

    elements = finding.get("elements")
    if isinstance(elements, list):
        for element in elements:
            if not isinstance(element, dict):
                continue
            mapping = element.get("source_mapping") or element.get("sourceMapping")
            if isinstance(mapping, dict):
                _extract_locations_from_mapping(locations, mapping)

    seen: set[Tuple[Optional[str], Optional[int], Optional[str]]] = set()
    unique: List[Dict[str, Any]] = []
    for location in locations:
        key = (
            location.get("file"),
            location.get("line"),
            location.get("span"),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(location)
    return unique


def _has_evidence(finding: Dict[str, Any]) -> bool:
    locations = finding.get("locations")
    if isinstance(locations, list) and locations:
        return True
    raw = finding.get("raw") or {}
    instances = raw.get("instances")
    if isinstance(instances, list) and instances:
        return True
    source_mapping = raw.get("source_mapping") or raw.get("sourceMapping")
    if isinstance(source_mapping, dict) and source_mapping.get("lines"):
        return True
    return False


def _normalize_existing_finding(finding: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(finding)
    title = (
        normalized.get("title")
        or normalized.get("check")
        or normalized.get("name")
        or "Untitled finding"
    )
    normalized["title"] = title

    severity = _normalize_severity(normalized.get("severity"))
    if severity is None:
        severity = _normalize_severity(normalized.get("impact"))
    normalized["severity"] = severity or "LOW"

    impact = normalized.get("impact")
    impact_severity = _normalize_severity(impact)
    if impact_severity is not None:
        normalized["impact"] = impact_severity

    normalized["confidence"] = _normalize_confidence(normalized.get("confidence"))

    if not normalized.get("locations"):
        normalized["locations"] = _extract_locations(normalized)

    sources = normalized.get("sources")
    if isinstance(sources, list):
        normalized["sources"] = [source for source in sources if source]
    return normalized


def _confidence_score(value: Any) -> int:
    normalized = _normalize_confidence(value)
    if normalized is None:
        return 1
    return int(round(normalized * 3))


def _rank_score(finding: Dict[str, Any]) -> int:
    severity = _normalize_severity(finding.get("severity")) or "LOW"
    severity_score = SEVERITY_SCORES.get(severity, 1)
    confidence_score = _confidence_score(finding.get("confidence"))
    return severity_score * 3 + confidence_score


def _dedupe_findings(findings: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    deduped: Dict[str, Dict[str, Any]] = {}

    def key_for(finding: Dict[str, Any]) -> str:
        title = (finding.get("title") or "").strip().lower()
        locations = finding.get("locations") or []
        file_path = ""
        line = ""
        if locations:
            first = locations[0]
            file_path = (first.get("file") or "").lower()
            line = str(first.get("line") or "")
        return f"{title}|{file_path}|{line}"

    for finding in findings:
        key = key_for(finding)
        if key not in deduped:
            deduped[key] = finding
            continue
        current = deduped[key]
        if _rank_score(finding) > _rank_score(current):
            primary, secondary = finding, current
        else:
            primary, secondary = current, finding

        merged = dict(primary)
        merged_locations = list(primary.get("locations") or [])
        merged_locations.extend(location for location in secondary.get("locations") or [])
        merged["locations"] = merged_locations

        sources: List[str] = []
        for source in (primary.get("source"), secondary.get("source")):
            if source and source not in sources:
                sources.append(source)
        merged["sources"] = sources

        for field in ("description", "impact", "remediation", "repro"):
            if not merged.get(field) and secondary.get(field):
                merged[field] = secondary[field]

        deduped[key] = merged

    return list(deduped.values())


def _normalize_finding(
    finding: Dict[str, Any],
    source: str | None,
    severity: str | None = None,
) -> Dict[str, Any]:
    normalized = {
        "title": finding.get("title") or finding.get("check") or finding.get("name"),
        "impact": finding.get("impact") or finding.get("severity") or severity,
        "severity": finding.get("severity") or severity,
        "confidence": finding.get("confidence") or finding.get("certainty"),
        "description": finding.get("description") or finding.get("details"),
        "elements": finding.get("elements", []),
        "source": source,
        "raw": finding,
    }
    return _normalize_existing_finding(normalized)


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
        ("informational_issues", "INFORMATIONAL"),
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
    sorted_detectors = sorted(detectors, key=_rank_score, reverse=True)
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

    normalized = [_normalize_existing_finding(detector) for detector in detectors]
    deduped = _dedupe_findings(normalized)
    evidence_filtered = [finding for finding in deduped if _has_evidence(finding)]
    filtered = evidence_filtered or deduped

    if not use_llm:
        return heuristic_rank(filtered, max_issues)

    api_key = os.getenv("OPENAI_API_KEY")
    ollama_model = os.getenv("OLLAMA_MODEL")
    if not api_key and not ollama_model:
        return heuristic_rank(filtered, max_issues)

    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    try:
        if api_key:
            return [
                _normalize_existing_finding(finding)
                for finding in call_llm(
                    filtered,
                    max_issues=max_issues,
                    api_key=api_key,
                    base_url=base_url,
                    model=model,
                )
            ]
        prompt = (
            "You are a smart-contract security triage agent. "
            "Given static analysis findings, pick the top vulnerabilities that are likely real "
            "and produce a JSON array of objects with fields: title, severity, confidence, "
            "description, impact, remediation, repro.\n\n"
            f"Limit to top {max_issues} issues. "
            "Use severity in [LOW, MEDIUM, HIGH, CRITICAL]. Confidence is 0-1.\n\n"
            "Findings:\n"
            f"{json.dumps(filtered, indent=2)}"
        )
        return [
            _normalize_existing_finding(finding)
            for finding in call_ollama(prompt=prompt, model=ollama_model)
        ]
    except (requests.RequestException, ValueError):
        return heuristic_rank(filtered, max_issues)
