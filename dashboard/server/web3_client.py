"""
web3_client.py — Read-only contract interactions for the dashboard backend.

Provides helpers to read bounties, agents, and ENS text records from
the OpenAuditRegistry deployed on Arc.
"""

from __future__ import annotations

import os
import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Minimal ABIs ──────────────────────────────────────────────────────────────

REGISTRY_ABI = json.loads("""[
  {"type":"function","name":"nextBountyId","inputs":[],"outputs":[{"name":"","type":"uint256"}],"stateMutability":"view"},
  {"type":"function","name":"nextAgentId","inputs":[],"outputs":[{"name":"","type":"uint256"}],"stateMutability":"view"},
  {"type":"function","name":"bounties","inputs":[{"name":"","type":"uint256"}],"outputs":[
    {"name":"sponsor","type":"address"},{"name":"targetContract","type":"address"},
    {"name":"reward","type":"uint256"},{"name":"deadline","type":"uint256"},
    {"name":"active","type":"bool"},{"name":"resolved","type":"bool"},
    {"name":"winner","type":"address"}
  ],"stateMutability":"view"},
  {"type":"function","name":"agents","inputs":[{"name":"","type":"uint256"}],"outputs":[
    {"name":"owner","type":"address"},{"name":"tba","type":"address"},
    {"name":"name","type":"string"},{"name":"metadataURI","type":"string"},
    {"name":"totalScore","type":"uint256"},{"name":"findingsCount","type":"uint256"},
    {"name":"registered","type":"bool"}
  ],"stateMutability":"view"},
  {"type":"function","name":"getPayoutChain","inputs":[{"name":"agentId","type":"uint256"}],"outputs":[{"name":"","type":"string"}],"stateMutability":"view"},
  {"type":"function","name":"getBountySubmitters","inputs":[{"name":"bountyId","type":"uint256"}],"outputs":[{"name":"","type":"address[]"}],"stateMutability":"view"},
  {"type":"function","name":"getReputation","inputs":[{"name":"agent","type":"address"}],"outputs":[
    {"name":"totalScore","type":"uint256"},{"name":"findingsCount","type":"uint256"},{"name":"avgScore","type":"uint256"}
  ],"stateMutability":"view"},
  {"type":"function","name":"ownerToAgentId","inputs":[{"name":"","type":"address"}],"outputs":[{"name":"","type":"uint256"}],"stateMutability":"view"},
  {"type":"function","name":"tbaToAgentId","inputs":[{"name":"","type":"address"}],"outputs":[{"name":"","type":"uint256"}],"stateMutability":"view"},
  {"type":"function","name":"usdc","inputs":[],"outputs":[{"name":"","type":"address"}],"stateMutability":"view"},
  {"type":"function","name":"payoutRelay","inputs":[],"outputs":[{"name":"","type":"address"}],"stateMutability":"view"}
]""")


def _get_web3():
    """Lazy import and init web3 to avoid hard dependency if not configured."""
    try:
        from web3 import Web3
    except ImportError:
        raise RuntimeError("web3 package not installed. pip install web3")

    rpc_url = os.getenv("ARC_TESTNET_RPC_URL") or os.getenv("RPC_URL", "")
    if not rpc_url:
        raise RuntimeError("ARC_TESTNET_RPC_URL or RPC_URL not set")

    return Web3(Web3.HTTPProvider(rpc_url))


def _get_registry():
    w3 = _get_web3()
    addr = os.getenv("OPENAUDIT_REGISTRY_ADDRESS", "")
    if not addr:
        raise RuntimeError("OPENAUDIT_REGISTRY_ADDRESS not set")
    return w3.eth.contract(address=w3.to_checksum_address(addr), abi=REGISTRY_ABI)


# ── Public API ────────────────────────────────────────────────────────────────


def list_bounties(limit: int = 50) -> List[Dict[str, Any]]:
    """Return all bounties from the registry."""
    contract = _get_registry()
    next_id = contract.functions.nextBountyId().call()
    results = []
    for i in range(1, min(next_id, limit + 1)):
        try:
            b = contract.functions.bounties(i).call()
            results.append({
                "id": i,
                "sponsor": b[0],
                "targetContract": b[1],
                "reward": str(b[2]),
                "reward_usdc": b[2] / 1e6,
                "deadline": b[3],
                "active": b[4],
                "resolved": b[5],
                "winner": b[6],
            })
        except Exception as e:
            logger.warning("Failed to read bounty %d: %s", i, e)
    return results


def list_agents(limit: int = 50) -> List[Dict[str, Any]]:
    """Return all registered agents with their payout chain."""
    contract = _get_registry()
    next_id = contract.functions.nextAgentId().call()
    results = []
    for i in range(1, min(next_id, limit + 1)):
        try:
            a = contract.functions.agents(i).call()
            if not a[6]:  # not registered
                continue
            payout_chain = ""
            try:
                payout_chain = contract.functions.getPayoutChain(i).call()
            except Exception:
                pass
            results.append({
                "id": i,
                "owner": a[0],
                "tba": a[1],
                "name": a[2],
                "metadataURI": a[3],
                "totalScore": a[4],
                "findingsCount": a[5],
                "avgScore": a[4] // a[5] if a[5] > 0 else 0,
                "payout_chain": payout_chain,
            })
        except Exception as e:
            logger.warning("Failed to read agent %d: %s", i, e)
    return results


def get_agent_payout_chain(name: str) -> Optional[str]:
    """Look up an agent's payout chain by name."""
    contract = _get_registry()
    agent_id = contract.functions.ownerToAgentId(name).call()
    if agent_id == 0:
        return None
    return contract.functions.getPayoutChain(agent_id).call()
