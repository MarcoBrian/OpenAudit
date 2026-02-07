"""Pinata IPFS service – pin JSON payloads and build gateway URLs.

Uses the Pinata v3 Files API with JWT authentication.
Docs: https://docs.pinata.cloud/api-reference
"""

from __future__ import annotations

import io
import json
import logging
import os
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger(__name__)

PINATA_JWT: Optional[str] = os.getenv("PINATA_JWT")
PINATA_GATEWAY_URL: Optional[str] = os.getenv("PINATA_GATEWAY_URL")

PINATA_UPLOAD_URL = "https://uploads.pinata.cloud/v3/files"


class PinataError(Exception):
    """Raised when a Pinata API call fails."""


def _ensure_configured() -> str:
    """Return the JWT or raise if not configured."""
    jwt = PINATA_JWT or os.getenv("PINATA_JWT")
    if not jwt:
        raise PinataError("PINATA_JWT environment variable is not set")
    return jwt


def pin_json(data: Dict[str, Any], *, name: str = "openaudit-report") -> str:
    """Upload a JSON payload to Pinata and return its IPFS CID.

    The payload is uploaded as a ``.json`` file via the v3 Files endpoint.

    Parameters
    ----------
    data:
        Serialisable dict to store on IPFS.
    name:
        Human-readable name attached to the pin (shown in the Pinata dashboard).

    Returns
    -------
    str
        The IPFS CID (content identifier) of the pinned file.
    """
    jwt = _ensure_configured()

    json_bytes = json.dumps(data, indent=2).encode("utf-8")
    file_obj = io.BytesIO(json_bytes)
    file_obj.name = f"{name}.json"

    headers = {"Authorization": f"Bearer {jwt}"}

    try:
        resp = requests.post(
            PINATA_UPLOAD_URL,
            headers=headers,
            files={"file": (f"{name}.json", file_obj, "application/json")},
            data={"name": f"{name}.json"},
            timeout=30,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise PinataError(f"Pinata upload failed: {exc}") from exc

    body = resp.json()

    # v3 response: {"data": {"id": "...", "cid": "...", ...}}
    cid = body.get("data", {}).get("cid")
    if not cid:
        raise PinataError(f"Unexpected Pinata response (no CID): {body}")

    logger.info("Pinned %s → CID %s", name, cid)
    return cid


def gateway_url(cid: str) -> str:
    """Build the full gateway URL for a given CID.

    Uses ``PINATA_GATEWAY_URL`` if set, otherwise falls back to the
    public IPFS gateway.
    """
    base = PINATA_GATEWAY_URL or os.getenv("PINATA_GATEWAY_URL") or "https://gateway.pinata.cloud"
    base = base.rstrip("/")
    return f"{base}/ipfs/{cid}"
