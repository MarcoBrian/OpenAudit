from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Reference:
    source: str
    url: str
    note: str


@dataclass
class Evidence:
    static_tool: str
    raw_findings: List[str]
    file_path: str


@dataclass
class Submission:
    title: str
    severity: str
    confidence: float
    description: str
    impact: str
    references: List[Reference]
    remediation: str
    repro: Optional[str]
    evidence: Evidence

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "severity": self.severity,
            "confidence": self.confidence,
            "description": self.description,
            "impact": self.impact,
            "references": [reference.__dict__ for reference in self.references],
            "remediation": self.remediation,
            "repro": self.repro,
            "evidence": self.evidence.__dict__,
        }


def build_submission(
    *,
    title: str,
    severity: str,
    confidence: float,
    description: str,
    impact: str,
    references: List[Reference],
    remediation: str,
    repro: Optional[str],
    evidence: Evidence,
) -> Submission:
    if not (0.0 <= confidence <= 1.0):
        raise ValueError("confidence must be between 0.0 and 1.0")
    return Submission(
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

