from __future__ import annotations

import json
import logging
import sys
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, File, Form, UploadFile
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
