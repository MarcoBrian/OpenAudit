from __future__ import annotations

import argparse
import json
from pathlib import Path

from agents.schema import Evidence, Reference, build_submission
from agents.aderyn_runner import run_aderyn
from agents.slither_runner import run_slither
from agents.solodit import build_search_links
from agents.reporting import write_report
from agents.triage import extract_findings, triage_findings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OpenAudit Agent MVP")
    parser.add_argument("--file", required=True, help="Path to Solidity file")
    parser.add_argument("--out", default="submission.json", help="Output JSON file")
    parser.add_argument(
        "--max-issues",
        type=int,
        default=2,
        help="Max issues to output in the submission",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Disable LLM triage and use heuristic ranking",
    )
    parser.add_argument(
        "--use-graph",
        action="store_true",
        help="Run the workflow via LangGraph",
    )
    parser.add_argument(
        "--tools",
        default="aderyn",
        help="Comma-separated tools to run: aderyn, slither",
    )
    return parser


def build_submission_payload(
    *,
    solidity_file: Path,
    findings: list[dict],
    triaged: list[dict],
    static_tools: list[str],
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

    references = [Reference(**reference) for reference in build_search_links(title)]
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


def run_linear(
    *,
    solidity_file: Path,
    max_issues: int,
    use_llm: bool,
    tools: list[str],
) -> dict:
    findings: list[dict] = []
    reports_dir = Path(__file__).resolve().parent.parent / "reports"
    for tool in tools:
        if tool == "aderyn":
            report_json = run_aderyn(solidity_file)
            write_report("aderyn", report_json, reports_dir)
            findings.extend(extract_findings(report_json, source="aderyn"))
        elif tool == "slither":
            report_json = run_slither(solidity_file)
            write_report("slither", report_json, reports_dir)
            findings.extend(extract_findings(report_json, source="slither"))
        else:
            raise ValueError(f"Unknown tool: {tool}")
    triaged = triage_findings(findings, max_issues=max_issues, use_llm=use_llm)
    return build_submission_payload(
        solidity_file=solidity_file,
        findings=findings,
        triaged=triaged,
        static_tools=tools,
    )


def run_graph(
    *,
    solidity_file: Path,
    max_issues: int,
    use_llm: bool,
    tools: list[str],
) -> dict:
    from agents.graph import run_workflow

    return run_workflow(
        solidity_file=solidity_file,
        max_issues=max_issues,
        use_llm=use_llm,
        tools=tools,
    )


def main() -> int:
    args = build_parser().parse_args()
    solidity_file = Path(args.file)
    tools = [tool.strip().lower() for tool in args.tools.split(",") if tool.strip()]

    if args.use_graph:
        output = run_graph(
            solidity_file=solidity_file,
            max_issues=args.max_issues,
            use_llm=not args.no_llm,
            tools=tools,
        )
    else:
        output = run_linear(
            solidity_file=solidity_file,
            max_issues=args.max_issues,
            use_llm=not args.no_llm,
            tools=tools,
        )

    Path(args.out).write_text(json.dumps(output, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

