from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List

import requests

from agents.ollama_client import call_ollama


def _truncate(text: str, limit: int = 8000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...<truncated>"


def _call_llm(
    *,
    prompt: str,
    api_key: str,
    base_url: str,
    model: str,
    timeout: int = 60,
) -> List[Dict[str, Any]]:
    response = requests.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        },
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    content = payload["choices"][0]["message"]["content"]
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM response was not valid JSON: {content}") from exc


def logic_review(
    *,
    solidity_file: Path,
    triaged_findings: List[Dict[str, Any]],
    max_issues: int = 1,
) -> List[Dict[str, Any]]:
    api_key = os.getenv("OPENAI_API_KEY")
    ollama_model = os.getenv("OLLAMA_MODEL")
    print(ollama_model)
    if not api_key and not ollama_model:
        return []

    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    contract_text = solidity_file.read_text(encoding="utf-8")
    triage_summary = json.dumps(triaged_findings, indent=2)

    prompt = (
        "You are a smart-contract security reviewer focused on logic bugs that "
        "can drain funds or break core invariants. Given the Solidity code and "
        "existing static-tool findings, identify at most "
        f"{max_issues} additional high-impact logic issue(s).\n\n"
        "Return a JSON array of objects with fields: title, severity, confidence, "
        "description, impact, remediation, repro.\n"
        "Use severity in [LOW, MEDIUM, HIGH, CRITICAL]. Confidence is 0-1.\n"
        "If no additional logic issues are found, return an empty array.\n\n"
        "Existing findings:\n"
        f"{triage_summary}\n\n"
        "Solidity code:\n"
        f"{_truncate(contract_text)}"
    )

    try:
        if api_key:
            return _call_llm(
                prompt=prompt,
                api_key=api_key,
                base_url=base_url,
                model=model,
            )
        return call_ollama(prompt=prompt, model=ollama_model)
    except (requests.RequestException, ValueError):
        return []
