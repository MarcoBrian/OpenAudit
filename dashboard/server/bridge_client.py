"""
bridge_client.py — HTTP client for the Bridge Kit microservice.

Calls the Node.js Bridge Kit service to execute cross-chain USDC transfers
after bounty resolution. The contracts live on Base Sepolia; payouts are
routed to the winner's preferred chain using Circle Bridge Kit (CCTP).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

# Default service URL (overridable via env)
BRIDGE_SERVICE_URL = os.getenv("BRIDGE_SERVICE_URL", "http://localhost:3001")


class BridgeError(Exception):
    """Raised when a bridge operation fails."""
    pass


class BridgeClient:
    """HTTP client for the OpenAudit Bridge Kit service."""

    def __init__(self, base_url: Optional[str] = None, timeout: float = 300.0):
        self.base_url = (base_url or BRIDGE_SERVICE_URL).rstrip("/")
        self.timeout = timeout  # Bridge can take minutes for attestation

    async def health(self) -> Dict[str, Any]:
        """Check bridge service health."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{self.base_url}/health")
            resp.raise_for_status()
            return resp.json()

    async def list_chains(self) -> List[Dict[str, Any]]:
        """List supported destination chains."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{self.base_url}/chains")
            resp.raise_for_status()
            data = resp.json()
            return data.get("supportedDestinations", [])

    async def bridge(
        self,
        *,
        amount: str,
        recipient: str,
        destination_chain: str,
    ) -> Dict[str, Any]:
        """
        Execute a cross-chain USDC bridge from Base Sepolia.

        Args:
            amount: USDC amount as string (e.g. "100.00")
            recipient: Destination wallet address
            destination_chain: ENS payout_chain value or Bridge Kit chain name

        Returns:
            Bridge result dict with bridge_id, status, steps, etc.
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/bridge",
                json={
                    "amount": amount,
                    "recipient": recipient,
                    "destination_chain": destination_chain,
                },
            )
            if resp.status_code >= 400:
                data = resp.json()
                raise BridgeError(data.get("error", f"Bridge failed: {resp.status_code}"))
            return resp.json()

    async def settle(
        self,
        *,
        bounty_id: str,
        winner: str,
        reward_usdc: str,
        payout_chain: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Process a bounty settlement — resolves ENS payout chain + bridges.

        If payout_chain is not provided, the bridge service will read it
        from the winner's ENS subname text record on-chain.

        Args:
            bounty_id: The bounty ID
            winner: Winner's address (owner or TBA)
            reward_usdc: USDC amount as string (e.g. "100.00")
            payout_chain: Optional override for destination chain

        Returns:
            Settlement result with bridge details.
        """
        payload: Dict[str, Any] = {
            "bounty_id": bounty_id,
            "winner": winner,
            "reward_usdc": reward_usdc,
        }
        if payout_chain:
            payload["payout_chain"] = payout_chain

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(f"{self.base_url}/settle", json=payload)
            if resp.status_code >= 400:
                data = resp.json()
                raise BridgeError(data.get("error", f"Settlement failed: {resp.status_code}"))
            return resp.json()

    async def get_bridge_status(self, bridge_id: str) -> Dict[str, Any]:
        """Check bridge status by ID."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(f"{self.base_url}/bridge/{bridge_id}")
            if resp.status_code == 404:
                return {"status": "not_found"}
            resp.raise_for_status()
            return resp.json()

    async def get_settlement_status(self, bounty_id: str) -> Dict[str, Any]:
        """Check settlement status by bounty ID."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(f"{self.base_url}/settle/{bounty_id}")
            if resp.status_code == 404:
                return {"status": "not_found"}
            resp.raise_for_status()
            return resp.json()

    async def get_payout_chain(self, address: str) -> Dict[str, Any]:
        """Read an agent's preferred payout chain from ENS."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(f"{self.base_url}/payout-chain/{address}")
            resp.raise_for_status()
            return resp.json()

    async def estimate_fees(
        self, amount: str = "1.00", destination_chain: str = "ethereum"
    ) -> Dict[str, Any]:
        """Estimate bridge fees."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self.base_url}/estimate",
                json={"amount": amount, "destination_chain": destination_chain},
            )
            resp.raise_for_status()
            return resp.json()


# Synchronous wrappers for non-async contexts
def _sync_bridge(
    *,
    amount: str,
    recipient: str,
    destination_chain: str,
    base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Synchronous bridge call using httpx."""
    url = (base_url or BRIDGE_SERVICE_URL).rstrip("/")
    with httpx.Client(timeout=300.0) as client:
        resp = client.post(
            f"{url}/bridge",
            json={
                "amount": amount,
                "recipient": recipient,
                "destination_chain": destination_chain,
            },
        )
        if resp.status_code >= 400:
            data = resp.json()
            raise BridgeError(data.get("error", f"Bridge failed: {resp.status_code}"))
        return resp.json()


def _sync_settle(
    *,
    bounty_id: str,
    winner: str,
    reward_usdc: str,
    payout_chain: Optional[str] = None,
    base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Synchronous settlement call using httpx."""
    url = (base_url or BRIDGE_SERVICE_URL).rstrip("/")
    payload: Dict[str, Any] = {
        "bounty_id": bounty_id,
        "winner": winner,
        "reward_usdc": reward_usdc,
    }
    if payout_chain:
        payload["payout_chain"] = payout_chain

    with httpx.Client(timeout=300.0) as client:
        resp = client.post(f"{url}/settle", json=payload)
        if resp.status_code >= 400:
            data = resp.json()
            raise BridgeError(data.get("error", f"Settlement failed: {resp.status_code}"))
        return resp.json()
