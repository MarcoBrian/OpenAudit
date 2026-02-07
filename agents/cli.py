from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from agents.submission import build_submission_payload
from agents.aderyn_runner import AderynError, run_aderyn
from agents.slither_runner import run_slither
from agents.logic import logic_review
from agents.progress import ProgressReporter
from agents.reporting import write_json, write_report
from agents.triage import extract_findings, filter_findings, triage_findings
from agents.graph import run_workflow
from agents.wallet import WalletInitError, get_wallet_details

# Lazy import of langchain_agent - it's slow to import
def _import_langchain_agent():
    """Lazy import to avoid slow LangChain imports when not needed."""
    print("  - Loading agent runtime modules (this may take a few seconds)...", flush=True)
    import_start = time.time()
    from agents.langchain_agent import run_agent
    import_time = time.time() - import_start
    print(f"    Agent runtime loaded ({import_time:.2f}s)", flush=True)
    return run_agent


def _add_common_args(parser: argparse.ArgumentParser) -> None:
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
    parser.add_argument(
        "--reports-dir",
        default="reports",
        help="Directory to read/write intermediate reports",
    )
    parser.add_argument(
        "--dump-intermediate",
        action="store_true",
        help="Write intermediate outputs to reports/ for debugging",
    )


def _add_analysis_args(parser: argparse.ArgumentParser) -> None:
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
    parser.add_argument(
        "--reports-dir",
        default="reports",
        help="Directory to read/write intermediate reports",
    )
    parser.add_argument(
        "--dump-intermediate",
        action="store_true",
        help="Write intermediate outputs to reports/ for debugging",
    )


def _registry_env_default() -> str | None:
    return (
        os.getenv("OPENAUDIT_REGISTRY_ADDRESS")
        or os.getenv("OPENAUDIT_REGISTRY")
        or os.getenv("BOUNTY_HIVE_ADDRESS")
        or os.getenv("BOUNTY_HIVE")
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OpenAudit Agent MVP")
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Run full pipeline (default)")
    _add_common_args(run_parser)

    scan_parser = subparsers.add_parser("scan", help="Run static tools only")
    scan_parser.add_argument("--file", required=True, help="Path to Solidity file")
    scan_parser.add_argument(
        "--tools",
        default="aderyn",
        help="Comma-separated tools to run: aderyn, slither",
    )
    scan_parser.add_argument(
        "--reports-dir",
        default="reports",
        help="Directory to write reports",
    )

    extract_parser = subparsers.add_parser("extract", help="Normalize findings")
    extract_parser.add_argument(
        "--reports-dir",
        default="reports",
        help="Directory containing tool reports",
    )

    triage_parser = subparsers.add_parser("triage", help="Run triage on findings")
    triage_parser.add_argument(
        "--reports-dir",
        default="reports",
        help="Directory containing findings.json",
    )
    triage_parser.add_argument(
        "--max-issues",
        type=int,
        default=2,
        help="Max issues to output in the submission",
    )
    triage_parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Disable LLM triage and use heuristic ranking",
    )

    logic_parser = subparsers.add_parser("logic", help="Run logic review")
    logic_parser.add_argument("--file", required=True, help="Path to Solidity file")
    logic_parser.add_argument(
        "--reports-dir",
        default="reports",
        help="Directory containing triage.json",
    )
    logic_parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Disable LLM logic review",
    )
    logic_parser.add_argument(
        "--max-issues",
        type=int,
        default=1,
        help="Max logic issues to output",
    )

    wallet_parser = subparsers.add_parser("wallet", help="Show AgentKit wallet details")
    wallet_parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw wallet details as JSON",
    )

    agent_parser = subparsers.add_parser("agent", help="Run LangChain agent runtime")
    agent_parser.add_argument(
        "--mode",
        choices=["chat", "auto"],
        default="chat",
        help="Agent runtime mode",
    )
    agent_parser.add_argument(
        "--interval",
        type=int,
        default=10,
        help="Seconds between autonomous actions (auto mode)",
    )
    agent_parser.add_argument(
        "--no-wallet-tools",
        action="store_true",
        help="Disable AgentKit wallet tools",
    )
    agent_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose agent logging",
    )
    agent_parser.add_argument(
        "--system-prompt",
        default=None,
        help="Override the default agent system prompt",
    )

    bounty_parser = subparsers.add_parser(
        "bounty", help="Query bounties and analyze targets"
    )
    bounty_subparsers = bounty_parser.add_subparsers(dest="bounty_command")

    bounty_list = bounty_subparsers.add_parser(
        "list", help="List bounties from OpenAuditRegistry"
    )
    bounty_list.add_argument(
        "--rpc-url",
        default=os.getenv("RPC_URL"),
        help="RPC URL for the chain (env: RPC_URL)",
    )
    bounty_list.add_argument(
        "--registry",
        "--registry-address",
        "--bounty-hive",
        dest="registry_address",
        default=_registry_env_default(),
        help=(
            "OpenAuditRegistry address (env: OPENAUDIT_REGISTRY_ADDRESS; "
            "legacy: BOUNTY_HIVE)"
        ),
    )
    bounty_list.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Max number of bounties to list",
    )

    bounty_analyze = bounty_subparsers.add_parser(
        "analyze", help="Analyze a bounty target contract"
    )
    bounty_analyze.add_argument(
        "--rpc-url",
        default=os.getenv("RPC_URL"),
        help="RPC URL for the chain (env: RPC_URL)",
    )
    bounty_analyze.add_argument(
        "--registry",
        "--registry-address",
        "--bounty-hive",
        dest="registry_address",
        default=_registry_env_default(),
        help=(
            "OpenAuditRegistry address (env: OPENAUDIT_REGISTRY_ADDRESS; "
            "legacy: BOUNTY_HIVE)"
        ),
    )
    bounty_analyze.add_argument(
        "--bounty-id",
        type=int,
        required=True,
        help="Bounty ID to analyze",
    )
    bounty_analyze.add_argument(
        "--source-map",
        default=os.getenv("BOUNTY_SOURCE_MAP"),
        help="Path to JSON mapping of target address to Solidity file path",
    )
    bounty_analyze.add_argument(
        "--use-etherscan",
        action="store_true",
        help="Fetch source from an Etherscan-compatible API",
    )
    _add_analysis_args(bounty_analyze)

    bounty_submit = bounty_subparsers.add_parser(
        "submit", help="Submit a bounty finding"
    )
    bounty_submit.add_argument(
        "--rpc-url",
        default=os.getenv("RPC_URL"),
        help="RPC URL for the chain (env: RPC_URL)",
    )
    bounty_submit.add_argument(
        "--registry",
        "--registry-address",
        "--bounty-hive",
        dest="registry_address",
        default=_registry_env_default(),
        help=(
            "OpenAuditRegistry address (env: OPENAUDIT_REGISTRY_ADDRESS; "
            "legacy: BOUNTY_HIVE)"
        ),
    )
    bounty_submit.add_argument(
        "--private-key",
        default=os.getenv("BOUNTY_SUBMITTER_PRIVATE_KEY"),
        help="Private key for the submitter wallet (env: BOUNTY_SUBMITTER_PRIVATE_KEY)",
    )
    bounty_submit.add_argument(
        "--bounty-id",
        type=int,
        required=True,
        help="Bounty ID to submit against",
    )
    bounty_submit.add_argument(
        "--report-cid",
        required=True,
        help="Report CID (e.g. IPFS CID)",
    )
    bounty_submit.add_argument(
        "--submitter",
        default=None,
        help="Optional: expected submitter address (sanity check)",
    )

    return parser


def run_linear(
    *,
    solidity_file: Path,
    max_issues: int,
    use_llm: bool,
    tools: list[str],
    dump_intermediate: bool,
    reports_dir: Path,
    progress: ProgressReporter | None = None,
) -> dict:
    findings: list[dict] = []
    tools_used: list[str] = []
    for tool in tools:
        if tool == "aderyn":
            if progress:
                progress.start("scan.aderyn", "Running Aderyn")
            try:
                report_json = run_aderyn(solidity_file)
            except AderynError as exc:
                if progress:
                    progress.complete(
                        "scan.aderyn",
                        "Aderyn failed; continuing with remaining tools",
                    )
                else:
                    print(
                        f"warning: aderyn failed; continuing ({exc})",
                        file=sys.stderr,
                    )
                continue
            write_report("aderyn", report_json, reports_dir)
            findings.extend(extract_findings(report_json, source="aderyn"))
            tools_used.append("aderyn")
            if progress:
                progress.complete("scan.aderyn", "Aderyn report ready")
        elif tool == "slither":
            if progress:
                progress.start("scan.slither", "Running Slither")
            report_json = run_slither(solidity_file)
            write_report("slither", report_json, reports_dir)
            findings.extend(extract_findings(report_json, source="slither"))
            tools_used.append("slither")
            if progress:
                progress.complete("scan.slither", "Slither report ready")
        else:
            raise ValueError(f"Unknown tool: {tool}")
    filtered = filter_findings(findings)
    if progress:
        progress.start("extract", "Normalizing findings")
        dropped = len(findings) - len(filtered)
        suffix = f", filtered {dropped}" if dropped > 0 else ""
        progress.complete(
            "extract",
            f"Extracted {len(findings)} findings{suffix}",
        )
        progress.start("triage", "Ranking findings")
    triaged = triage_findings(filtered, max_issues=max_issues, use_llm=use_llm)
    if progress:
        progress.complete("triage", f"Selected {len(triaged)} findings")
    if dump_intermediate:
        write_json("static_analysis_summary.json", filtered, reports_dir)
        write_json("triage.json", triaged, reports_dir)
    api_key = os.getenv("OPENAI_API_KEY")
    ollama_model = os.getenv("OLLAMA_MODEL")
    if use_llm and (api_key or ollama_model):
        if progress:
            progress.start("logic", "Running logic review")
        logic_findings = logic_review(
            solidity_file=solidity_file,
            triaged_findings=triaged,
            max_issues=1,
        )
        if dump_intermediate:
            write_json("logic.json", logic_findings, reports_dir)
        if logic_findings:
            triaged = logic_findings + triaged
        if progress:
            progress.complete("logic", f"Logic findings: {len(logic_findings)}")
    else:
        if progress:
            progress.complete("logic", "Logic review skipped (LLM not configured)")
    if progress:
        progress.start("finalize", "Building submission")
    submission = build_submission_payload(
        solidity_file=solidity_file,
        findings=filtered,
        triaged=triaged,
        static_tools=tools_used,
        reports_dir=reports_dir if dump_intermediate else None,
    )
    if progress:
        progress.complete("finalize", "Submission ready")
    return submission


def run_graph(
    *,
    solidity_file: Path,
    max_issues: int,
    use_llm: bool,
    tools: list[str],
    progress: ProgressReporter | None = None,
    reports_dir: Path | None = None,
) -> dict:
    return run_workflow(
        solidity_file=solidity_file,
        max_issues=max_issues,
        use_llm=use_llm,
        tools=tools,
        progress=progress,
        reports_dir=reports_dir,
    )


def main() -> int:
    import time
    start_time = time.time()
    
    print("Starting OpenAudit agent...", flush=True)
    
    try:
        load_dotenv(override=False)  # Don't override existing env vars
    except Exception as exc:
        # Handle .env parsing errors gracefully
        # This can happen if .env has syntax errors or variable resolution issues
        print(f"Warning: Could not parse .env file: {exc}", file=sys.stderr)
        print("Continuing - environment variables may be set via system or command line.", file=sys.stderr)
    
    args = build_parser().parse_args()
    command = args.command or "run"
    
    if command == "agent":
        # For agent command, we know we'll need langchain - print early
        print("Loading agent runtime (this may take a few seconds)...", flush=True)

    if command == "scan":
        solidity_file = Path(args.file)
        tools = [tool.strip().lower() for tool in args.tools.split(",") if tool.strip()]
        reports_dir = Path(args.reports_dir)
        for tool in tools:
            if tool == "aderyn":
                report_json = run_aderyn(solidity_file)
                write_report("aderyn", report_json, reports_dir)
            elif tool == "slither":
                report_json = run_slither(solidity_file)
                write_report("slither", report_json, reports_dir)
            else:
                raise ValueError(f"Unknown tool: {tool}")
        return 0

    if command == "extract":
        reports_dir = Path(args.reports_dir)
        findings: list[dict] = []
        aderyn_path = reports_dir / "aderyn_report.json"
        slither_path = reports_dir / "slither_report.json"
        if aderyn_path.exists():
            findings.extend(
                extract_findings(
                    json.loads(aderyn_path.read_text(encoding="utf-8")),
                    source="aderyn",
                )
            )
        if slither_path.exists():
            findings.extend(
                extract_findings(
                    json.loads(slither_path.read_text(encoding="utf-8")),
                    source="slither",
                )
            )
        write_json("static_analysis_summary.json", findings, reports_dir)
        return 0

    if command == "triage":
        reports_dir = Path(args.reports_dir)
        findings_path = reports_dir / "static_analysis_summary.json"
        findings = json.loads(findings_path.read_text(encoding="utf-8"))
        triaged = triage_findings(
            findings,
            max_issues=args.max_issues,
            use_llm=not args.no_llm,
        )
        write_json("triage.json", triaged, reports_dir)
        return 0

    if command == "logic":
        reports_dir = Path(args.reports_dir)
        triage_path = reports_dir / "triage.json"
        triaged = json.loads(triage_path.read_text(encoding="utf-8"))
        logic_findings = logic_review(
            solidity_file=Path(args.file),
            triaged_findings=triaged,
            max_issues=args.max_issues,
        ) if not args.no_llm else []
        write_json("logic.json", logic_findings, reports_dir)
        return 0

    if command == "wallet":
        try:
            details = get_wallet_details()
        except WalletInitError as exc:
            print(f"Wallet init failed: {exc}")
            return 1
        payload = details.raw if args.json else details.to_dict()
        print(json.dumps(payload, indent=2))
        return 0

    if command == "agent":
        # Lazy import - only load langchain_agent when actually needed
        run_agent = _import_langchain_agent()
        return run_agent(
            mode=args.mode,
            include_wallet_tools=not args.no_wallet_tools,
            interval=args.interval,
            verbose=args.verbose,
            system_prompt=args.system_prompt,
        )

    if command == "bounty":
        from agents.bounty_discovery import (
            RegistryClient,
            load_source_from_etherscan,
            load_source_from_map,
        )
        from agents.bounty_submission import BountySubmissionClient

        registry_address = args.registry_address
        if not registry_address:
            raise ValueError(
                "Provide --registry-address or set OPENAUDIT_REGISTRY_ADDRESS."
            )

        if args.bounty_command == "list":
            client = RegistryClient(args.rpc_url, registry_address)
            total = client.total_bounties()
            limit = min(total, args.limit)
            payload = []
            for bounty_id in range(1, limit + 1):
                bounty = client.get_bounty(bounty_id)
                payload.append(bounty.__dict__)
            print(json.dumps({"total": total, "bounties": payload}, indent=2))
            return 0

        if args.bounty_command == "analyze":
            client = RegistryClient(args.rpc_url, registry_address)
            bounty = client.get_bounty(args.bounty_id)
            if args.use_etherscan:
                solidity_file = load_source_from_etherscan(bounty.target_contract)
            elif args.source_map:
                solidity_file = load_source_from_map(
                    bounty.target_contract,
                    Path(args.source_map),
                )
            else:
                raise ValueError(
                    "Provide --source-map or enable --use-etherscan to fetch source."
                )

            tools = [tool.strip().lower() for tool in args.tools.split(",") if tool.strip()]
            reports_dir = Path(args.reports_dir)
            if args.use_graph:
                output = run_graph(
                    solidity_file=solidity_file,
                    max_issues=args.max_issues,
                    use_llm=not args.no_llm,
                    tools=tools,
                    reports_dir=reports_dir,
                )
            else:
                output = run_linear(
                    solidity_file=solidity_file,
                    max_issues=args.max_issues,
                    use_llm=not args.no_llm,
                    tools=tools,
                    dump_intermediate=args.dump_intermediate,
                    reports_dir=reports_dir,
                )

            Path(args.out).write_text(json.dumps(output, indent=2), encoding="utf-8")
            return 0

        if args.bounty_command == "submit":
            if not args.private_key:
                raise ValueError(
                    "Provide --private-key or set BOUNTY_SUBMITTER_PRIVATE_KEY."
                )
            submitter_client = BountySubmissionClient(args.rpc_url, registry_address)
            derived_address = submitter_client.web3.eth.account.from_key(
                args.private_key
            ).address
            if args.submitter and args.submitter.lower() != derived_address.lower():
                raise ValueError(
                    "Submitter address does not match provided private key."
                )
            tx_hash = submitter_client.submit_finding(
                private_key=args.private_key,
                bounty_id=args.bounty_id,
                report_cid=args.report_cid,
            )
            payload = {
                "submitter": derived_address,
                "submit_tx": tx_hash,
            }
            print(json.dumps(payload, indent=2))
            return 0

        raise ValueError("Missing bounty subcommand (list/analyze/submit).")

    solidity_file = Path(args.file)
    tools = [tool.strip().lower() for tool in args.tools.split(",") if tool.strip()]
    reports_dir = Path(args.reports_dir)

    if args.use_graph:
        output = run_graph(
            solidity_file=solidity_file,
            max_issues=args.max_issues,
            use_llm=not args.no_llm,
            tools=tools,
            reports_dir=reports_dir,
        )
    else:
        output = run_linear(
            solidity_file=solidity_file,
            max_issues=args.max_issues,
            use_llm=not args.no_llm,
            tools=tools,
            dump_intermediate=args.dump_intermediate,
            reports_dir=reports_dir,
        )

    Path(args.out).write_text(json.dumps(output, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
