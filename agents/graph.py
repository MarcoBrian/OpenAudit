from __future__ import annotations

from pathlib import Path
import os
from typing import Dict, List, TypedDict

from agents.aderyn_runner import run_aderyn
from agents.slither_runner import run_slither
from agents.cli import build_submission_payload
from agents.reporting import write_json, write_report
from agents.logic import logic_review
from agents.progress import ProgressReporter
from agents.triage import extract_findings, triage_findings


class AgentState(TypedDict, total=False):
    solidity_file: Path
    max_issues: int
    use_llm: bool
    tools: List[str]
    progress: ProgressReporter | None
    reports_dir: Path
    report_jsons: List[Dict]
    findings: List[Dict]
    triaged: List[Dict]
    logic_findings: List[Dict]
    submission: Dict


def node_scan(state: AgentState) -> AgentState:
    report_jsons: List[Dict] = []
    reports_dir = state.get("reports_dir") or (
        Path(__file__).resolve().parent.parent / "reports"
    )
    progress = state.get("progress")
    for tool in state["tools"]:
        if tool == "aderyn":
            if progress:
                progress.start("scan.aderyn", "Running Aderyn")
            report_json = run_aderyn(state["solidity_file"])
            write_report("aderyn", report_json, reports_dir)
            report_jsons.append({"source": "aderyn", "data": report_json})
            if progress:
                progress.complete("scan.aderyn", "Aderyn report ready")
        elif tool == "slither":
            if progress:
                progress.start("scan.slither", "Running Slither")
            report_json = run_slither(state["solidity_file"])
            write_report("slither", report_json, reports_dir)
            report_jsons.append({"source": "slither", "data": report_json})
            if progress:
                progress.complete("scan.slither", "Slither report ready")
        else:
            raise ValueError(f"Unknown tool: {tool}")
    return {"report_jsons": report_jsons}


def node_extract(state: AgentState) -> AgentState:
    findings: List[Dict] = []
    progress = state.get("progress")
    if progress:
        progress.start("extract", "Normalizing findings")
    for report in state["report_jsons"]:
        findings.extend(extract_findings(report["data"], source=report["source"]))
    reports_dir = state.get("reports_dir")
    if reports_dir:
        write_json("static_analysis_summary.json", findings, reports_dir)
    if progress:
        progress.complete("extract", f"Extracted {len(findings)} findings")
    return {"findings": findings}


def node_triage(state: AgentState) -> AgentState:
    progress = state.get("progress")
    if progress:
        progress.start("triage", "Ranking findings")
    triaged = triage_findings(
        state["findings"],
        max_issues=state["max_issues"],
        use_llm=state["use_llm"],
    )
    reports_dir = state.get("reports_dir")
    if reports_dir:
        write_json("triage.json", triaged, reports_dir)
    if progress:
        progress.complete("triage", f"Selected {len(triaged)} findings")
    return {"triaged": triaged}


def node_logic(state: AgentState) -> AgentState:
    progress = state.get("progress")
    if not state["use_llm"]:
        if progress:
            progress.complete("logic", "Logic review skipped")
        return {"logic_findings": []}
    api_key = os.getenv("OPENAI_API_KEY")
    ollama_model = os.getenv("OLLAMA_MODEL")
    if not (api_key or ollama_model):
        if progress:
            progress.complete("logic", "Logic review skipped (LLM not configured)")
        return {"logic_findings": []}
    if progress:
        progress.start("logic", "Running logic review")
    logic_findings = logic_review(
        solidity_file=state["solidity_file"],
        triaged_findings=state["triaged"],
        max_issues=1,
    )
    reports_dir = state.get("reports_dir")
    if reports_dir:
        write_json("logic.json", logic_findings, reports_dir)
    if progress:
        progress.complete("logic", f"Logic findings: {len(logic_findings)}")
    return {"logic_findings": logic_findings}


def node_finalize(state: AgentState) -> AgentState:
    triaged = state["triaged"]
    if state.get("logic_findings"):
        triaged = state["logic_findings"] + triaged
    progress = state.get("progress")
    if progress:
        progress.start("finalize", "Building submission")
    submission = build_submission_payload(
        solidity_file=state["solidity_file"],
        findings=state["findings"],
        triaged=triaged,
        static_tools=state["tools"],
        reports_dir=state.get("reports_dir"),
    )
    if progress:
        progress.complete("finalize", "Submission ready")
    return {"submission": submission}


def run_workflow(
    *,
    solidity_file: Path,
    max_issues: int,
    use_llm: bool,
    tools: list[str],
    progress: ProgressReporter | None = None,
    reports_dir: Path | None = None,
) -> Dict:
    try:
        from langgraph.graph import StateGraph
    except ImportError as exc:
        raise RuntimeError(
            "LangGraph is not installed. Install it with: pip install langgraph"
        ) from exc

    graph = StateGraph(AgentState)
    graph.add_node("scan", node_scan)
    graph.add_node("extract", node_extract)
    graph.add_node("triage", node_triage)
    graph.add_node("logic", node_logic)
    graph.add_node("finalize", node_finalize)
    graph.set_entry_point("scan")
    graph.add_edge("scan", "extract")
    graph.add_edge("extract", "triage")
    graph.add_edge("triage", "logic")
    graph.add_edge("logic", "finalize")
    graph.add_edge("finalize", graph.END)

    runnable = graph.compile()
    result = runnable.invoke(
        {
            "solidity_file": solidity_file,
            "max_issues": max_issues,
            "use_llm": use_llm,
            "tools": tools,
            "progress": progress,
            "reports_dir": reports_dir,
        }
    )
    return result["submission"]

