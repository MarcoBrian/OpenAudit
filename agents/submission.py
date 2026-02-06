from __future__ import annotations

from pathlib import Path

from agents.reporting import write_json
from agents.schema import Evidence, Reference, build_submission
from agents.solodit import build_references


def build_submission_payload(
    *,
    solidity_file: Path,
    findings: list[dict],
    triaged: list[dict],
    static_tools: list[str],
    reports_dir: Path | None = None,
) -> dict:
    def normalize_confidence(value: object) -> float:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            mapping = {"low": 0.3, "medium": 0.6, "high": 0.85}
            normalized = mapping.get(value.strip().lower())
            if normalized is not None:
                return normalized
        return 0.5

    if not triaged:
        return {"message": "No actionable findings detected.", "findings": []}

    top = triaged[0]
    title = top.get("title") or top.get("check") or "Potential vulnerability"
    severity = top.get("severity") or "MEDIUM"
    confidence = normalize_confidence(top.get("confidence", 0.5))
    description = top.get("description") or "No description provided."
    impact = top.get("impact") or "Potential impact not specified."
    remediation = top.get("remediation") or "Review and apply standard mitigations."
    repro = top.get("repro")

    references_payload = build_references(
        issue_title=title,
        description=description,
        impact=impact,
        severity=severity,
        confidence=confidence,
    )
    if reports_dir:
        write_json("solodit.json", references_payload, reports_dir)
    references = [Reference(**reference) for reference in references_payload]
    evidence = Evidence(
        static_tool="+".join(static_tools),
        raw_findings=[
            finding.get("title")
            or finding.get("check")
            or finding.get("name")
            or "unknown"
            for finding in findings
        ],
        file_path=str(solidity_file),
    )

    submission = build_submission(
        title=title,
        severity=severity,
        confidence=confidence,
        description=description,
        impact=impact,
        references=references,
        remediation=remediation,
        repro=repro,
        evidence=evidence,
    )

    return submission.to_dict()
