from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional

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


# Cache for Solodit tags to avoid repeated API calls
_solodit_tags_cache: Optional[set[str]] = None


def _normalize_tag(tag: str) -> list[str]:
    """Normalize a tag string into individual words."""
    # Convert to lowercase and split on spaces/hyphens
    normalized = re.sub(r'[-\s]+', ' ', str(tag).lower().strip())
    # Split into words and filter empty strings
    words = [w for w in normalized.split() if w]
    return words


def _extract_tags_from_findings(items: List[Dict[str, Any]]) -> set[str]:
    """Extract tags from Solodit findings and add them to the cache."""
    global _solodit_tags_cache
    
    if not items:
        return set()
    
    tags: set[str] = set()
    
    for item in items:
        # Extract tags from various possible fields
        tag_fields = [
            item.get("tags"),
            item.get("tag"),
            item.get("categories"),
            item.get("category"),
            item.get("vulnerability_type"),
            item.get("vuln_type"),
            item.get("type"),
        ]
        
        for tag_field in tag_fields:
            if isinstance(tag_field, list):
                for tag_item in tag_field:
                    if isinstance(tag_item, dict):
                        tag_value = (
                            tag_item.get("value")
                            or tag_item.get("name")
                            or tag_item.get("tag")
                            or tag_item.get("label")
                            or tag_item.get("title")
                        )
                        if tag_value:
                            tag_str = str(tag_value).lower()
                            tags.add(tag_str)
                            tags.update(_normalize_tag(tag_str))
                    elif isinstance(tag_item, str):
                        tag_str = tag_item.lower()
                        tags.add(tag_str)
                        tags.update(_normalize_tag(tag_str))
            elif isinstance(tag_field, str):
                tag_str = tag_field.lower()
                tags.add(tag_str)
                tags.update(_normalize_tag(tag_str))
        
        # Also extract keywords from title and description
        title = item.get("title") or item.get("name") or ""
        description = item.get("description") or item.get("summary") or ""
        
        if title:
            # Extract meaningful words from title (3+ chars)
            title_words = re.findall(r'\b[a-z]{3,}\b', title.lower())
            tags.update(title_words)
        
        if description:
            # Extract meaningful words from description (4+ chars to avoid noise)
            desc_words = re.findall(r'\b[a-z]{4,}\b', description.lower())
            tags.update(desc_words)
    
    # Update cache with new tags
    if _solodit_tags_cache is None:
        _solodit_tags_cache = tags.copy()
    else:
        _solodit_tags_cache.update(tags)
    
    return tags


def _get_solodit_tags() -> set[str]:
    """Get vulnerability tags, using cached tags or fallback."""
    global _solodit_tags_cache
    
    # Return cached tags if available
    if _solodit_tags_cache is not None:
        return _solodit_tags_cache
    
    # Initialize with fallback tags
    _solodit_tags_cache = {
        "reentrancy", "overflow", "underflow", "access", "control", "ownership",
        "hijack", "drain", "drainage", "withdraw", "transfer", "approval", "allowance",
        "race", "condition", "frontrun", "front-run", "mev", "flashloan", "flash", "loan",
        "governance", "centralization", "privilege", "permission", "authorization",
        "injection", "dos", "denial", "service", "gas", "limit", "unbounded", "loop",
        "timestamp", "block", "number", "randomness", "oracle", "price", "manipulation",
        "signature", "replay", "nonce", "tx", "origin", "sender", "call", "delegatecall",
        "selfdestruct", "suicide", "uninitialized", "storage", "variable", "proxy",
        "upgrade", "initialization", "constructor", "fallback", "receive"
    }
    return _solodit_tags_cache


def _extract_keywords(text: str, max_words: int = 10) -> str:
    """Extract key terms from text, focusing on vulnerability-related words from Solodit tags."""
    if not text:
        return ""
    
    # Get vulnerability keywords from Solodit tags (or fallback)
    vuln_keywords = _get_solodit_tags()
    
    # Common stop words to filter out
    stop_words = {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with",
        "by", "from", "as", "is", "are", "was", "were", "be", "been", "being", "have", "has",
        "had", "do", "does", "did", "will", "would", "should", "could", "may", "might",
        "this", "that", "these", "those", "it", "its", "they", "them", "their", "can",
        "function", "functions", "contract", "contracts", "address", "addresses", "value",
        "values", "call", "calls", "send", "sends", "allow", "allows", "make", "makes"
    }
    
    # Remove common stop words and punctuation
    words = re.findall(r'\b[a-z]+\b', text.lower())
    
    # Filter out stop words and very short words
    words = [w for w in words if w not in stop_words and len(w) > 3]
    
    # Prioritize vulnerability keywords, then take other significant words
    prioritized = [w for w in words if w in vuln_keywords]
    other_words = [w for w in words if w not in vuln_keywords]
    
    # Combine: vulnerability keywords first (up to max_words), then other significant words
    # But limit total to max_words
    keywords = prioritized[:max_words] + other_words[:max(0, max_words - len(prioritized))]
    return " ".join(keywords[:max_words])


def _map_severity_to_impact(severity: str) -> List[str]:
    """Map our severity levels to Solodit impact levels."""
    severity_upper = severity.upper()
    mapping = {
        "CRITICAL": ["CRITICAL", "HIGH"],
        "HIGH": ["HIGH", "MEDIUM"],
        "MEDIUM": ["MEDIUM", "LOW"],
        "LOW": ["LOW", "INFO"],
        "INFO": ["INFO", "LOW"]
    }
    return mapping.get(severity_upper, [])


def build_references(
    issue_title: str,
    description: str = "",
    impact: str = "",
    severity: str = "",
) -> List[Dict[str, str]]:
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

    api_key = os.getenv("SOLODIT_API_KEY")
    if not api_key:
        # Return empty list if no API key is configured
        # You can set SOLODIT_API_KEY in your .env file or environment
        return []

    try:
        # Build a richer query from title, description, and impact
        query_parts = [issue_title]
        
        # Extract keywords from description and impact
        desc_keywords = _extract_keywords(description, max_words=5)
        impact_keywords = _extract_keywords(impact, max_words=5)
        
        if desc_keywords:
            query_parts.append(desc_keywords)
        if impact_keywords:
            query_parts.append(impact_keywords)
        
        # Combine into a single query (Solodit API may support multi-term search)
        keywords_query = " ".join(query_parts)
        
        # Debug: log the query being sent
        if os.getenv("SOLODIT_DEBUG"):
            import sys
            print(f"Solodit query: {keywords_query}", file=sys.stderr)
            print(f"Query parts: {query_parts}", file=sys.stderr)
        
        filters: Dict[str, Any] = {"keywords": keywords_query}
        
        # Map severity to impact levels if not explicitly set
        if not impacts and severity:
            mapped_impacts = _map_severity_to_impact(severity)
            if mapped_impacts:
                impacts = mapped_impacts
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

        # Debug: log the request body
        if os.getenv("SOLODIT_DEBUG"):
            import sys
            import json as json_module
            print(f"Solodit request body: {json_module.dumps(body, indent=2)}", file=sys.stderr)

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
        response_data = response.json()
        items = _extract_items(response_data)
        
        # Debug: log if no items found
        if not items:
            # Check if response has any useful info
            if os.getenv("DEBUG") or os.getenv("SOLODIT_DEBUG"):
                import sys
                print(f"Solodit API returned no items.", file=sys.stderr)
                print(f"Response type: {type(response_data)}", file=sys.stderr)
                if isinstance(response_data, dict):
                    print(f"Response keys: {list(response_data.keys())}", file=sys.stderr)
                    # Show first 500 chars of response for debugging
                    import json
                    print(f"Response preview: {json.dumps(response_data, indent=2)[:500]}", file=sys.stderr)
                elif isinstance(response_data, list):
                    print(f"Response is a list with {len(response_data)} items", file=sys.stderr)
            return []
        
        # Extract tags from findings to build up our tag cache
        _extract_tags_from_findings(items)
        
        return [_build_reference(item, base_url) for item in items]
    except requests.HTTPError as e:
        # Log HTTP errors (401, 403, 404, 500, etc.)
        import sys
        error_msg = f"Solodit API HTTP error: {e.response.status_code} - {e.response.text[:200] if e.response else str(e)}"
        if os.getenv("DEBUG") or os.getenv("SOLODIT_DEBUG"):
            print(error_msg, file=sys.stderr)
        return []
    except requests.RequestException as e:
        # Log other request errors (network, timeout, etc.)
        import sys
        if os.getenv("DEBUG") or os.getenv("SOLODIT_DEBUG"):
            print(f"Solodit API request error: {e}", file=sys.stderr)
        return []
    except Exception as e:
        # Catch any other unexpected errors
        import sys
        if os.getenv("DEBUG") or os.getenv("SOLODIT_DEBUG"):
            print(f"Solodit API unexpected error: {e}", file=sys.stderr)
        return []

