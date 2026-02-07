"""Thread-safe CID registry – persists pinned-report metadata to a JSON file.

Each entry records the CID, originating job ID, title, severity, gateway URL,
and the timestamp when the report was pinned.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_lock = threading.Lock()

DEFAULT_REGISTRY_PATH = Path(__file__).resolve().parent.parent / "runs" / "ipfs_registry.json"


def _read(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _write(path: Path, entries: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(entries, indent=2), encoding="utf-8")
    tmp.replace(path)


def add_entry(
    cid: str,
    job_id: str,
    title: str,
    severity: str,
    gateway_url: str,
    *,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
) -> Dict[str, Any]:
    """Append a new entry to the registry and return it."""
    entry: Dict[str, Any] = {
        "cid": cid,
        "job_id": job_id,
        "title": title,
        "severity": severity,
        "gateway_url": gateway_url,
        "pinned_at": datetime.now(timezone.utc).isoformat(),
    }
    with _lock:
        entries = _read(registry_path)
        # Deduplicate by CID
        if any(e["cid"] == cid for e in entries):
            return entry
        entries.append(entry)
        _write(registry_path, entries)
    return entry


def list_entries(
    *,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
) -> List[Dict[str, Any]]:
    """Return all registry entries (newest first)."""
    with _lock:
        entries = _read(registry_path)
    return list(reversed(entries))


def get_entry(
    cid: str,
    *,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
) -> Optional[Dict[str, Any]]:
    """Look up a single entry by CID."""
    with _lock:
        entries = _read(registry_path)
    for entry in entries:
        if entry["cid"] == cid:
            return entry
    return None
