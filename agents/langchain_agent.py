from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, TypedDict

from dotenv import load_dotenv

# Track if we're loading for agent mode (check sys.argv early)
_is_agent_mode = len(sys.argv) > 1 and "agent" in sys.argv

if _is_agent_mode:
    print("  - Importing LangChain (this may take a moment)...", flush=True)
    import_start = time.time()

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
    if _is_agent_mode:
        import_time = time.time() - import_start
        print(f"    LangChain imported ({import_time:.2f}s)", flush=True)
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

if _is_agent_mode:
    print("  - Importing agent modules...", flush=True)
    module_start = time.time()

from agents.aderyn_runner import AderynError, run_aderyn
from agents.logic import logic_review
from agents.progress import ProgressReporter
from agents.reporting import write_json, write_report
from agents.slither_runner import run_slither
from agents.submission import build_submission_payload
from agents.triage import extract_findings, filter_findings, triage_findings
from agents.wallet import WalletInitError, create_agentkit

if _is_agent_mode:
    module_time = time.time() - module_start
    print(f"    Agent modules imported ({module_time:.2f}s)", flush=True)

try:
    if _is_agent_mode:
        print("  - Importing web3...", flush=True)
        web3_start = time.time()
    from web3 import Web3  # type: ignore
    from web3.exceptions import ContractLogicError  # type: ignore
    if _is_agent_mode:
        web3_time = time.time() - web3_start
        print(f"    web3 imported ({web3_time:.2f}s)", flush=True)
except ImportError as exc:  # pragma: no cover - optional dependency
    Web3 = None  # type: ignore[assignment]
    ContractLogicError = Exception  # type: ignore[assignment]
    _WEB3_IMPORT_ERROR = exc
else:
    _WEB3_IMPORT_ERROR = None


class AgentRuntimeError(RuntimeError):
    pass


DEFAULT_AGENT_SYSTEM_PROMPT = (
    "You are OpenAudit's autonomous agent (the agent itself, not a third-party service). "
    "You must register yourself in the OpenAuditRegistry to submit bounties and earn rewards. "
    "IMPORTANT: When users ask to register the agent, you MUST use the register_agent tool. "
    "Do not just explain how to register - actually call the tool.\n\n"
    "Available tools:\n"
    "1. run_audit - Analyze Solidity files and produce JSON submissions\n"
    "2. register_agent - Register this agent in the OpenAuditRegistry (USE THIS when asked to register)\n"
    "3. check_registration - Verify if an agent is registered\n"
    "4. Wallet tools - Only use when explicitly requested\n\n"
    "Examples:\n"
    "- User: 'Register this agent' → Use register_agent tool\n"
    "- User: 'Register me' → Use register_agent tool\n"
    "- User: 'Sign up the agent' → Use register_agent tool\n"
    "- User: 'Check if I'm registered' → Use check_registration tool\n"
    "- User: 'How do I submit a bounty?' → Explain that registration is required and offer to register now\n"
    "Keep responses concise and actionable. Always use tools when appropriate."
)

DEFAULT_CHAT_SYSTEM_PROMPT = (
    "You are the OpenAudit agent. You are responsible for self-registering and "
    "self-checking your registration in the OpenAuditRegistry so you can submit bounties and earn rewards. "
    "You can run Solidity audits using Aderyn and Slither, triage findings, optionally perform an LLM "
    "logic review, and produce a JSON submission. "
    "If the user asks about bounties, rewards, or submissions, state clearly that you (the agent) must be "
    "registered first and offer to register yourself. "
    "Be clear, concise, and actionable. When the user asks for an action, "
    "the system will execute tools separately, so focus on guidance and missing inputs."
)

_INFO_PHRASES = (
    "what can you do",
    "what do you do",
    "what does",
    "how do",
    "how to",
    "why",
    "explain",
    "describe",
    "overview",
    "intro",
    "introduction",
    "usage",
    "commands",
    "capabilities",
    "docs",
    "documentation",
    "purpose",
)

_REGISTER_ACTION_PHRASES = (
    "register this agent",
    "register the agent",
    "register me",
    "register agent",
    "register yourself",
    "sign up the agent",
    "sign up",
    "sign-up",
    "enroll",
    "create an agent registration",
)

_CHECK_ACTION_PHRASES = (
    "check registration",
    "check if i'm registered",
    "check if i am registered",
    "am i registered",
    "are we registered",
    "registration status",
    "check_registration",
    "verify registration",
    "is this agent registered",
)

_AUDIT_ACTION_PHRASES = (
    "run audit",
    "run_audit",
    "audit this",
    "audit the contract",
    "audit contract",
    "scan contract",
    "analyze contract",
    "review contract",
)

_AUDIT_CONTEXT_HINTS = ("contract", "solidity", "smart contract", ".sol")

_REGISTER_CONTEXT_HINTS = ("agent", "registry", "openaudit", "tba", "ens")

_INTENT_ROUTER_PROMPT = (
    "You are a routing classifier for the OpenAudit agent. Decide whether the user is asking to "
    "perform an action right now. Return strict JSON only, with keys: action, params, confidence.\n"
    "Valid actions: run_audit, register_agent, check_registration, none.\n"
    "Use action=none for explanations, questions, or if you are unsure.\n"
    "Only choose register_agent if the user explicitly asks to register now (self-register). "
    "Only choose check_registration if the user asks to check registration status. "
    "Only choose run_audit if the user asks to run an audit now.\n"
    "params should include: file for run_audit if present; agent_name/agent_id/tba_address for "
    "check_registration if present; agent_name for register_agent if provided.\n"
    "confidence must be a number between 0 and 1.\n"
    "Output JSON only. Example: {\"action\":\"check_registration\",\"params\":{\"agent_name\":\"agent-local-test\"},\"confidence\":0.78}"
)

class ActionIntent(TypedDict):
    action: str
    params: Dict[str, Any]


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _contains_any(text: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in text for phrase in phrases)


def _extract_json_payload(text: str) -> Dict[str, Any]:
    cleaned = text.strip().strip("`")
    if cleaned.startswith("{") and cleaned.endswith("}"):
        try:
            parsed = json.loads(cleaned)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        snippet = cleaned[start : end + 1]
        try:
            parsed = json.loads(snippet)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _parse_key_value_args(text: str) -> Dict[str, str]:
    params: Dict[str, str] = {}
    for token in text.split():
        if "=" in token:
            key, value = token.split("=", 1)
            params[key.strip()] = value.strip().strip("`\"'")
    return params


def _extract_agent_name(text: str) -> Optional[str]:
    raw = text.strip()
    if not raw:
        return None

    patterns = (
        r"check\s+(?:whether|if)\s+['\"]?([\w\-]+)['\"]?\s+is\s+registered",
        r"check(?: registration)?(?: for)?\s+['\"]?([\w\-]+)['\"]?(?:\s+if\s+registered)?",
        r"verify(?: registration)?(?: for)?\s+['\"]?([\w\-]+)['\"]?(?:\s+if\s+registered)?",
        r"is\s+['\"]?([\w\-]+)['\"]?\s+(?:already\s+)?registered",
        r"registered\s+for\s+['\"]?([\w\-]+)['\"]?",
        r"agent\s+['\"]?([\w\-]+)['\"]?\s+(?:registered|registration|status)",
    )
    stop_words = {
        "me",
        "i",
        "we",
        "us",
        "my",
        "our",
        "this",
        "that",
        "it",
        "whether",
        "if",
        "is",
        "are",
        "am",
        "you",
        "your",
        "the",
        "a",
        "an",
        "agent",
        "registration",
        "registered",
        "status",
        "check",
        "verify",
    }
    for pattern in patterns:
        match = re.search(pattern, raw, flags=re.IGNORECASE)
        if match:
            candidate = match.group(1).strip().strip("`\"'")
            if candidate and candidate.lower() not in stop_words:
                return candidate
    return None


def _extract_register_agent_name(text: str) -> Optional[str]:
    raw = text.strip()
    if not raw:
        return None

    patterns = (
        r"register(?:\s+\w+)*\s+as\s+['\"]?([\w\-]+)['\"]?",
        r"register\s+['\"]?([\w\-]+)['\"]?\s+as",
        r"(?:agent\s+name|name)\s*[:=]?\s*['\"]?([\w\-]+)['\"]?",
    )
    for pattern in patterns:
        match = re.search(pattern, raw, flags=re.IGNORECASE)
        if match:
            candidate = match.group(1).strip().strip("`\"'")
            if candidate and candidate not in {"me", "i", "we", "us", "my", "our", "this", "that", "it", "yourself"}:
                return candidate
    return None


def _coerce_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y", "on"}:
            return True
        if normalized in {"false", "0", "no", "n", "off"}:
            return False
    return default


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_agent_info(raw: Any) -> Any:
    if isinstance(raw, dict):
        return (
            raw.get("owner"),
            raw.get("tba"),
            raw.get("name"),
            raw.get("metadataURI"),
            raw.get("totalScore"),
            raw.get("findingsCount"),
            raw.get("registered"),
        )
    if isinstance(raw, (list, tuple)) and len(raw) == 1 and isinstance(raw[0], (list, tuple)):
        return raw[0]
    return raw


def _agent_info_to_dict(raw: Any) -> Dict[str, Any]:
    info = _normalize_agent_info(raw)
    if isinstance(info, dict):
        owner = info.get("owner")
        tba = info.get("tba")
        name = info.get("name")
        metadata_uri = info.get("metadataURI") or info.get("metadata_uri")
        total_score = _coerce_int(info.get("totalScore"), 0)
        findings_count = _coerce_int(info.get("findingsCount"), 0)
        registered = _coerce_bool(info.get("registered"), False)
        return {
            "owner": owner,
            "tba": tba,
            "name": name,
            "metadata_uri": metadata_uri,
            "total_score": total_score,
            "findings_count": findings_count,
            "registered": registered,
        }
    if isinstance(info, (list, tuple)):
        items = list(info)
        if len(items) < 7:
            items.extend([None] * (7 - len(items)))
        owner, tba, name, metadata_uri, total_score, findings_count, registered = items[:7]
        return {
            "owner": owner,
            "tba": tba,
            "name": name,
            "metadata_uri": metadata_uri,
            "total_score": _coerce_int(total_score, 0),
            "findings_count": _coerce_int(findings_count, 0),
            "registered": _coerce_bool(registered, False),
        }
    return {
        "owner": None,
        "tba": None,
        "name": None,
        "metadata_uri": None,
        "total_score": 0,
        "findings_count": 0,
        "registered": False,
    }


REGISTRY_ABI: list[dict[str, Any]] = [
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "uint256", "name": "agentId", "type": "uint256"},
            {"indexed": True, "internalType": "address", "name": "owner", "type": "address"},
            {"indexed": True, "internalType": "address", "name": "tba", "type": "address"},
            {"indexed": False, "internalType": "string", "name": "name", "type": "string"},
        ],
        "name": "AgentRegistered",
        "type": "event",
    },
    {
        "inputs": [
            {"internalType": "string", "name": "name", "type": "string"},
            {"internalType": "string", "name": "metadataURI", "type": "string"},
        ],
        "name": "registerAgent",
        "outputs": [
            {"internalType": "uint256", "name": "agentId", "type": "uint256"},
            {"internalType": "address", "name": "tba", "type": "address"},
        ],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "string", "name": "", "type": "string"}],
        "name": "nameToAgentId",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "string", "name": "name", "type": "string"}],
        "name": "resolveName",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "uint256", "name": "agentId", "type": "uint256"}],
        "name": "getAgent",
        "outputs": [
            {
                "components": [
                    {"internalType": "address", "name": "owner", "type": "address"},
                    {"internalType": "address", "name": "tba", "type": "address"},
                    {"internalType": "string", "name": "name", "type": "string"},
                    {"internalType": "string", "name": "metadataURI", "type": "string"},
                    {"internalType": "uint256", "name": "totalScore", "type": "uint256"},
                    {"internalType": "uint256", "name": "findingsCount", "type": "uint256"},
                    {"internalType": "bool", "name": "registered", "type": "bool"},
                ],
                "internalType": "struct OpenAuditRegistry.Agent",
                "name": "",
                "type": "tuple",
            },
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "address", "name": "addr", "type": "address"}],
        "name": "isRegistered",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "address", "name": "", "type": "address"}],
        "name": "tbaToAgentId",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "address", "name": "", "type": "address"}],
        "name": "ownerToAgentId",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "nextAgentId",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
]


def _load_env() -> None:
    try:
        load_dotenv(override=False)
    except Exception:
        return


def _get_rpc_url() -> Optional[str]:
    return os.getenv("OPENAUDIT_WALLET_RPC_URL") or os.getenv("RPC_URL")


def _get_registry_address() -> Optional[str]:
    return (
        os.getenv("OPENAUDIT_REGISTRY_ADDRESS")
        or os.getenv("OPENAUDIT_REGISTRY")
        or os.getenv("AGENT_REGISTRY_ADDRESS")
    )


def _ensure_registry_contract(contract: Any, registry_checksum: str) -> Optional[str]:
    try:
        contract.functions.nextAgentId().call()
    except Exception as exc:
        return (
            "error: OpenAuditRegistry ABI mismatch. "
            f"Check OPENAUDIT_REGISTRY_ADDRESS ({registry_checksum}). "
            f"Detail: {exc}"
        )
    return None


def _extract_agent_registered_event(contract: Any, receipt: Any) -> Optional[Dict[str, Any]]:
    try:
        events = contract.events.AgentRegistered().process_receipt(receipt)
    except Exception:
        return None
    if not events:
        return None
    args = events[-1].get("args", {})
    return {
        "agent_id": int(args.get("agentId", 0)) if args.get("agentId") is not None else None,
        "tba": args.get("tba"),
        "owner": args.get("owner"),
        "name": args.get("name"),
    }


def _is_info_intent(text: str) -> bool:
    return _contains_any(text, _INFO_PHRASES)


def _detect_action_intent(text: str) -> Optional[ActionIntent]:
    cleaned = _normalize_text(text)
    if not cleaned:
        return None
    if _is_info_intent(cleaned):
        return None

    payload = _extract_json_payload(text)
    kv = _parse_key_value_args(text)
    params: Dict[str, Any] = payload if payload else kv

    explicit_run = "run_audit" in cleaned
    explicit_register = "register_agent" in cleaned
    explicit_check = "check_registration" in cleaned
    has_file = ".sol" in cleaned or "file" in params

    register_word = re.search(r"\bregister\b", cleaned) is not None
    sign_up_word = "sign up" in cleaned or "sign-up" in cleaned or "signup" in cleaned
    enroll_word = re.search(r"\benroll\b", cleaned) is not None
    register_context = _contains_any(cleaned, _REGISTER_CONTEXT_HINTS)
    self_register = re.search(r"\bregister\b.*\b(yourself|myself|self)\b", cleaned) is not None
    register_imperative = re.match(r"^(ok\s+|okay\s+|please\s+|go\s+)?register\b", cleaned) is not None
    is_registered_question = re.search(r"\bis\s+['\"]?[\w\-]+['\"]?\s+registered\b", cleaned) is not None
    check_word = re.search(r"\bregistered\b", cleaned) is not None and (
        "am i" in cleaned
        or "are we" in cleaned
        or "are you" in cleaned
        or "is " in cleaned
        or "check" in cleaned
        or "status" in cleaned
        or is_registered_question
    )

    if explicit_check or _contains_any(cleaned, _CHECK_ACTION_PHRASES):
        if not any(key in params for key in ("agent_name", "agent_id", "tba_address")):
            candidate = _extract_agent_name(text)
            if candidate:
                params["agent_name"] = candidate
        return {"action": "check_registration", "params": params}

    if check_word:
        if not any(key in params for key in ("agent_name", "agent_id", "tba_address")):
            candidate = _extract_agent_name(text)
            if candidate:
                params["agent_name"] = candidate
        return {"action": "check_registration", "params": params}

    if (
        explicit_register
        or _contains_any(cleaned, _REGISTER_ACTION_PHRASES)
        or self_register
        or (register_word and register_context)
        or (sign_up_word and register_context)
        or (enroll_word and register_context)
        or register_imperative
    ):
        if "agent_name" not in params:
            candidate = _extract_register_agent_name(text)
            if candidate:
                params["agent_name"] = candidate
        return {"action": "register_agent", "params": params}

    audit_context = _contains_any(cleaned, _AUDIT_CONTEXT_HINTS)
    audit_phrase = _contains_any(cleaned, _AUDIT_ACTION_PHRASES)
    audit_verb = re.search(r"\b(audit|scan|analyze|review)\b", cleaned) is not None
    if explicit_run or has_file or audit_phrase or (audit_verb and audit_context):
        return {"action": "run_audit", "params": params}

    return None


def _classify_intent_with_llm(text: str, llm: Any) -> Optional[ActionIntent]:
    normalized = _normalize_text(text)
    if not normalized or _is_info_intent(normalized):
        return None

    try:
        response = llm.invoke(
            [
                SystemMessage(content=_INTENT_ROUTER_PROMPT),
                HumanMessage(content=text),
            ]
        )
    except Exception:
        return None

    content = response.content if hasattr(response, "content") else str(response)
    payload = _extract_json_payload(str(content))
    if not payload:
        return None

    action = payload.get("action")
    if action == "none" or action is None:
        return None
    if action not in {"run_audit", "register_agent", "check_registration"}:
        return None

    confidence = payload.get("confidence", 0)
    try:
        confidence_value = float(confidence)
    except (TypeError, ValueError):
        confidence_value = 0.0
    if confidence_value < 0.6:
        return None

    params = payload.get("params") or {}
    if not isinstance(params, dict):
        params = {}

    return {"action": action, "params": params}


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
        # ChatOpenAI initialization is fast (doesn't make network calls)
        return ChatOpenAI(
            model=openai_model,
            api_key=openai_key,
            base_url=openai_base_url,
            temperature=0.2,
        )

    ollama_model = os.getenv("OLLAMA_MODEL")
    if ollama_model:
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        # ChatOllama might try to connect - this could be slow if Ollama isn't running
        # Add timeout to fail faster
        try:
            return ChatOllama(
                model=ollama_model, 
                base_url=base_url, 
                temperature=0.2,
                timeout=5.0,  # 5 second timeout for initialization
            )
        except Exception as exc:
            raise AgentRuntimeError(
                f"Failed to connect to Ollama at {base_url}. "
                f"Is Ollama running? Error: {exc}"
            ) from exc

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


def _run_audit_impl(
    file: str,
    tools: str = "aderyn,slither",
    max_issues: int = 2,
    use_llm: bool = True,
    dump_intermediate: bool = True,
    reports_dir: str = "reports",
) -> str:
    """Run the OpenAudit pipeline on a Solidity file and return submission JSON."""
    if isinstance(file, dict):
        payload = file
    else:
        payload = _extract_json_payload(str(file))

    if payload:
        file = payload.get("file", file)
        tools = payload.get("tools", tools)
        max_issues = payload.get("max_issues", max_issues)
        use_llm = payload.get("use_llm", use_llm)
        dump_intermediate = payload.get("dump_intermediate", dump_intermediate)
        reports_dir = payload.get("reports_dir", reports_dir)

    max_issues = _coerce_int(max_issues, 2)
    use_llm = _coerce_bool(use_llm, True)
    dump_intermediate = _coerce_bool(dump_intermediate, True)
    reports_dir = str(reports_dir or "reports")

    try:
        target = Path(str(file)).expanduser()
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
        return _run_audit_impl(
            file=file,
            tools=tools,
            max_issues=max_issues,
            use_llm=use_llm,
            dump_intermediate=dump_intermediate,
            reports_dir=reports_dir,
        )


def _register_agent_impl(
    metadata_uri: Optional[str] = None,
    agent_name: Optional[str] = None,
    initial_operator: Optional[str] = None,
) -> str:
    """
    REGISTER THIS AGENT in the on-chain OpenAuditRegistry. Use this tool when the user asks to:
    - Register the agent
    - Register this agent
    - Sign up the agent
    - Create an agent registration
    - Register in the OpenAuditRegistry
    
    This tool registers the agent as an ERC-721 NFT, creates a Token Bound Account (TBA),
    and sets up an ENS subdomain. The agent will be able to participate in bounties after registration.

    Parameters (all optional):
    - metadata_uri: IPFS URI for agent metadata (default: "ipfs://test-agent-metadata")
    - agent_name: Name for the agent, will become {agent_name}.openaudit.eth (default: "agent-local-test")
    - initial_operator: (legacy) ignored by OpenAuditRegistry; kept for backward compatibility

    If no parameters are provided, sensible test defaults are used for local Anvil.

    Configuration (via .env):
    - OPENAUDIT_WALLET_PRIVATE_KEY: private key of the agent wallet (REQUIRED)
    - OPENAUDIT_WALLET_RPC_URL: RPC URL for the target network (REQUIRED)
    - OPENAUDIT_REGISTRY_ADDRESS: OpenAuditRegistry contract address (REQUIRED)

    Returns JSON with status, agent_id, tba address, and transaction hash.
    """
    if Web3 is None:
        raise AgentRuntimeError(
            "web3.py is not installed. Install it with: pip install web3"
        ) from _WEB3_IMPORT_ERROR  # type: ignore[arg-type]

    _load_env()

    # Allow LangChain to pass a single JSON-encoded argument
    if isinstance(metadata_uri, dict):  # type: ignore[redundant-expr]
        payload = metadata_uri  # type: ignore[assignment]
        metadata_uri = payload.get("metadata_uri")
        agent_name = payload.get("agent_name")
        initial_operator = payload.get("initial_operator")

    private_key = os.getenv("OPENAUDIT_WALLET_PRIVATE_KEY")
    rpc_url = _get_rpc_url()
    if not private_key or not rpc_url:
        return (
            "error: missing OPENAUDIT_WALLET_PRIVATE_KEY or OPENAUDIT_WALLET_RPC_URL (or RPC_URL). "
            "Set these in your .env to enable on-chain registration."
        )

    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        return f"error: could not connect to RPC at {rpc_url}"

    account = w3.eth.account.from_key(private_key)

    registry_address = _get_registry_address()
    if not registry_address:
        return (
            "error: missing OPENAUDIT_REGISTRY_ADDRESS. "
            "Set this in your .env to enable on-chain registration."
        )

    try:
        registry_checksum = w3.to_checksum_address(registry_address)
    except ValueError:
        return f"error: invalid OPENAUDIT_REGISTRY_ADDRESS: {registry_address}"

    contract = w3.eth.contract(address=registry_checksum, abi=REGISTRY_ABI)
    registry_error = _ensure_registry_contract(contract, registry_checksum)
    if registry_error:
        return registry_error

    # Defaults for local testing
    metadata_uri = metadata_uri or "ipfs://test-agent-metadata"
    agent_name = agent_name or "agent-local-test"
    if initial_operator:
        # OpenAuditRegistry does not accept initial_operator; keep for backward compatibility.
        pass

    try:
        nonce = w3.eth.get_transaction_count(account.address)
        tx = contract.functions.registerAgent(
            agent_name,
            metadata_uri,
        ).build_transaction(
            {
                "from": account.address,
                "nonce": nonce,
                "gas": 500000,
                "gasPrice": w3.eth.gas_price,
            }
        )
        signed = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

        if receipt.status != 1:
            return json.dumps(
                {
                    "status": "failed",
                    "tx_hash": tx_hash.hex(),
                    "agent_name": agent_name,
                    "metadata_uri": metadata_uri,
                }
            )

        agent_id_int: Optional[int] = None
        tba_addr: Optional[str] = None

        event_data = _extract_agent_registered_event(contract, receipt)
        if event_data:
            agent_id_int = event_data.get("agent_id")
            tba_addr = event_data.get("tba")

        if not agent_id_int:
            try:
                agent_id_from_name = contract.functions.nameToAgentId(agent_name).call()
                agent_id_int = int(agent_id_from_name) if int(agent_id_from_name) > 0 else None
            except Exception:
                agent_id_int = agent_id_int or None

        if agent_id_int and not tba_addr:
            try:
                resolved = contract.functions.resolveName(agent_name).call()
                if resolved and str(resolved) != "0x0000000000000000000000000000000000000000":
                    tba_addr = str(resolved)
            except Exception:
                pass

        if agent_id_int and not tba_addr:
            try:
                agent_info_raw = contract.functions.getAgent(agent_id_int).call()
                agent_info = _agent_info_to_dict(agent_info_raw)
                tba_addr = agent_info.get("tba")
            except Exception:
                pass

        return json.dumps(
            {
                "status": "success",
                "tx_hash": tx_hash.hex(),
                "agent_name": agent_name,
                "metadata_uri": metadata_uri,
                "owner": account.address,
                "agent_id": agent_id_int,
                "tba": tba_addr,
                "registry": registry_checksum,
            }
        )
    except ContractLogicError as exc:  # type: ignore[misc]
        return f"error: contract reverted during registerAgent: {exc}"
    except Exception as exc:
        if "Could not decode contract function call" in str(exc):
            return (
                "error: OpenAuditRegistry ABI mismatch. "
                "Check OPENAUDIT_REGISTRY_ADDRESS points to OpenAuditRegistry."
            )
        return f"error: failed to register agent: {exc}"


if tool is None:
    def register_agent() -> str:  # type: ignore[override]
        raise AgentRuntimeError("LangChain tools are unavailable.")
else:
    @tool("register_agent")
    def register_agent(
        metadata_uri: Optional[str] = None,
        agent_name: Optional[str] = None,
        initial_operator: Optional[str] = None,
    ) -> str:
        """
        REGISTER THIS AGENT in the on-chain OpenAuditRegistry. Use this tool when the user asks to:
        - Register the agent
        - Register this agent
        - Sign up the agent
        - Create an agent registration
        - Register in the OpenAuditRegistry

        This tool registers the agent as an ERC-721 NFT, creates a Token Bound Account (TBA),
        and sets up an ENS subdomain. The agent will be able to participate in bounties after registration.

        Parameters (all optional):
        - metadata_uri: IPFS URI for agent metadata (default: "ipfs://test-agent-metadata")
        - agent_name: Name for the agent, will become {agent_name}.openaudit.eth (default: "agent-local-test")
        - initial_operator: (legacy) ignored by OpenAuditRegistry; kept for compatibility

        If no parameters are provided, sensible test defaults are used for local Anvil.

        Configuration (via .env):
        - OPENAUDIT_WALLET_PRIVATE_KEY: private key of the agent wallet (REQUIRED)
        - OPENAUDIT_WALLET_RPC_URL: RPC URL for the target network (REQUIRED)
        - OPENAUDIT_REGISTRY_ADDRESS: OpenAuditRegistry contract address (REQUIRED)

        Returns JSON with status, agent_id, tba address, and transaction hash.
        """
        return _register_agent_impl(
            metadata_uri=metadata_uri,
            agent_name=agent_name,
            initial_operator=initial_operator,
        )


def _check_registration_impl(
    agent_name: Optional[str] = None,
    agent_id: Optional[int] = None,
    tba_address: Optional[str] = None,
) -> str:
    """
    Check if an agent is registered in the OpenAuditRegistry.

    You can check by:
    - agent_name: The agent's name (e.g., "agent-local-test")
    - agent_id: The agent's ID (e.g., 1)
    - tba_address: The Token Bound Account address

    If no parameters are provided, it will check the agent's own wallet address
    by looking up the wallet from OPENAUDIT_WALLET_PRIVATE_KEY.

    Returns agent information including name, TBA, owner, metadata URI, and agent ID.
    """
    if Web3 is None:
        raise AgentRuntimeError(
            "web3.py is not installed. Install it with: pip install web3"
        ) from _WEB3_IMPORT_ERROR  # type: ignore[arg-type]

    _load_env()

    # Allow LangChain to pass a single JSON-encoded argument
    if isinstance(agent_name, dict):  # type: ignore[redundant-expr]
        payload = agent_name  # type: ignore[assignment]
        agent_name = payload.get("agent_name")
        agent_id = payload.get("agent_id")
        tba_address = payload.get("tba_address")

    if agent_id is not None:
        try:
            agent_id = int(agent_id)
        except (TypeError, ValueError):
            return f"error: invalid agent_id: {agent_id}"

    rpc_url = _get_rpc_url()
    if not rpc_url:
        return (
            "error: missing OPENAUDIT_WALLET_RPC_URL (or RPC_URL). "
            "Set this in your .env to enable registration checks."
        )

    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        return f"error: could not connect to RPC at {rpc_url}"

    registry_address = _get_registry_address()
    if not registry_address:
        return (
            "error: missing OPENAUDIT_REGISTRY_ADDRESS. "
            "Set this in your .env to enable registration checks."
        )

    try:
        registry_checksum = w3.to_checksum_address(registry_address)
    except ValueError:
        return f"error: invalid OPENAUDIT_REGISTRY_ADDRESS: {registry_address}"

    contract = w3.eth.contract(address=registry_checksum, abi=REGISTRY_ABI)
    registry_error = _ensure_registry_contract(contract, registry_checksum)
    if registry_error:
        return registry_error

    result: Dict[str, Any] = {
        "registry": registry_checksum,
    }

    try:
        # Check by agent name
        if agent_name:
            agent_id_from_name = contract.functions.nameToAgentId(agent_name).call()
            agent_id_int = _coerce_int(agent_id_from_name, 0)
            if agent_id_int == 0:
                try:
                    resolved_tba = contract.functions.resolveName(agent_name).call()
                    if resolved_tba and str(resolved_tba) != "0x0000000000000000000000000000000000000000":
                        agent_id_int = _coerce_int(
                            contract.functions.tbaToAgentId(resolved_tba).call(),
                            0,
                        )
                except Exception:
                    agent_id_int = 0
            if agent_id_int == 0:
                return json.dumps({
                    "status": "not_found",
                    "agent_name": agent_name,
                    "message": f"Agent with name '{agent_name}' is not registered",
                    **result,
                })
            agent_info_raw = contract.functions.getAgent(agent_id_int).call()
            agent_info = _agent_info_to_dict(agent_info_raw)
            return json.dumps({
                "status": "registered",
                "agent_name": agent_name,
                "agent_id": int(agent_id_int),
                "tba": agent_info.get("tba"),
                "owner": agent_info.get("owner"),
                "metadata_uri": agent_info.get("metadata_uri"),
                "total_score": agent_info.get("total_score", 0),
                "findings_count": agent_info.get("findings_count", 0),
                **result,
            })

        # Check by agent ID
        if agent_id is not None:
            try:
                agent_info_raw = contract.functions.getAgent(agent_id).call()
                agent_info = _agent_info_to_dict(agent_info_raw)
                if not agent_info.get("registered"):
                    return json.dumps({
                        "status": "not_found",
                        "agent_id": agent_id,
                        "message": f"Agent with ID {agent_id} does not exist",
                        **result,
                    })
                return json.dumps({
                    "status": "registered",
                    "agent_id": agent_id,
                    "name": agent_info.get("name"),
                    "tba": agent_info.get("tba"),
                    "owner": agent_info.get("owner"),
                    "metadata_uri": agent_info.get("metadata_uri"),
                    "total_score": agent_info.get("total_score", 0),
                    "findings_count": agent_info.get("findings_count", 0),
                    **result,
                })
            except Exception as exc:
                if "AgentDoesNotExist" in str(exc) or "execution reverted" in str(exc).lower():
                    return json.dumps({
                        "status": "not_found",
                        "agent_id": agent_id,
                        "message": f"Agent with ID {agent_id} does not exist",
                        **result,
                    })
                raise

        # Check by TBA address
        if tba_address:
            try:
                tba_checksum = w3.to_checksum_address(tba_address)
            except ValueError:
                return f"error: invalid TBA address: {tba_address}"

            agent_id_from_tba = contract.functions.tbaToAgentId(tba_checksum).call()
            if _coerce_int(agent_id_from_tba, 0) == 0:
                return json.dumps({
                    "status": "not_registered",
                    "tba": tba_checksum,
                    "message": "This TBA address is not registered as an agent",
                    **result,
                })

            agent_info_raw = contract.functions.getAgent(agent_id_from_tba).call()
            agent_info = _agent_info_to_dict(agent_info_raw)
            return json.dumps({
                "status": "registered",
                "tba": tba_checksum,
                "agent_id": int(agent_id_from_tba),
                "name": agent_info.get("name"),
                "owner": agent_info.get("owner"),
                "metadata_uri": agent_info.get("metadata_uri"),
                "total_score": agent_info.get("total_score", 0),
                "findings_count": agent_info.get("findings_count", 0),
                **result,
            })

        # No parameters: check by wallet address
        private_key = os.getenv("OPENAUDIT_WALLET_PRIVATE_KEY")
        if not private_key:
            return (
                "error: no search parameters provided and OPENAUDIT_WALLET_PRIVATE_KEY not set. "
                "Provide agent_name, agent_id, or tba_address, or set OPENAUDIT_WALLET_PRIVATE_KEY."
            )

        account = w3.eth.account.from_key(private_key)
        wallet_address = account.address
        wallet_checksum = w3.to_checksum_address(wallet_address)

        owner_id = contract.functions.ownerToAgentId(wallet_checksum).call()
        if _coerce_int(owner_id, 0) > 0:
            agent_info_raw = contract.functions.getAgent(owner_id).call()
            agent_info = _agent_info_to_dict(agent_info_raw)
            return json.dumps({
                "status": "registered",
                "agent_id": int(owner_id),
                "name": agent_info.get("name"),
                "tba": agent_info.get("tba"),
                "owner": agent_info.get("owner"),
                "metadata_uri": agent_info.get("metadata_uri"),
                "total_score": agent_info.get("total_score", 0),
                "findings_count": agent_info.get("findings_count", 0),
                "wallet_address": wallet_address,
                **result,
            })

        tba_id = contract.functions.tbaToAgentId(wallet_checksum).call()
        if _coerce_int(tba_id, 0) > 0:
            agent_info_raw = contract.functions.getAgent(tba_id).call()
            agent_info = _agent_info_to_dict(agent_info_raw)
            return json.dumps({
                "status": "registered",
                "agent_id": int(tba_id),
                "name": agent_info.get("name"),
                "tba": agent_info.get("tba"),
                "owner": agent_info.get("owner"),
                "metadata_uri": agent_info.get("metadata_uri"),
                "total_score": agent_info.get("total_score", 0),
                "findings_count": agent_info.get("findings_count", 0),
                "wallet_address": wallet_address,
                **result,
            })

        # Otherwise, scan registered agents to see if this wallet is owner
        next_id = contract.functions.nextAgentId().call()
        try:
            total_int = max(0, int(next_id) - 1)
        except (TypeError, ValueError):
            total_int = 0

        for agent_id in range(1, total_int + 1):
            try:
                agent_info_raw = contract.functions.getAgent(agent_id).call()
                agent_info = _agent_info_to_dict(agent_info_raw)
            except Exception:
                continue
            if not agent_info.get("registered"):
                continue
            owner = str(agent_info.get("owner") or "").lower()
            if owner == wallet_checksum.lower():
                return json.dumps({
                    "status": "registered",
                    "agent_id": agent_id,
                    "name": agent_info.get("name"),
                    "tba": agent_info.get("tba"),
                    "owner": agent_info.get("owner"),
                    "metadata_uri": agent_info.get("metadata_uri"),
                    "total_score": agent_info.get("total_score", 0),
                    "findings_count": agent_info.get("findings_count", 0),
                    "wallet_address": wallet_address,
                    "total_agents": total_int,
                    **result,
                })

        return json.dumps({
            "status": "not_registered",
            "message": "No registered agent found for this wallet address.",
            "wallet_address": wallet_address,
            "total_agents": total_int,
            **result,
        })

    except Exception as exc:
        if "Could not decode contract function call" in str(exc):
            return (
                "error: OpenAuditRegistry ABI mismatch. "
                "Check OPENAUDIT_REGISTRY_ADDRESS points to OpenAuditRegistry."
            )
        return f"error: failed to check registration: {exc}"


if tool is None:
    def check_registration() -> str:  # type: ignore[override]
        raise AgentRuntimeError("LangChain tools are unavailable.")
else:
    @tool("check_registration")
    def check_registration(
        agent_name: Optional[str] = None,
        agent_id: Optional[int] = None,
        tba_address: Optional[str] = None,
    ) -> str:
        """
        Check if an agent is registered in the OpenAuditRegistry.

        You can check by:
        - agent_name: The agent's name (e.g., "agent-local-test")
        - agent_id: The agent's ID (e.g., 1)
        - tba_address: The Token Bound Account address

        If no parameters are provided, it will check the agent's own wallet address
        by looking up the wallet from OPENAUDIT_WALLET_PRIVATE_KEY.

        Returns agent information including name, TBA, owner, metadata URI, and agent ID.
        """
        return _check_registration_impl(
            agent_name=agent_name,
            agent_id=agent_id,
            tba_address=tba_address,
        )


def _build_tools(include_wallet_tools: bool) -> List[BaseTool]:
    _require_langchain()
    tools: List[BaseTool] = [run_audit, register_agent, check_registration]

    if not include_wallet_tools:
        return tools

    try:
        # Lazy import to avoid importing coinbase_agentkit_langchain (and its
        # nest_asyncio side effects) when wallet tools are not needed.
        from coinbase_agentkit_langchain import get_langchain_tools

        # This can be slow if wallet initialization fails or tries to connect
        agentkit = create_agentkit()
    except WalletInitError as exc:
        print(f"warning: coinbase-agentkit wallet tools disabled ({exc})", file=sys.stderr)
        print("  Note: Agent still has wallet access via web3 for register_agent and check_registration tools.", file=sys.stderr)
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
    base_prompt = system_prompt or DEFAULT_AGENT_SYSTEM_PROMPT
    tool_instructions = (
        "You have access to the following tools:\n{tools}\n\n"
        "Tool names: {tool_names}\n\n"
        "You are the agent itself. Registration is for THIS agent's on-chain identity.\n\n"
        "CRITICAL: When a user asks to register the agent, you MUST call the register_agent tool. "
        "Do not just explain - actually execute the registration.\n\n"
        "Tool input formats:\n"
        "- register_agent: JSON with optional metadata_uri, agent_name (initial_operator ignored if provided)\n"
        "- check_registration: JSON with optional agent_name, agent_id, or tba_address\n"
        "- run_audit: JSON with file (required), tools, max_issues, use_llm, dump_intermediate, reports_dir\n\n"
        "Use the following format:\n"
        "Thought: your reasoning\n"
        "Action: the tool name to use\n"
        "Action Input: the input to the tool (strict JSON, no extra text)\n"
        "Observation: the tool result\n"
        "Final: your response to the user\n"
        "If no tool is needed, skip Action/Observation and respond with Final only.\n"
    )
    # Add few-shot examples for registration
    # ⚠️ CRITICAL: In LangChain ChatPromptTemplate, curly braces are template variables!
    # To use literal curly braces (like empty JSON {}), you MUST escape them as {{}}
    # Single {} will be interpreted as a variable placeholder and cause KeyError
    # Always use {{}} for literal braces, {{variable}} for template variables
    examples = (
        "\n\nExample interactions:\n"
        "User: 'Register this agent'\n"
        "Assistant: I'll register this agent now.\n"
        "Action: register_agent\n"
        "Action Input: {{}}\n\n"  # Empty JSON object - MUST use {{}} not {}
        "User: 'Check if I'm registered'\n"
        "Assistant: I'll check your registration status.\n"
        "Action: check_registration\n"
        "Action Input: {{}}\n\n"  # Empty JSON object - MUST use {{}} not {}
    )
    
    # ⚠️ WARNING: When building prompt strings for ChatPromptTemplate:
    # - Use {variable} for template variables (e.g., {input}, {tools})
    # - Use {{}} for literal curly braces (e.g., empty JSON {{}})
    # - NEVER use single {} for literal braces - it will cause KeyError!
    prompt_string = f"{base_prompt}\n\n{tool_instructions}{examples}"
    
    # Validation: Check for unescaped {} that would cause KeyError
    # Look for {} that's not part of {{}} or {variable_name}
    unescaped_braces = re.findall(r'(?<!\{)\{(?!\{|\w+\})', prompt_string)
    if unescaped_braces:
        raise ValueError(
            "⚠️ CRITICAL ERROR: Found unescaped {} in prompt template! "
            "LangChain interprets {} as a variable placeholder. "
            "Use {{}} for literal braces. "
            "See agents/LANGCHAIN_PROMPT_WARNING.md for details."
        )
    
    return ChatPromptTemplate.from_messages(
        [
            ("system", prompt_string),
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
    
    llm_start = time.time()
    llm = _build_llm()
    llm_time = time.time() - llm_start
    print(f"    LLM initialized ({llm_time:.2f}s)", flush=True)
    
    tools_start = time.time()
    print("  - Loading tools...", flush=True)
    tools = _build_tools(include_wallet_tools)
    tools_time = time.time() - tools_start
    print(f"    Tools loaded ({tools_time:.2f}s)", flush=True)
    
    executor_start = time.time()
    print("  - Creating agent executor...", flush=True)
    
    if _USE_NEW_API:
        # LangChain v1.0+ API: create_agent returns a directly invokable agent
        base_prompt = system_prompt or DEFAULT_AGENT_SYSTEM_PROMPT
        agent = create_agent(
            model=llm,
            tools=tools,
            system_prompt=base_prompt,
        )
        executor_time = time.time() - executor_start
        print(f"    Agent executor created ({executor_time:.2f}s)", flush=True)
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
        executor = AgentExecutor(
            agent=agent,
            tools=tools,
            verbose=verbose,
            handle_parsing_errors=True,
            max_iterations=10,  # Increased to allow tool calls
            max_execution_time=120,  # Increased timeout
            early_stopping_method="force",
            return_intermediate_steps=True,  # Return intermediate steps for debugging
        )
        executor_time = time.time() - executor_start
        print(f"    Agent executor created ({executor_time:.2f}s)", flush=True)
        return executor


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
        return system_prompt or DEFAULT_CHAT_SYSTEM_PROMPT

    def _extract_audit_params(text: str) -> Dict[str, Any]:
        cleaned = text.strip().strip("`")
        params = _extract_json_payload(cleaned) or _parse_key_value_args(cleaned)

        if "file" not in params:
            match = re.search(r"([\\w./\\-\\\\]+\\.sol)", cleaned)
            if match:
                params["file"] = match.group(1)
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

            intent = _detect_action_intent(user_input)
            if intent is None:
                try:
                    llm = _ensure_chat_llm()
                    intent = _classify_intent_with_llm(user_input, llm)
                except Exception:
                    intent = None

            if intent is not None:
                action = intent["action"]
                params = dict(intent["params"])

                if action == "run_audit":
                    params = {**_extract_audit_params(user_input), **params}
                    allowed = {"file", "tools", "max_issues", "use_llm", "dump_intermediate", "reports_dir"}
                    params = {key: value for key, value in params.items() if key in allowed}
                    if not params.get("file"):
                        print(
                            "Please provide a Solidity file path, e.g. "
                            "`run_audit file=sample_contracts/CoinFlip.sol`."
                        )
                        continue
                    try:
                        output = _run_audit_impl(**params)
                    except Exception as exc:
                        print(f"error: failed to run audit ({exc})")
                        continue
                    print(output)
                    continue

                if action == "register_agent":
                    allowed = {"metadata_uri", "agent_name", "initial_operator"}
                    params = {key: value for key, value in params.items() if key in allowed}
                    if "agent_name" not in params:
                        candidate = _extract_register_agent_name(user_input)
                        if candidate:
                            params["agent_name"] = candidate
                    try:
                        output = _register_agent_impl(**params)
                    except Exception as exc:
                        print(f"error: failed to register agent ({exc})")
                        continue
                    print(output)
                    continue

                if action == "check_registration":
                    allowed = {"agent_name", "agent_id", "tba_address"}
                    params = {key: value for key, value in params.items() if key in allowed}
                    if not any(key in params for key in ("agent_name", "agent_id", "tba_address")):
                        candidate = _extract_agent_name(user_input)
                        if candidate:
                            params["agent_name"] = candidate
                    try:
                        output = _check_registration_impl(**params)
                    except Exception as exc:
                        print(f"error: failed to check registration ({exc})")
                        continue
                    print(output)
                    continue

            # Non-action requests: route to the LLM for explanations and guidance
            try:
                llm = _ensure_chat_llm()
                response = llm.invoke(
                    [
                        SystemMessage(content=_chat_system_prompt()),
                        HumanMessage(content=user_input),
                    ]
                )
                output = response.content if hasattr(response, "content") else str(response)
                if output:
                    print(output)
            except AgentRuntimeError as exc:
                print(f"error: {exc}")
            except Exception as exc:
                print(f"error: failed to process message ({exc})")
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
    start_time = time.time()
    
    try:
        load_dotenv(override=False)  # Don't override if already loaded
    except Exception:
        # .env might have already been loaded, or there's a parsing error
        # Continue anyway - environment variables might be set another way
        pass
    
    print("Initializing agent...", flush=True)
    
    print("  - Loading LLM...", flush=True)
    llm_start = time.time()
    agent_executor = create_agent_executor(
        include_wallet_tools=include_wallet_tools,
        system_prompt=system_prompt,
        verbose=verbose,
    )
    llm_time = time.time() - llm_start
    
    total_time = time.time() - start_time
    print(f"Agent ready! (LLM: {llm_time:.2f}s, Total: {total_time:.2f}s)", flush=True)
    
    if mode == "auto":
        return run_autonomous_mode(agent_executor, interval)
    return run_chat_mode(agent_executor, system_prompt=system_prompt)
