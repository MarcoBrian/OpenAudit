from __future__ import annotations

import json
import os
import shlex
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict


class AderynError(RuntimeError):
    pass


def _resolve_project_root(solidity_file: Path) -> Path:
    env_root = os.getenv("ADERYN_ROOT") or os.getenv("OPENAUDIT_PROJECT_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()

    candidate = solidity_file if solidity_file.is_dir() else solidity_file.parent
    try:
        result = subprocess.run(
            ["git", "-C", str(candidate), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return candidate.resolve()

    if result.returncode == 0:
        root = Path(result.stdout.strip())
        if root.exists():
            return root.resolve()
    return candidate.resolve()


def _build_command(
    *,
    root: Path,
    output_path: Path,
    include: str | None,
    solidity_file: Path,
) -> list[list[str]]:
    custom_cmd = os.getenv("ADERYN_CMD")
    if custom_cmd:
        formatted = custom_cmd.format(
            target=str(root),
            root=str(root),
            output=str(output_path),
            include=include or "",
            file=str(solidity_file),
        )
        return [shlex.split(formatted)]

    include_args: list[str] = []
    if include:
        include_args = ["--path-includes", include]

    return [
        ["aderyn", "--output", str(output_path), *include_args, str(root)],
        ["aderyn", "-o", str(output_path), *include_args, str(root)],
        ["aderyn", str(root), "--output", str(output_path), *include_args],
    ]


def run_aderyn(solidity_file: Path) -> Dict[str, Any]:
    if not solidity_file.exists():
        raise FileNotFoundError(f"Solidity file not found: {solidity_file}")

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir) / "aderyn.json"
        root = _resolve_project_root(solidity_file)
        include: str | None = None
        if solidity_file.is_file():
            try:
                include = str(solidity_file.resolve().relative_to(root))
            except ValueError:
                root = solidity_file.parent.resolve()
                include = solidity_file.name

        last_result = None
        for command in _build_command(
            root=root,
            output_path=temp_path,
            include=include,
            solidity_file=solidity_file,
        ):
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                cwd=str(root),
            )
            last_result = result
            if temp_path.exists():
                break
        else:
            result = last_result
            raise AderynError(
                "Aderyn failed. Ensure it is installed and the file compiles.\n"
                f"stdout:\n{result.stdout if result else ''}\n\n"
                f"stderr:\n{result.stderr if result else ''}"
            )

        try:
            with temp_path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except json.JSONDecodeError as exc:
            result = last_result
            raise AderynError(
                "Aderyn produced an invalid report.\n"
                f"stdout:\n{result.stdout if result else ''}\n\n"
                f"stderr:\n{result.stderr if result else ''}"
            ) from exc
