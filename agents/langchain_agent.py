from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv

try:
    # LangChain v1.0+ uses create_agent instead of create_react_agent
    try:
        from langchain.agents import create_agent
        _USE_NEW_API = True
    except ImportError:
        # Fallback to older API if available
        try:
            from langchain.agents import AgentExecutor, create_react_agent
            _USE_NEW_API = False
        except ImportError:
            # Try langgraph.prebuilt for older versions
            from langgraph.prebuilt import create_react_agent
            from langchain.agents import AgentExecutor
            _USE_NEW_API = False
    
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.tools import BaseTool, tool
    from langchain_openai import ChatOpenAI
    from langchain_community.chat_models import ChatOllama
    
    # AgentExecutor might not be needed in new API
    if _USE_NEW_API:
        AgentExecutor = None  # type: ignore[assignment]
        create_react_agent = None  # type: ignore[assignment]
    else:
        # Ensure AgentExecutor is defined for old API
        if 'AgentExecutor' not in locals():
            AgentExecutor = None  # type: ignore[assignment]
    
    _LANGCHAIN_IMPORT_ERROR = None
except ImportError as exc:  # pragma: no cover - optional dependency
    AgentExecutor = None  # type: ignore[assignment]
    create_react_agent = None  # type: ignore[assignment]
    create_agent = None  # type: ignore[assignment]
    _USE_NEW_API = False
    HumanMessage = None  # type: ignore[assignment]
    SystemMessage = None  # type: ignore[assignment]
    ChatPromptTemplate = None  # type: ignore[assignment]
    BaseTool = None  # type: ignore[assignment]
    tool = None  # type: ignore[assignment]
    ChatOpenAI = None  # type: ignore[assignment]
    ChatOllama = None  # type: ignore[assignment]
    _LANGCHAIN_IMPORT_ERROR = exc

from agents.aderyn_runner import AderynError, run_aderyn
from agents.logic import logic_review
from agents.progress import ProgressReporter
from agents.reporting import write_json, write_report
from agents.slither_runner import run_slither
from agents.submission import build_submission_payload
from agents.triage import extract_findings, filter_findings, triage_findings
from agents.wallet import WalletInitError, create_agentkit


class AgentRuntimeError(RuntimeError):
    pass


def _require_langchain() -> None:
    if _LANGCHAIN_IMPORT_ERROR is not None:
        raise AgentRuntimeError(
            "LangChain dependencies are not installed. "
            "Install them with: pip install langchain langchain-openai langchain-community"
        ) from _LANGCHAIN_IMPORT_ERROR


def _build_llm() -> Any:
    _require_langchain()
    openai_key = os.getenv("OPENAI_API_KEY")
    openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    openai_base_url = os.getenv("OPENAI_BASE_URL")
    if openai_key:
        return ChatOpenAI(
            model=openai_model,
            api_key=openai_key,
            base_url=openai_base_url,
            temperature=0.2,
        )

    ollama_model = os.getenv("OLLAMA_MODEL")
    if ollama_model:
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        return ChatOllama(model=ollama_model, base_url=base_url, temperature=0.2)

    raise AgentRuntimeError(
        "No LLM configured. Set OPENAI_API_KEY or OLLAMA_MODEL to run the LangChain agent."
    )


def _parse_tools(tools: str | List[str]) -> List[str]:
    if isinstance(tools, list):
        return [tool.strip().lower() for tool in tools if tool.strip()]
    return [tool.strip().lower() for tool in tools.split(",") if tool.strip()]


def _run_pipeline(
    *,
    solidity_file: Path,
    tools: List[str],
    max_issues: int,
    use_llm: bool,
    dump_intermediate: bool,
    reports_dir: Path,
    progress: ProgressReporter | None = None,
) -> dict:
    findings: list[dict] = []
    tools_used: list[str] = []

    def _start(step: str, message: str) -> float:
        if progress is not None:
            progress.start(step, message)
        print(f"[audit] {message}...", flush=True)
        return time.perf_counter()

    def _finish(step: str, message: str, start_time: float) -> None:
        duration = time.perf_counter() - start_time
        if progress is not None:
            progress.complete(step, f"{message} ({duration:.1f}s)")
        print(f"[audit] {message} ({duration:.1f}s)", flush=True)

    print(f"[audit] Starting audit for {solidity_file}", flush=True)

    for tool_name in tools:
        if tool_name == "aderyn":
            start = _start("scan.aderyn", "Running Aderyn")
            try:
                report_json = run_aderyn(solidity_file)
            except AderynError as exc:
                if progress is not None:
                    progress.fail("scan.aderyn", str(exc))
                print(f"warning: aderyn failed; continuing ({exc})", file=sys.stderr)
                continue
            write_report("aderyn", report_json, reports_dir)
            findings.extend(extract_findings(report_json, source="aderyn"))
            tools_used.append("aderyn")
            _finish("scan.aderyn", "Aderyn complete", start)
        elif tool_name == "slither":
            start = _start("scan.slither", "Running Slither")
            report_json = run_slither(solidity_file)
            write_report("slither", report_json, reports_dir)
            findings.extend(extract_findings(report_json, source="slither"))
            tools_used.append("slither")
            _finish("scan.slither", "Slither complete", start)
        else:
            raise ValueError(f"Unknown tool: {tool_name}")

    start = _start("triage", "Triaging findings")
    filtered = filter_findings(findings)
    triaged = triage_findings(filtered, max_issues=max_issues, use_llm=use_llm)
    _finish("triage", "Triaging complete", start)

    if dump_intermediate:
        write_json("static_analysis_summary.json", filtered, reports_dir)
        write_json("triage.json", triaged, reports_dir)

    api_key = os.getenv("OPENAI_API_KEY")
    ollama_model = os.getenv("OLLAMA_MODEL")
    if use_llm and (api_key or ollama_model):
        start = _start("logic", "Running logic review")
        logic_findings = logic_review(
            solidity_file=solidity_file,
            triaged_findings=triaged,
            max_issues=1,
        )
        _finish("logic", "Logic review complete", start)
        if dump_intermediate:
            write_json("logic.json", logic_findings, reports_dir)
        if logic_findings:
            triaged = logic_findings + triaged

    start = _start("submission", "Building submission payload")
    submission = build_submission_payload(
        solidity_file=solidity_file,
        findings=filtered,
        triaged=triaged,
        static_tools=tools_used,
        reports_dir=reports_dir if dump_intermediate else None,
    )
    _finish("submission", "Submission ready", start)
    return submission


if tool is None:
    def run_audit() -> str:  # type: ignore[override]
        raise AgentRuntimeError("LangChain tools are unavailable.")
else:
    @tool("run_audit")
    def run_audit(
        file: str,
        tools: str = "aderyn,slither",
        max_issues: int = 2,
        use_llm: bool = True,
        dump_intermediate: bool = True,
        reports_dir: str = "reports",
    ) -> str:
        """Run the OpenAudit pipeline on a Solidity file and return submission JSON."""
        def _extract_json(text: str) -> Dict[str, Any]:
            try:
                parsed = json.loads(text)
                return parsed if isinstance(parsed, dict) else {}
            except json.JSONDecodeError:
                pass
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                snippet = text[start : end + 1]
                try:
                    parsed = json.loads(snippet)
                    return parsed if isinstance(parsed, dict) else {}
                except json.JSONDecodeError:
                    return {}
            return {}

        if isinstance(file, dict):
            payload = file
        else:
            payload = _extract_json(str(file))

        if payload:
            file = payload.get("file", file)
            tools = payload.get("tools", tools)
            max_issues = int(payload.get("max_issues", max_issues))
            use_llm = bool(payload.get("use_llm", use_llm))
            dump_intermediate = bool(payload.get("dump_intermediate", dump_intermediate))
            reports_dir = payload.get("reports_dir", reports_dir)

        try:
            target = Path(str(file))
            if not target.exists():
                return f"error: Solidity file not found: {file}"
        except OSError as exc:
            return f"error: invalid file path: {exc}"

        submission = _run_pipeline(
            solidity_file=target,
            tools=_parse_tools(tools),
            max_issues=max_issues,
            use_llm=use_llm,
            dump_intermediate=dump_intermediate,
            reports_dir=Path(reports_dir),
            progress=ProgressReporter(Path(reports_dir)) if dump_intermediate else None,
        )
        return json.dumps(submission, indent=2)


def _build_tools(include_wallet_tools: bool) -> List[BaseTool]:
    _require_langchain()
    tools: List[BaseTool] = [run_audit]

    if not include_wallet_tools:
        return tools

    try:
        # Lazy import to avoid importing coinbase_agentkit_langchain (and its
        # nest_asyncio side effects) when wallet tools are not needed.
        from coinbase_agentkit_langchain import get_langchain_tools

        agentkit = create_agentkit()
    except WalletInitError as exc:
        print(f"warning: wallet disabled ({exc})", file=sys.stderr)
        return tools
    except ImportError as exc:
        raise AgentRuntimeError(
            "coinbase-agentkit-langchain is not installed. "
            "Install it with: pip install coinbase-agentkit-langchain"
        ) from exc

    tools.extend(get_langchain_tools(agentkit))
    return tools


def _build_prompt(system_prompt: str | None = None) -> ChatPromptTemplate:
    _require_langchain()
    base_prompt = system_prompt or (
        "You are OpenAudit's autonomous agent. "
        "Use the run_audit tool to analyze Solidity files and produce a JSON submission. "
        "Only use wallet tools when explicitly requested. "
        "Keep responses concise and actionable."
    )
    tool_instructions = (
        "You have access to the following tools:\n{tools}\n\n"
        "Tool names: {tool_names}\n\n"
        "When calling a tool, the Action Input must be a strict JSON object with keys: "
        "file, tools, max_issues, use_llm, dump_intermediate, reports_dir. "
        "Do not include any extra text or formatting in Action Input.\n\n"
        "Use the following format:\n"
        "Thought: your reasoning\n"
        "Action: the tool name to use\n"
        "Action Input: the input to the tool\n"
        "Observation: the tool result\n"
        "Final: your response to the user\n"
        "If no tool is needed, skip Action/Observation and respond with Final only.\n"
    )
    return ChatPromptTemplate.from_messages(
        [
            ("system", f"{base_prompt}\n\n{tool_instructions}"),
            ("human", "{input}"),
            ("assistant", "{agent_scratchpad}"),
        ]
    )


def create_agent_executor(
    *,
    include_wallet_tools: bool,
    system_prompt: str | None = None,
    verbose: bool = False,
) -> Any:
    _require_langchain()
    llm = _build_llm()
    tools = _build_tools(include_wallet_tools)
    
    if _USE_NEW_API:
        # LangChain v1.0+ API: create_agent returns a directly invokable agent
        base_prompt = system_prompt or (
            "You are OpenAudit's autonomous agent. "
            "Use the run_audit tool to analyze Solidity files and produce a JSON submission. "
            "Only use wallet tools when explicitly requested. "
            "Keep responses concise and actionable."
        )
        agent = create_agent(
            model=llm,
            tools=tools,
            system_prompt=base_prompt,
        )
        return agent
    else:
        # Old API: use create_react_agent with AgentExecutor
        if create_react_agent is None or AgentExecutor is None:
            raise AgentRuntimeError(
                "LangChain agent creation functions are unavailable. "
                "Install compatible LangChain version."
            )
        prompt = _build_prompt(system_prompt)
        agent = create_react_agent(llm, tools, prompt)
        return AgentExecutor(
            agent=agent,
            tools=tools,
            verbose=verbose,
            handle_parsing_errors=True,
            max_iterations=4,
            max_execution_time=60,
            early_stopping_method="force",
        )


def run_chat_mode(agent_executor: Any, system_prompt: str | None = None) -> int:
    if HumanMessage is None:
        raise AgentRuntimeError("LangChain message classes are unavailable.")
    if SystemMessage is None:
        raise AgentRuntimeError("LangChain message classes are unavailable.")

    chat_llm: Any | None = None

    def _ensure_chat_llm() -> Any:
        nonlocal chat_llm
        if chat_llm is None:
            chat_llm = _build_llm()
        return chat_llm

    def _chat_system_prompt() -> str:
        base_prompt = system_prompt or (
            "You are OpenAudit's assistant focused on Solidity security audits. "
            "Answer audit-related questions concisely and help users run audits. "
            "If a request is not about auditing Solidity contracts, refuse briefly and ask "
            "for an audit-related question."
        )
        return (
            f"{base_prompt}\n\n"
            "Only discuss audit topics: Solidity, audit workflow, findings, vulnerabilities, "
            "static analysis tools, triage, and report interpretation. "
            "If asked about unrelated topics, respond with a brief refusal. "
            "Respond in plain text. Do not use tool-calling formats unless explicitly asked."
        )

    def _looks_like_audit_request(text: str) -> bool:
        cleaned = text.strip().lower()
        if not cleaned:
            return False
        if "run_audit" in cleaned:
            return True
        if ".sol" in cleaned:
            return True
        return False

    def _is_audit_topic(text: str) -> bool:
        cleaned = text.strip().lower()
        if not cleaned:
            return False
        if _looks_like_audit_request(cleaned):
            return True
        meta_phrases = {
            "purpose",
            "what can you do",
            "what do you do",
            "capabilities",
            "help",
            "how do i use",
            "how to use",
            "usage",
            "commands",
            "agent",
            "openaudit",
            "hi",
            "hello",
            "hey",
            "hey there",
            "yo",
            "hola",
            "sup",
            "good morning",
            "good afternoon",
            "good evening",
        }
        if any(phrase in cleaned for phrase in meta_phrases):
            return True
        audit_keywords = {
            "audit",
            "auditing",
            "solidity",
            "smart contract",
            "contract",
            "vulnerability",
            "reentrancy",
            "access control",
            "overflow",
            "underflow",
            "gas",
            "slither",
            "aderyn",
            "triage",
            "finding",
            "findings",
            "logic review",
            "static analysis",
            "invariant",
            "exploit",
            "security",
            "openaudit",
            "pipeline",
            "report",
            "severity",
            "confidence",
            "solc",
            "foundry",
            "hardhat",
            "ethers",
            "viem",
        }
        return any(keyword in cleaned for keyword in audit_keywords)

    def _parse_bool(value: str, default: bool) -> bool:
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y", "on"}:
            return True
        if normalized in {"false", "0", "no", "n", "off"}:
            return False
        return default

    def _extract_audit_params(text: str) -> Dict[str, Any]:
        cleaned = text.strip().strip("`")
        params: Dict[str, Any] = {}

        if cleaned.startswith("run_audit"):
            cleaned = cleaned[len("run_audit") :].strip()

        if cleaned.startswith("{") and cleaned.endswith("}"):
            try:
                payload = json.loads(cleaned)
                if isinstance(payload, dict):
                    return payload
            except json.JSONDecodeError:
                pass

        for token in cleaned.split():
            if "=" in token:
                key, value = token.split("=", 1)
                params[key.strip()] = value.strip().strip("`\"'")

        file_match = params.get("file")
        if not file_match:
            match = re.search(r"([\\w./\\-\\\\]+\\.sol)", cleaned)
            if match:
                file_match = match.group(1)
                params["file"] = file_match
            else:
                for token in cleaned.split():
                    if ".sol" in token:
                        params["file"] = token.strip("`\"'")
                        break

        return params

    print("Starting chat mode. Type 'exit' to quit.")
    while True:
        try:
            user_input = input("\nPrompt: ").strip()
            if user_input.lower() in {"exit", "quit"}:
                return 0

            if _looks_like_audit_request(user_input):
                params = _extract_audit_params(user_input)
                file_value = params.get("file")
                if not file_value:
                    print(
                        "Please provide a Solidity file path, e.g. "
                        "`run_audit file=sample_contracts/CoinFlip.sol`."
                    )
                    continue
                tools_value = params.get("tools", "aderyn,slither")
                max_issues_value = int(params.get("max_issues", 2))
                use_llm_value = _parse_bool(str(params.get("use_llm", True)), True)
                dump_value = _parse_bool(str(params.get("dump_intermediate", True)), True)
                reports_value = params.get("reports_dir", "reports")

                try:
                    submission = _run_pipeline(
                        solidity_file=Path(str(file_value)),
                        tools=_parse_tools(tools_value),
                        max_issues=max_issues_value,
                        use_llm=use_llm_value,
                        dump_intermediate=dump_value,
                        reports_dir=Path(str(reports_value)),
                        progress=ProgressReporter(Path(str(reports_value))) if dump_value else None,
                    )
                except Exception as exc:
                    print(f"error: failed to run audit ({exc})")
                    continue

                print(json.dumps(submission, indent=2))
                continue

            if not _looks_like_audit_request(user_input):
                if not _is_audit_topic(user_input):
                    print(
                        "I can only help with Solidity audit topics. "
                        "Ask about auditing a contract or provide a `.sol` file."
                    )
                    continue
                llm = _ensure_chat_llm()
                try:
                    response = llm.invoke(
                        [
                            SystemMessage(content=_chat_system_prompt()),
                            HumanMessage(content=user_input),
                        ]
                    )
                    output = response.content if hasattr(response, "content") else str(response)
                except Exception as exc:
                    output = (
                        "I can run audits. Provide a Solidity file path, or use "
                        "`run_audit file=sample_contracts/CoinFlip.sol`."
                    )
                    print(f"warning: LLM chat failed ({exc})", file=sys.stderr)
                print(output)
                continue
            
            # Handle both old (AgentExecutor) and new (direct agent) APIs
            if _USE_NEW_API:
                # New API: invoke with messages
                result = agent_executor.invoke({"messages": [HumanMessage(content=user_input)]})
                # New API returns messages, extract content
                if isinstance(result, dict) and "messages" in result:
                    messages = result["messages"]
                    if messages and hasattr(messages[-1], "content"):
                        output = messages[-1].content
                    else:
                        output = str(result)
                else:
                    output = str(result)
            else:
                # Old API: invoke with input dict
                result = agent_executor.invoke({"input": user_input})
                output = result.get("output") if isinstance(result, dict) else result
            
            if output:
                output_text = str(output)
                if (
                    "Agent stopped due to iteration limit" in output_text
                    or "iteration limit" in output_text
                    or "time limit" in output_text
                ):
                    output = (
                        "I can help run audits. Provide a Solidity file path, e.g. "
                        "`run_audit file=sample_contracts/CoinFlip.sol`."
                    )
                print(output)
        except EOFError:
            print("Goodbye.")
            return 0
        except KeyboardInterrupt:
            print("Goodbye.")
            return 0


def run_autonomous_mode(agent_executor: Any, interval: int) -> int:
    if HumanMessage is None:
        raise AgentRuntimeError("LangChain message classes are unavailable.")

    print("Starting autonomous mode. Press Ctrl+C to stop.")
    while True:
        try:
            thought = (
                "Review the latest Solidity file in the repository and run an audit. "
                "If no file is specified, ask for one."
            )
            
            # Handle both old (AgentExecutor) and new (direct agent) APIs
            if _USE_NEW_API:
                # New API: invoke with messages
                result = agent_executor.invoke({"messages": [HumanMessage(content=thought)]})
                # New API returns messages, extract content
                if isinstance(result, dict) and "messages" in result:
                    messages = result["messages"]
                    if messages and hasattr(messages[-1], "content"):
                        output = messages[-1].content
                    else:
                        output = str(result)
                else:
                    output = str(result)
            else:
                # Old API: invoke with input dict
                result = agent_executor.invoke({"input": thought})
                output = result.get("output") if isinstance(result, dict) else result
            
            if output:
                print(output)
            time.sleep(max(1, interval))
        except KeyboardInterrupt:
            print("Goodbye.")
            return 0


def run_agent(
    *,
    mode: str,
    include_wallet_tools: bool,
    interval: int,
    verbose: bool,
    system_prompt: str | None,
) -> int:
    load_dotenv()
    agent_executor = create_agent_executor(
        include_wallet_tools=include_wallet_tools,
        system_prompt=system_prompt,
        verbose=verbose,
    )
    if mode == "auto":
        return run_autonomous_mode(agent_executor, interval)
    return run_chat_mode(agent_executor, system_prompt=system_prompt)
