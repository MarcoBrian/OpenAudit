from __future__ import annotations

import json
import os
from pathlib import Path
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

SNIPPET_CONTEXT_LINES = 3

DEFAULT_FILTERS = {
    "min_severity": "MEDIUM",
    "min_confidence": 0.6,
    "default": {"allow": [], "deny": []},
    "tools": {
        "slither": {
            "allow": [
                "reentrancy",
                "arbitrary-send",
                "tx-origin",
                "delegatecall",
                "weak-prng",
                "incorrect-equality",
                "oracle",
                "price-manipulation",
                "access-control",
                "uninitialized",
                "selfdestruct",
                "suicidal",
                "proxy",
                "upgrade",
                "signature",
                "replay",
                "dos",
                "denial-of-service",
                "front-run",
                "frontrun",
                "mev",
            ],
            "deny": [
                "solc-version",
                "naming-convention",
                "constable-states",
                "state-variable-could-be-constant",
                "dead-code",
                "unused-return",
                "pragma",
                "immutable-states",
                "redundant-statements",
            ],
        },
        "aderyn": {
            "allow": [
                "tx-origin",
                "reentrancy",
                "access-control",
                "authorization",
                "arbitrary-send",
                "delegatecall",
                "selfdestruct",
                "oracle",
                "price-manipulation",
                "uninitialized",
                "proxy",
                "upgrade",
                "signature",
                "replay",
                "dos",
                "denial-of-service",
                "front-run",
                "frontrun",
                "mev",
            ],
            "deny": [
                "empty-require-revert",
                "modifier-used-only-once",
                "state-variable-could-be-constant",
                "public-function-not-used-internally",
                "unused-function",
                "unused-variable",
            ],
        },
    },
}


def _format_snippet(lines: List[str], start_line: int) -> str:
    formatted = []
    for idx, line in enumerate(lines, start=start_line):
        formatted.append(f"{idx:>4} | {line.rstrip()}")
    return "\n".join(formatted)


def _canonical_identifier(text: str) -> str:
    lowered = "".join(ch.lower() if ch.isalnum() else "-" for ch in text.strip())
    return "-".join(part for part in lowered.split("-") if part)


def _load_filters() -> Dict[str, Any]:
    path_override = os.getenv("OPENAUDIT_FILTERS_PATH")
    if path_override:
        candidate = Path(path_override).expanduser()
        if candidate.is_file():
            return json.loads(candidate.read_text(encoding="utf-8"))

    default_path = Path(__file__).with_name("triage_filters.json")
    if default_path.is_file():
        return json.loads(default_path.read_text(encoding="utf-8"))

    return dict(DEFAULT_FILTERS)


def _parse_patterns(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _severity_threshold(config: Dict[str, Any]) -> Optional[int]:
    override = os.getenv("OPENAUDIT_MIN_SEVERITY")
    raw = override if override is not None else config.get("min_severity")
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return int(raw)
    if isinstance(raw, str):
        normalized = _normalize_severity(raw)
        if normalized:
            return SEVERITY_SCORES.get(normalized)
    return None


def _confidence_threshold(config: Dict[str, Any]) -> Optional[float]:
    override = os.getenv("OPENAUDIT_MIN_CONFIDENCE")
    raw = override if override is not None else config.get("min_confidence")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _finding_identifiers(finding: Dict[str, Any]) -> List[str]:
    raw = finding.get("raw") or {}
    identifiers: List[str] = []
    for key in ("title", "check", "name"):
        value = finding.get(key)
        if value:
            identifiers.append(str(value))
    for key in ("check", "detector_name", "id", "name", "title"):
        value = raw.get(key)
        if value:
            identifiers.append(str(value))
    return identifiers


def _matches_patterns(identifiers: List[str], patterns: List[str]) -> bool:
    if not patterns:
        return False
    canonical_identifiers = [_canonical_identifier(value) for value in identifiers]
    for pattern in patterns:
        canonical_pattern = _canonical_identifier(pattern)
        if not canonical_pattern:
            continue
        for identifier in canonical_identifiers:
            if canonical_pattern in identifier:
                return True
    return False


def filter_findings(findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    config = _load_filters()
    tools_config = config.get("tools") or {}
    default_config = config.get("default") or {}
    default_allow = _parse_patterns(default_config.get("allow"))
    default_deny = _parse_patterns(default_config.get("deny"))

    min_severity_score = _severity_threshold(config)
    min_confidence = _confidence_threshold(config)

    filtered: List[Dict[str, Any]] = []
    for finding in findings:
        source = (finding.get("source") or "default").lower()
        tool_config = tools_config.get(source) or {}
        allow = _parse_patterns(tool_config.get("allow"))
        deny = _parse_patterns(tool_config.get("deny"))
        if not allow:
            allow = list(default_allow)
        deny = list(default_deny) + deny

        identifiers = _finding_identifiers(finding)
        if deny and _matches_patterns(identifiers, deny):
            continue
        if allow and not _matches_patterns(identifiers, allow):
            continue

        if min_severity_score is not None:
            severity = _normalize_severity(finding.get("severity")) or "LOW"
            if SEVERITY_SCORES.get(severity, 0) < min_severity_score:
                continue
        if min_confidence is not None:
            confidence = _normalize_confidence(finding.get("confidence"))
            if confidence is None:
                confidence = 0.5
            if confidence < min_confidence:
                continue

        filtered.append(finding)
    return filtered


def _resolve_file_path(file_path: str) -> Optional[Path]:
    candidate = Path(file_path)
    if candidate.is_file():
        return candidate
    cwd_candidate = Path.cwd() / file_path
    if cwd_candidate.is_file():
        return cwd_candidate
    return None


def _read_snippet(
    file_path: str,
    *,
    line: int,
    context_lines: int = SNIPPET_CONTEXT_LINES,
    cache: Dict[Path, List[str]],
) -> Optional[Dict[str, Any]]:
    resolved = _resolve_file_path(file_path)
    if resolved is None:
        return None
    if resolved not in cache:
        try:
            cache[resolved] = resolved.read_text(encoding="utf-8").splitlines()
        except OSError:
            return None
    lines = cache[resolved]
    if line < 1 or line > len(lines):
        return None
    start_line = max(1, line - context_lines)
    end_line = min(len(lines), line + context_lines)
    snippet_lines = lines[start_line - 1 : end_line]
    return {
        "start_line": start_line,
        "end_line": end_line,
        "snippet": _format_snippet(snippet_lines, start_line),
    }


def _attach_snippets(findings: List[Dict[str, Any]]) -> None:
    cache: Dict[Path, List[str]] = {}
    for finding in findings:
        locations = finding.get("locations")
        if not isinstance(locations, list):
            continue
        for location in locations:
            if not isinstance(location, dict):
                continue
            file_path = location.get("file")
            line = location.get("line")
            if not file_path or not isinstance(line, int):
                continue
            snippet_info = _read_snippet(file_path, line=line, cache=cache)
            if snippet_info:
                location.update(snippet_info)


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
        "Use severity in [LOW, MEDIUM, HIGH, CRITICAL]. Confidence is 0-1. "
        "Each finding may include code snippets in locations[].snippet.\n\n"
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
    filtered = filter_findings(filtered)

    if not filtered:
        return []

    if not use_llm:
        return heuristic_rank(filtered, max_issues)

    api_key = os.getenv("OPENAI_API_KEY")
    ollama_model = os.getenv("OLLAMA_MODEL")
    if not api_key and not ollama_model:
        return heuristic_rank(filtered, max_issues)

    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    try:
        _attach_snippets(filtered)
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
            "Use severity in [LOW, MEDIUM, HIGH, CRITICAL]. Confidence is 0-1. "
            "Each finding may include code snippets in locations[].snippet.\n\n"
            "Findings:\n"
            f"{json.dumps(filtered, indent=2)}"
        )
        return [
            _normalize_existing_finding(finding)
            for finding in call_ollama(prompt=prompt, model=ollama_model)
        ]
    except (requests.RequestException, ValueError):
        return heuristic_rank(filtered, max_issues)
