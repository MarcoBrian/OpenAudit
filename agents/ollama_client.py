from __future__ import annotations

import json
import os
from typing import Any, Dict, List

try:
    import ollama
except (ImportError, Exception):  # pragma: no cover - optional dependency
    # Catch all exceptions during import (e.g., pydantic version conflicts)
    ollama = None


def call_ollama(
    *,
    prompt: str,
    model: str,
    base_url: str | None = None,
    timeout: int = 60,
) -> List[Dict[str, Any]]:
    api_base = base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    api_key = os.getenv("OLLAMA_API_KEY")
    if ollama is None:
        raise RuntimeError("ollama python library is not installed")

    headers = None
    if api_key:
        headers = {"Authorization": f"Bearer {api_key}"}

    client = ollama.Client(host=api_base, headers=headers)
    payload = client.chat(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        options={"num_ctx": 8192},
    )
    content = payload.get("message", {}).get("content", "")
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Ollama response was not valid JSON: {content}") from exc
