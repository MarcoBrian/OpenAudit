from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def write_report(tool: str, report_json: Dict[str, Any], reports_dir: Path) -> Path:
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / f"{tool}_report.json"
    report_path.write_text(json.dumps(report_json, indent=2), encoding="utf-8")
    return report_path


def write_json(filename: str, payload: Any, reports_dir: Path) -> Path:
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / filename
    report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return report_path
