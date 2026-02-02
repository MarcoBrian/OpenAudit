from __future__ import annotations

from pathlib import Path
from typing import Dict, List, TypedDict

from agents.aderyn_runner import run_aderyn
from agents.slither_runner import run_slither
from agents.cli import build_submission_payload
from agents.reporting import write_report
from agents.triage import extract_findings, triage_findings


class AgentState(TypedDict, total=False):
    solidity_file: Path
    max_issues: int
    use_llm: bool
    tools: List[str]
    report_jsons: List[Dict]
    findings: List[Dict]
    triaged: List[Dict]
    submission: Dict


def node_scan(state: AgentState) -> AgentState:
    report_jsons: List[Dict] = []
    reports_dir = Path(__file__).resolve().parent.parent / "reports"
    for tool in state["tools"]:
        if tool == "aderyn":
            report_json = run_aderyn(state["solidity_file"])
            write_report("aderyn", report_json, reports_dir)
            report_jsons.append({"source": "aderyn", "data": report_json})
        elif tool == "slither":
            report_json = run_slither(state["solidity_file"])
            write_report("slither", report_json, reports_dir)
            report_jsons.append({"source": "slither", "data": report_json})
        else:
            raise ValueError(f"Unknown tool: {tool}")
    return {"report_jsons": report_jsons}


def node_extract(state: AgentState) -> AgentState:
    findings: List[Dict] = []
    for report in state["report_jsons"]:
        findings.extend(extract_findings(report["data"], source=report["source"]))
    return {"findings": findings}


def node_triage(state: AgentState) -> AgentState:
    triaged = triage_findings(
        state["findings"],
        max_issues=state["max_issues"],
        use_llm=state["use_llm"],
    )
    return {"triaged": triaged}


def node_finalize(state: AgentState) -> AgentState:
    submission = build_submission_payload(
        solidity_file=state["solidity_file"],
        findings=state["findings"],
        triaged=state["triaged"],
        static_tools=state["tools"],
    )
    return {"submission": submission}


def run_workflow(
    *,
    solidity_file: Path,
    max_issues: int,
    use_llm: bool,
    tools: list[str],
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
    graph.add_node("finalize", node_finalize)
    graph.set_entry_point("scan")
    graph.add_edge("scan", "extract")
    graph.add_edge("extract", "triage")
    graph.add_edge("triage", "finalize")
    graph.add_edge("finalize", graph.END)

    runnable = graph.compile()
    result = runnable.invoke(
        {
            "solidity_file": solidity_file,
            "max_issues": max_issues,
            "use_llm": use_llm,
            "tools": tools,
        }
    )
    return result["submission"]

