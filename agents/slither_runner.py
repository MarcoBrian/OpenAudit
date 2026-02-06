from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict


class SlitherError(RuntimeError):
    pass


def _parse_version(text: str) -> tuple[int, int, int] | None:
    parts = text.strip().split(".")
    if not parts or not all(part.isdigit() for part in parts):
        return None
    while len(parts) < 3:
        parts.append("0")
    return int(parts[0]), int(parts[1]), int(parts[2])


def _constraint_allows(version: tuple[int, int, int], constraint: str) -> bool:
    if not constraint:
        return True

    constraint = constraint.replace(" ", "")
    if constraint.startswith("^"):
        base = _parse_version(constraint[1:])
        if not base:
            return False
        major, minor, patch = base
        if major > 0:
            upper = (major + 1, 0, 0)
        elif minor > 0:
            upper = (0, minor + 1, 0)
        else:
            upper = (0, 0, patch + 1)
        return base <= version < upper

    comparators = re.findall(r"(>=|<=|>|<|=)(\d+(?:\.\d+){0,2})", constraint)
    if comparators:
        for op, ver in comparators:
            parsed = _parse_version(ver)
            if not parsed:
                return False
            if op == ">=" and not (version >= parsed):
                return False
            if op == "<=" and not (version <= parsed):
                return False
            if op == ">" and not (version > parsed):
                return False
            if op == "<" and not (version < parsed):
                return False
            if op == "=" and not (version == parsed):
                return False
        return True

    parsed = _parse_version(constraint)
    if parsed:
        return version == parsed

    return True


def _detect_pragma(solidity_file: Path) -> str | None:
    pattern = re.compile(r"pragma\s+solidity\s+([^;]+);")
    with solidity_file.open("r", encoding="utf-8") as handle:
        for line in handle:
            match = pattern.search(line)
            if match:
                return match.group(1).strip()
    return None


def _select_solc_binary(solidity_file: Path) -> str | None:
    def resolve_solc_binary(folder: Path, version: str) -> str | None:
        direct = folder / "solc"
        if direct.exists():
            return str(direct)
        versioned = folder / f"solc-{version}"
        if versioned.exists():
            return str(versioned)
        return None

    version_override = os.getenv("SOLC_VERSION")
    if version_override:
        folder = (
            Path.home()
            / ".solc-select"
            / "artifacts"
            / f"solc-{version_override}"
        )
        candidate = resolve_solc_binary(folder, version_override)
        if candidate:
            return candidate

    override = os.getenv("SOLC_BIN")
    if override:
        return override

    pragma = _detect_pragma(solidity_file)
    if not pragma:
        return None

    artifacts_dir = Path.home() / ".solc-select" / "artifacts"
    if not artifacts_dir.exists():
        return None

    candidates: list[tuple[tuple[int, int, int], Path]] = []
    for item in artifacts_dir.glob("solc-*"):
        version_str = item.name.replace("solc-", "")
        parsed = _parse_version(version_str)
        if not parsed:
            continue
        solc_path = resolve_solc_binary(item, version_str)
        if solc_path:
            candidates.append((parsed, Path(solc_path)))

    if not candidates:
        return None

    candidates.sort(reverse=True)
    for version, path in candidates:
        if _constraint_allows(version, pragma):
            return str(path)

    return None


def run_slither(solidity_file: Path) -> Dict[str, Any]:
    if not solidity_file.exists():
        raise FileNotFoundError(f"Solidity file not found: {solidity_file}")

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir) / "slither.json"
        solc_path = _select_solc_binary(solidity_file)
        command = ["slither", str(solidity_file), "--json", str(temp_path)]
        if solc_path:
            command.extend(["--solc", solc_path])

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )

        if not temp_path.exists():
            raise SlitherError(
                "Slither failed. Ensure it is installed and the file compiles.\n"
                f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr}"
            )

        with temp_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
