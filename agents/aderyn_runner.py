from __future__ import annotations

import json
import os
import shlex
import subprocess
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict


class AderynError(RuntimeError):
    pass


def _build_command(
    target: Path,
    output_path: Path,
) -> list[list[str]]:
    custom_cmd = os.getenv("ADERYN_CMD")
    if custom_cmd:
        formatted = custom_cmd.format(
            target=str(target),
            output=str(output_path),
        )
        return [shlex.split(formatted)]

    return [
        ["aderyn", str(target), "--output", str(output_path)],
        ["aderyn", "--output", str(output_path), str(target)],
        ["aderyn", "-o", str(output_path), str(target)],
    ]


def run_aderyn(solidity_file: Path) -> Dict[str, Any]:
    if not solidity_file.exists():
        raise FileNotFoundError(f"Solidity file not found: {solidity_file}")

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir) / "aderyn.json"
        if solidity_file.is_dir():
            target = solidity_file
        else:
            copied_path = Path(temp_dir) / solidity_file.name
            shutil.copy2(solidity_file, copied_path)
            target = Path(temp_dir)

        last_result = None
        for command in _build_command(target, temp_path):
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
            )
            last_result = result
            if result.returncode == 0 and temp_path.exists():
                break
        else:
            result = last_result
            raise AderynError(
                "Aderyn failed. Ensure it is installed and the file compiles.\n"
                f"stdout:\n{result.stdout if result else ''}\n\n"
                f"stderr:\n{result.stderr if result else ''}"
            )

        with temp_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

