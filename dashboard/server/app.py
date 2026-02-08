from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from agents.cli import run_graph, run_linear
from agents.progress import ProgressReporter
from agents import langchain_agent as lc_agent

# Local modules
from dashboard.server.pinata import PinataError, gateway_url, pin_json
from dashboard.server import registry

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
RUNS_DIR = BASE_DIR / "runs"
AGENT_SESSIONS_DIR = RUNS_DIR / "agent_sessions"

load_dotenv()

app = FastAPI(title="OpenAudit Platform API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Agent runtime (in-memory sessions) ---
_AGENT_EXECUTOR = None
_AGENT_LOCK = threading.Lock()
_AGENT_SESSIONS: Dict[str, Dict[str, Any]] = {}
_CHAT_LLM = None

@app.get("/", tags=["health"])
def health_check():
    """Simple health-check endpoint."""
    return {"status": "ok", "service": "OpenAudit API"}


@app.post("/api/agent/chat")
async def agent_chat(request: Request) -> JSONResponse:
    body = await request.json()
    message = (body.get("message") or "").strip()
    if not message:
        return JSONResponse({"error": "Missing 'message' field"}, status_code=400)

    session_id = body.get("session_id") or uuid.uuid4().hex
    session_dir = AGENT_SESSIONS_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    session = _AGENT_SESSIONS.setdefault(session_id, {"history": []})
    history: list[dict] = session["history"]
    history.append({"role": "user", "content": message})

    # Run the agent work in a background thread so the event loop can keep serving
    # progress polling requests while long analyses run.
    payload = await asyncio.to_thread(_run_agent_in_session, session_dir, message)

    output = payload.get("output", "")
    history.append({"role": "assistant", "content": output})
    action = payload.get("action")
    duration_ms = payload.get("duration_ms")
    if action and duration_ms is not None:
        logger.info("Agent chat action=%s duration_ms=%s session=%s", action, duration_ms, session_id)

    return JSONResponse(
        {
            "session_id": session_id,
            "response": output,
            "action": action,
            "duration_ms": duration_ms,
            "session_dir": str(session_dir),
            "reports_dir": str(session_dir / "reports"),
            "submission_path": str(session_dir / "submission.json"),
            "history": history,
        }
    )


@app.get("/api/agent/sessions/{session_id}/events")
def get_agent_events(session_id: str, limit: int = 200) -> JSONResponse:
    session_dir = AGENT_SESSIONS_DIR / session_id
    events_path = session_dir / "reports" / "progress.jsonl"
    if not events_path.exists():
        return JSONResponse({"events": []})
    lines = events_path.read_text(encoding="utf-8").splitlines()
    events = [json.loads(line) for line in lines[-limit:]]
    return JSONResponse({"events": events})



def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _allowed_artifacts() -> set[str]:
    return {
        "submission.json",
        "aderyn_report.json",
        "slither_report.json",
        "static_analysis_summary.json",
        "triage.json",
        "logic.json",
        "ipfs.json",
    }


def _find_source_file(job_dir: Path) -> Optional[Path]:
    for file in job_dir.glob("*.sol"):
        return file
    return None


def _get_agent_executor():
    global _AGENT_EXECUTOR
    if _AGENT_EXECUTOR is None:
        _AGENT_EXECUTOR = lc_agent.create_agent_executor(
            include_wallet_tools=False,
            system_prompt=None,
            verbose=False,
        )
    return _AGENT_EXECUTOR


def _get_chat_llm():
    global _CHAT_LLM
    if _CHAT_LLM is None:
        _CHAT_LLM = lc_agent._build_llm()
    return _CHAT_LLM


def _build_agent_input(history: list[dict], message: str) -> str:
    if not history:
        return message
    lines = []
    for item in history:
        role = item.get("role", "user")
        content = item.get("content", "")
        if content:
            lines.append(f"{role}: {content}")
    lines.append(f"user: {message}")
    return "\n".join(lines)


def _run_agent_in_session(session_dir: Path, message: str) -> Dict[str, Any]:
    with _AGENT_LOCK:
        prev_cwd = os.getcwd()
        try:
            os.chdir(session_dir)
            return _route_agent_message(message)
        finally:
            os.chdir(prev_cwd)


def _extract_audit_params(text: str) -> Dict[str, Any]:
    cleaned = text.strip().strip("`")
    params = lc_agent._extract_json_payload(cleaned) or lc_agent._parse_key_value_args(cleaned)
    if "file" not in params:
        match = lc_agent.re.search(r"([\\w./\\-\\\\]+\\.sol)", cleaned)
        if match:
            params["file"] = match.group(1)
        else:
            for token in cleaned.split():
                if ".sol" in token:
                    params["file"] = token.strip("`\"'")
                    break
    return params


def _route_agent_message(message: str) -> Dict[str, Any]:
    start = time.perf_counter()
    intent = lc_agent._detect_action_intent(message)
    if intent is None:
        try:
            llm = _get_chat_llm()
            intent = lc_agent._classify_intent_with_llm(message, llm)
        except Exception:
            intent = None

    if intent is None:
        try:
            llm = _get_chat_llm()
            response = llm.invoke(
                [
                    lc_agent.SystemMessage(content=lc_agent.DEFAULT_CHAT_SYSTEM_PROMPT),
                    lc_agent.HumanMessage(content=message),
                ]
            )
            output = response.content if hasattr(response, "content") else str(response)
            duration = int((time.perf_counter() - start) * 1000)
            return {"output": output, "action": "chat", "duration_ms": duration}
        except Exception as exc:  # noqa: BLE001
            duration = int((time.perf_counter() - start) * 1000)
            return {"output": f"error: failed to process message ({exc})", "action": "chat", "duration_ms": duration}

    action = intent["action"]
    params = dict(intent["params"])

    def _wrap(output: str) -> Dict[str, Any]:
        duration = int((time.perf_counter() - start) * 1000)
        return {"output": output, "action": action, "duration_ms": duration}

    if action == "run_audit":
        params = {**_extract_audit_params(message), **params}
        allowed = {"file", "tools", "max_issues", "use_llm", "dump_intermediate", "reports_dir"}
        params = {key: value for key, value in params.items() if key in allowed}
        if not params.get("file"):
            return _wrap("error: missing Solidity file path. Provide `run_audit file=...`.")
        return _wrap(lc_agent._run_audit_impl(**params))

    if action == "register_agent":
        allowed = {"metadata_uri", "agent_name", "initial_operator"}
        params = {key: value for key, value in params.items() if key in allowed}
        if "agent_name" not in params:
            candidate = lc_agent._extract_register_agent_name(message)
            if candidate:
                params["agent_name"] = candidate
        return _wrap(lc_agent._register_agent_impl(**params))

    if action == "check_registration":
        allowed = {"agent_name", "agent_id", "tba_address"}
        params = {key: value for key, value in params.items() if key in allowed}
        if not any(key in params for key in ("agent_name", "agent_id", "tba_address")):
            candidate = lc_agent._extract_agent_name(message)
            if candidate:
                params["agent_name"] = candidate
        return _wrap(lc_agent._check_registration_impl(**params))

    if action == "list_bounties":
        allowed = {"limit", "rpc_url", "registry_address", "registry"}
        params = {key: value for key, value in params.items() if key in allowed}
        return _wrap(lc_agent._list_bounties_impl(**params))

    if action == "analyze_bounty":
        allowed = {
            "bounty_id",
            "tools",
            "max_issues",
            "use_llm",
            "dump_intermediate",
            "reports_dir",
            "submission_path",
            "rpc_url",
            "registry_address",
            "registry",
            "use_etherscan",
            "source_map",
        }
        params = {key: value for key, value in params.items() if key in allowed}
        if "bounty_id" not in params:
            bounty_id = lc_agent._extract_bounty_id(message)
            if bounty_id is not None:
                params["bounty_id"] = bounty_id
        if "bounty_id" not in params:
            return _wrap("error: missing bounty_id. Provide `analyze_bounty bounty_id=...`.")
        return _wrap(lc_agent._analyze_bounty_impl(**params))

    if action == "pin_submission":
        allowed = {"submission_path", "name"}
        params = {key: value for key, value in params.items() if key in allowed}
        if "submission_path" not in params:
            params["submission_path"] = "submission.json"
        return _wrap(lc_agent._pin_submission_impl(**params))

    if action == "submit_bounty":
        allowed = {"bounty_id", "report_cid", "rpc_url", "registry_address", "registry", "private_key"}
        params = {key: value for key, value in params.items() if key in allowed}
        bounty_val = params.get("bounty_id")
        if isinstance(bounty_val, str):
            params["bounty_id"] = bounty_val.strip().strip("`\"',")
        if not params.get("bounty_id") or not lc_agent.re.search(r"(\\d+)", str(params.get("bounty_id", ""))):
            bounty_id = lc_agent._extract_bounty_id(message)
            if bounty_id is not None:
                params["bounty_id"] = bounty_id

        report_val = params.get("report_cid")
        if isinstance(report_val, str):
            params["report_cid"] = report_val.strip().strip("`\"',")
        if not params.get("report_cid"):
            report_cid = lc_agent._extract_report_cid(message)
            if report_cid:
                params["report_cid"] = report_cid
        if "bounty_id" not in params or "report_cid" not in params:
            return _wrap("error: missing bounty_id or report_cid.")
        return _wrap(lc_agent._submit_bounty_impl(**params))

    return _wrap("error: unsupported action.")


def _run_job(
    *,
    job_dir: Path,
    solidity_file: Path,
    max_issues: int,
    use_llm: bool,
    use_graph: bool,
    tools: list[str],
) -> None:
    progress = ProgressReporter(job_dir)
    status_path = job_dir / "status.json"
    progress.start("queued", "Job started")
    _write_json(status_path, {"status": "running"})
    try:
        if use_graph:
            submission = run_graph(
                solidity_file=solidity_file,
                max_issues=max_issues,
                use_llm=use_llm,
                tools=tools,
                progress=progress,
                reports_dir=job_dir,
            )
        else:
            submission = run_linear(
                solidity_file=solidity_file,
                max_issues=max_issues,
                use_llm=use_llm,
                tools=tools,
                dump_intermediate=True,
                reports_dir=job_dir,
                progress=progress,
            )
        _write_json(job_dir / "submission.json", submission)

        # --- Auto-pin to IPFS via Pinata ---
        try:
            cid = pin_json(submission, name=f"openaudit-{job_dir.name}")
            gw_url = gateway_url(cid)
            _write_json(job_dir / "ipfs.json", {"cid": cid, "gateway_url": gw_url})
            registry.add_entry(
                cid=cid,
                job_id=job_dir.name,
                title=submission.get("title", "Untitled"),
                severity=submission.get("severity", "UNKNOWN"),
                gateway_url=gw_url,
            )
            logger.info("Pinned job %s → CID %s", job_dir.name, cid)
        except Exception as pin_exc:  # noqa: BLE001
            logger.warning("IPFS pin failed for job %s: %s", job_dir.name, pin_exc)
            _write_json(job_dir / "ipfs_error.json", {"error": str(pin_exc)})

        _write_json(status_path, {"status": "completed"})
        progress.complete("done", "Job completed")
    except Exception as exc:  # noqa: BLE001
        _write_json(job_dir / "error.json", {"error": str(exc)})
        _write_json(status_path, {"status": "failed"})
        progress.fail("done", "Job failed")


@app.post("/api/jobs")
async def create_job(
    file: UploadFile = File(...),
    tools: str = Form("aderyn"),
    max_issues: int = Form(2),
    use_llm: bool = Form(True),
    use_graph: bool = Form(False),
) -> JSONResponse:
    job_id = uuid.uuid4().hex
    job_dir = RUNS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    solidity_path = job_dir / file.filename
    solidity_path.write_bytes(await file.read())

    tool_list = [tool.strip().lower() for tool in tools.split(",") if tool.strip()]
    thread = threading.Thread(
        target=_run_job,
        kwargs={
            "job_dir": job_dir,
            "solidity_file": solidity_path,
            "max_issues": max_issues,
            "use_llm": use_llm,
            "use_graph": use_graph,
            "tools": tool_list or ["aderyn"],
        },
        daemon=True,
    )
    thread.start()
    return JSONResponse({"job_id": job_id})


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> JSONResponse:
    job_dir = RUNS_DIR / job_id
    status = _load_json(job_dir / "status.json") or {"status": "unknown"}
    progress = _load_json(job_dir / "progress.json")
    submission = _load_json(job_dir / "submission.json")
    error = _load_json(job_dir / "error.json")
    ipfs = _load_json(job_dir / "ipfs.json")
    return JSONResponse(
        {
            "job_id": job_id,
            "status": status.get("status"),
            "progress": progress,
            "submission": submission,
            "error": error,
            "ipfs": ipfs,
        }
    )


@app.get("/api/jobs/{job_id}/events")
def get_events(job_id: str, limit: int = 200) -> JSONResponse:
    job_dir = RUNS_DIR / job_id
    events_path = job_dir / "progress.jsonl"
    if not events_path.exists():
        return JSONResponse({"events": []})
    lines = events_path.read_text(encoding="utf-8").splitlines()
    events = [json.loads(line) for line in lines[-limit:]]
    return JSONResponse({"events": events})


@app.get("/api/jobs/{job_id}/artifacts")
def list_artifacts(job_id: str) -> JSONResponse:
    job_dir = RUNS_DIR / job_id
    available: list[str] = []
    for name in _allowed_artifacts():
        if (job_dir / name).exists():
            available.append(name)
    source = _find_source_file(job_dir)
    if source:
        available.append(source.name)
    return JSONResponse({"artifacts": sorted(available)})


@app.get("/api/jobs/{job_id}/artifact/{name}", response_model=None)
def get_artifact(job_id: str, name: str):
    job_dir = RUNS_DIR / job_id
    allowed = _allowed_artifacts()
    if name in allowed:
        path = job_dir / name
        if path.exists():
            return FileResponse(path)
        return JSONResponse({"error": "Not found"}, status_code=404)
    source = _find_source_file(job_dir)
    if source and name == source.name:
        return FileResponse(source)
    return JSONResponse({"error": "Not allowed"}, status_code=400)


# ---------------------------------------------------------------------------
# IPFS / Pinata endpoints
# ---------------------------------------------------------------------------


@app.post("/api/ipfs/pin/{job_id}")
def pin_job_report(job_id: str) -> JSONResponse:
    """Manually pin a completed job's submission to Pinata.

    Idempotent: if the report was already pinned, the existing CID is returned.
    """
    job_dir = RUNS_DIR / job_id
    if not job_dir.exists():
        return JSONResponse({"error": "Job not found"}, status_code=404)

    # Return existing pin if already done
    existing = _load_json(job_dir / "ipfs.json")
    if existing:
        return JSONResponse(existing)

    submission = _load_json(job_dir / "submission.json")
    if not submission:
        return JSONResponse(
            {"error": "No submission.json found – job may not be complete"},
            status_code=400,
        )

    try:
        cid = pin_json(submission, name=f"openaudit-{job_id}")
        gw_url = gateway_url(cid)
        ipfs_data = {"cid": cid, "gateway_url": gw_url}
        _write_json(job_dir / "ipfs.json", ipfs_data)
        registry.add_entry(
            cid=cid,
            job_id=job_id,
            title=submission.get("title", "Untitled"),
            severity=submission.get("severity", "UNKNOWN"),
            gateway_url=gw_url,
        )
        return JSONResponse(ipfs_data)
    except PinataError as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)


@app.get("/api/ipfs/reports")
def list_ipfs_reports() -> JSONResponse:
    """Return all pinned reports from the local CID registry."""
    entries = registry.list_entries()
    return JSONResponse({"reports": entries})


@app.post("/api/ipfs/pin")
async def pin_report(request: Request) -> JSONResponse:
    """Pin an arbitrary JSON report to IPFS and return its CID.

    This is the endpoint the agent should call **before** ``submitFinding``
    on-chain.  The flow is:

    1. Agent builds its bug-report JSON.
    2. ``POST /api/ipfs/pin`` with ``{ "report": <report_json>, "name": "<optional_name>" }``
    3. Server pins to Pinata, returns ``{ "cid": "...", "gateway_url": "..." }``.
    4. Agent calls ``submitFinding(bountyId, cid)`` on-chain.
    """
    body = await request.json()

    report = body.get("report")
    if not report or not isinstance(report, dict):
        return JSONResponse(
            {"error": "Missing or invalid 'report' field (must be a JSON object)"},
            status_code=400,
        )

    name = body.get("name", "openaudit-report")

    try:
        cid = pin_json(report, name=str(name))
        gw_url = gateway_url(cid)

        # Add to local registry
        registry.add_entry(
            cid=cid,
            job_id=name,
            title=report.get("title", "Untitled"),
            severity=report.get("severity", "UNKNOWN"),
            gateway_url=gw_url,
        )

        return JSONResponse({"cid": cid, "gateway_url": gw_url})
    except PinataError as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)
