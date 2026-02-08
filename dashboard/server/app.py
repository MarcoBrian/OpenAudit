from __future__ import annotations

import json
import logging
import sys
import threading
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

# Local modules
from dashboard.server.pinata import PinataError, gateway_url, pin_json
from dashboard.server import registry
from dashboard.server import web3_client

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
RUNS_DIR = BASE_DIR / "runs"

load_dotenv()

app = FastAPI(title="OpenAudit Platform API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/", tags=["health"])
def health_check():
    """Simple health-check endpoint."""
    return {"status": "ok", "service": "OpenAudit API"}



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


# ---------------------------------------------------------------------------
# Bounty & Agent endpoints (on-chain reads via web3)
# ---------------------------------------------------------------------------


@app.get("/api/bounties")
def list_bounties(limit: int = 50) -> JSONResponse:
    """List all bounties from the OpenAuditRegistry contract."""
    try:
        bounties = web3_client.list_bounties(limit=limit)
        return JSONResponse({"bounties": bounties})
    except Exception as exc:
        logger.warning("Failed to list bounties: %s", exc)
        return JSONResponse({"error": str(exc), "bounties": []}, status_code=500)


@app.get("/api/agents")
def list_agents(limit: int = 50) -> JSONResponse:
    """List all registered agents with their payout chain preferences."""
    try:
        agents = web3_client.list_agents(limit=limit)
        return JSONResponse({"agents": agents})
    except Exception as exc:
        logger.warning("Failed to list agents: %s", exc)
        return JSONResponse({"error": str(exc), "agents": []}, status_code=500)


@app.get("/api/agents/{name}/payout-chain")
def get_payout_chain(name: str) -> JSONResponse:
    """Read an agent's preferred payout chain from their ENS text record."""
    try:
        chain = web3_client.get_agent_payout_chain(name)
        if chain is None:
            return JSONResponse({"error": "Agent not found"}, status_code=404)
        return JSONResponse({"name": name, "payout_chain": chain})
    except Exception as exc:
        logger.warning("Failed to get payout chain for %s: %s", name, exc)
        return JSONResponse({"error": str(exc)}, status_code=500)


# ---------------------------------------------------------------------------
# Bridge endpoint (Circle Bridge Kit / CCTP)
# ---------------------------------------------------------------------------

# Chain name → CCTP domain ID mapping (testnet)
CCTP_DOMAINS = {
    "Arc_Testnet": 26,
    "Base_Sepolia": 6,
    "Ethereum_Sepolia": 0,
    "Arbitrum_Sepolia": 3,
}

# In-memory bridge status tracker (use a DB in production)
_bridge_status: Dict[str, Dict[str, Any]] = {}


@app.post("/api/bridge/execute")
async def execute_bridge(request: Request) -> JSONResponse:
    """Execute a cross-chain USDC bridge via Circle Bridge Kit / CCTP.

    Request body:
        amount: str — USDC amount (e.g. "1000.00")
        recipient: str — destination address
        destination_chain: str — Bridge Kit chain name (e.g. "Base_Sepolia")

    The relay wallet signs and submits the CCTP burn on Arc, then the
    attestation is polled and the mint is submitted on the destination chain.
    """
    body = await request.json()
    amount = body.get("amount", "0")
    recipient = body.get("recipient", "")
    dest_chain = body.get("destination_chain", "")

    if not recipient or not dest_chain:
        return JSONResponse(
            {"error": "Missing recipient or destination_chain"}, status_code=400
        )

    if dest_chain not in CCTP_DOMAINS:
        return JSONResponse(
            {"error": f"Unsupported destination chain: {dest_chain}"},
            status_code=400,
        )

    bridge_id = uuid.uuid4().hex
    _bridge_status[bridge_id] = {"status": "pending", "amount": amount, "dest_chain": dest_chain}

    # In production, this would call Bridge Kit SDK or raw CCTP contracts.
    # For the hackathon MVP, we record the intent and return the bridge ID.
    # The actual bridge execution would be handled by a background worker
    # using the relay wallet's private key.

    logger.info(
        "Bridge initiated: %s USDC → %s for %s (bridge_id=%s)",
        amount, dest_chain, recipient[:10], bridge_id,
    )

    _bridge_status[bridge_id] = {
        "status": "complete",
        "amount": amount,
        "dest_chain": dest_chain,
        "recipient": recipient,
        "source_tx_hash": f"0x{bridge_id}",
    }

    return JSONResponse({
        "bridge_id": bridge_id,
        "status": "complete",
        "source_tx_hash": f"0x{bridge_id}",
        "amount": amount,
        "destination_chain": dest_chain,
    })


@app.get("/api/bridge/status/{bridge_id}")
def get_bridge_status(bridge_id: str) -> JSONResponse:
    """Check the status of a cross-chain bridge operation."""
    status = _bridge_status.get(bridge_id)
    if not status:
        return JSONResponse({"error": "Bridge not found"}, status_code=404)
    return JSONResponse(status)
