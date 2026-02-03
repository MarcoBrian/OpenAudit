from __future__ import annotations

import json
import os
from typing import Any, Dict, List

import requests


def _extract_items(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("findings", "results", "data", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _auth_headers() -> Dict[str, str]:
    api_key = os.getenv("SOLODIT_API_KEY")
    if not api_key:
        return {}
    header = os.getenv("SOLODIT_AUTH_HEADER", "X-Cyfrin-API-Key")
    prefix = os.getenv("SOLODIT_AUTH_PREFIX", "")
    value = f"{prefix} {api_key}".strip() if prefix else api_key
    return {header: value}


def _build_reference(item: Dict[str, Any], base_url: str) -> Dict[str, str]:
    url = (
        item.get("source_link")
        or item.get("url")
        or item.get("link")
        or item.get("solodit_url")
    )
    if not url:
        slug = item.get("slug") or item.get("id") or item.get("finding_id")
        if slug:
            url = f"{base_url.rstrip('/')}/findings/{slug}"
    title = item.get("title") or item.get("name") or "Solodit finding"
    impact = item.get("impact")
    firm = item.get("firm_name") or item.get("firm")
    if impact or firm:
        meta = ", ".join(
            value for value in [impact, firm] if value
        )
        title = f"{title} ({meta})"
    if not url:
        return {"source": "Solodit", "url": "", "note": title}
    return {"source": "Solodit", "url": url, "note": title}


def _rate_limit_info(headers: Dict[str, str]) -> Dict[str, str]:
    limit = headers.get("X-RateLimit-Limit")
    remaining = headers.get("X-RateLimit-Remaining")
    reset = headers.get("X-RateLimit-Reset")
    info: Dict[str, str] = {}
    if limit:
        info["limit"] = limit
    if remaining:
        info["remaining"] = remaining
    if reset:
        info["reset"] = reset
    return info


def build_references(issue_title: str) -> List[Dict[str, str]]:
    base_url = os.getenv("SOLODIT_BASE_URL", "https://solodit.cyfrin.io/api/v1/solodit")
    endpoint = os.getenv("SOLODIT_FINDINGS_ENDPOINT", "/findings")
    page = int(os.getenv("SOLODIT_PAGE", "1"))
    page_size = int(os.getenv("SOLODIT_PAGE_SIZE", "10"))
    impacts_raw = os.getenv("SOLODIT_IMPACTS", "")
    impacts = [value.strip().upper() for value in impacts_raw.split(",") if value.strip()]
    sort_field = os.getenv("SOLODIT_SORT_FIELD")
    sort_direction = os.getenv("SOLODIT_SORT_DIRECTION")
    quality_score = os.getenv("SOLODIT_QUALITY_SCORE")
    rarity_score = os.getenv("SOLODIT_RARITY_SCORE")
    tags_raw = os.getenv("SOLODIT_TAGS", "")
    protocol_categories_raw = os.getenv("SOLODIT_PROTOCOL_CATEGORIES", "")
    filters_json = os.getenv("SOLODIT_FILTERS_JSON", "")

    if not os.getenv("SOLODIT_API_KEY"):
        return []

    try:
        filters: Dict[str, Any] = {"keywords": issue_title}
        if impacts:
            filters["impact"] = impacts
        if sort_field:
            filters["sortField"] = sort_field
        if sort_direction:
            filters["sortDirection"] = sort_direction
        if quality_score:
            filters["qualityScore"] = int(quality_score)
        if rarity_score:
            filters["rarityScore"] = int(rarity_score)
        if tags_raw:
            filters["tags"] = [{"value": tag.strip()} for tag in tags_raw.split(",") if tag.strip()]
        if protocol_categories_raw:
            filters["protocolCategory"] = [
                {"value": value.strip()}
                for value in protocol_categories_raw.split(",")
                if value.strip()
            ]
        if filters_json:
            try:
                parsed = json.loads(filters_json)
                if isinstance(parsed, dict):
                    filters.update(parsed)
            except json.JSONDecodeError:
                pass

        body: Dict[str, Any] = {
            "page": page,
            "pageSize": page_size,
            "filters": filters,
        }

        response = requests.post(
            f"{base_url.rstrip('/')}{endpoint}",
            headers={"Content-Type": "application/json", **_auth_headers()},
            json=body,
            timeout=30,
        )
        if response.status_code == 429:
            rate_info = _rate_limit_info(response.headers)
            note = "Solodit rate limit reached"
            if rate_info:
                details = ", ".join(f"{key}={value}" for key, value in rate_info.items())
                note = f"{note} ({details})"
            return [
                {
                    "source": "Solodit",
                    "url": f"{base_url.rstrip('/')}{endpoint}",
                    "note": note,
                }
            ]
        response.raise_for_status()
        items = _extract_items(response.json())
        if not items:
            return []
        return [_build_reference(item, base_url) for item in items]
    except requests.RequestException:
        return []

