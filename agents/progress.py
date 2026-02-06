from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass
class ProgressEvent:
    step: str
    status: str
    message: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "step": self.step,
            "status": self.status,
            "timestamp": self.timestamp or _utc_now(),
        }
        if self.message:
            payload["message"] = self.message
        if self.data is not None:
            payload["data"] = self.data
        return payload


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProgressReporter:
    def __init__(self, reports_dir: Path) -> None:
        self.reports_dir = reports_dir
        self.events_path = reports_dir / "progress.jsonl"
        self.state_path = reports_dir / "progress.json"
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def emit(
        self,
        *,
        step: str,
        status: str,
        message: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> None:
        event = ProgressEvent(step=step, status=status, message=message, data=data)
        payload = event.to_dict()
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload) + "\n")
        self.state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def start(self, step: str, message: Optional[str] = None) -> None:
        self.emit(step=step, status="running", message=message)

    def complete(self, step: str, message: Optional[str] = None) -> None:
        self.emit(step=step, status="completed", message=message)

    def fail(self, step: str, message: Optional[str] = None) -> None:
        self.emit(step=step, status="failed", message=message)
