from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import requests
from web3 import Web3


OPENAUDIT_REGISTRY_ABI = [
    {
        "inputs": [],
        "name": "nextBountyId",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "name": "bounties",
        "outputs": [
            {"internalType": "address", "name": "sponsor", "type": "address"},
            {"internalType": "address", "name": "targetContract", "type": "address"},
            {"internalType": "uint256", "name": "reward", "type": "uint256"},
            {"internalType": "uint256", "name": "deadline", "type": "uint256"},
            {"internalType": "bool", "name": "active", "type": "bool"},
            {"internalType": "bool", "name": "resolved", "type": "bool"},
            {"internalType": "address", "name": "winner", "type": "address"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
]


@dataclass(frozen=True)
class BountyDetails:
    bounty_id: int
    sponsor: str
    target_contract: str
    reward_usdc: int  # USDC amount in 6-decimal units (1 USDC = 1_000_000)
    deadline: int
    active: bool
    resolved: bool
    winner: str

    @property
    def reward_wei(self) -> int:
        """Backward-compatible alias."""
        return self.reward_usdc

    @property
    def reward_display(self) -> str:
        """Human-readable USDC amount."""
        return f"{self.reward_usdc / 1e6:.2f} USDC"


class RegistryClient:
    def __init__(self, rpc_url: str, registry_address: str) -> None:
        if not rpc_url:
            raise ValueError("RPC URL is required to access OpenAuditRegistry.")
        if not registry_address:
            raise ValueError("OpenAuditRegistry address is required.")
        self.web3 = Web3(Web3.HTTPProvider(rpc_url))
        if not self.web3.is_connected():
            raise ConnectionError("Unable to connect to RPC endpoint.")
        self.contract = self.web3.eth.contract(
            address=self.web3.to_checksum_address(registry_address),
            abi=OPENAUDIT_REGISTRY_ABI,
        )

    def total_bounties(self) -> int:
        next_id = int(self.contract.functions.nextBountyId().call())
        return max(0, next_id - 1)

    def get_bounty(self, bounty_id: int) -> BountyDetails:
        (
            sponsor,
            target_contract,
            reward,
            deadline,
            active,
            resolved,
            winner,
        ) = self.contract.functions.bounties(bounty_id).call()
        return BountyDetails(
            bounty_id=bounty_id,
            sponsor=sponsor,
            target_contract=target_contract,
            reward_usdc=int(reward),
            deadline=int(deadline),
            active=bool(active),
            resolved=bool(resolved),
            winner=winner,
        )


# Backwards-compatible alias
BountyClient = RegistryClient


def load_source_from_map(target_contract: str, source_map_path: Path) -> Path:
    payload = json.loads(source_map_path.read_text(encoding="utf-8"))
    key = target_contract.lower()
    source_path = payload.get(key)
    if not source_path:
        raise FileNotFoundError(
            f"Missing source mapping for {target_contract} in {source_map_path}."
        )
    source_file = Path(source_path).expanduser()
    if not source_file.exists():
        raise FileNotFoundError(f"Mapped source file not found: {source_file}")
    return source_file


def load_source_from_etherscan(target_contract: str) -> Path:
    api_url = os.getenv("ETHERSCAN_API_URL")
    api_key = os.getenv("ETHERSCAN_API_KEY")
    if not api_url or not api_key:
        raise ValueError(
            "ETHERSCAN_API_URL and ETHERSCAN_API_KEY must be set to fetch source."
        )
    response = requests.get(
        api_url,
        params={
            "module": "contract",
            "action": "getsourcecode",
            "address": target_contract,
            "apikey": api_key,
        },
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    result = payload.get("result") or []
    if not result:
        raise ValueError("No source returned from explorer API.")
    source_code = result[0].get("SourceCode") or ""
    if not source_code:
        raise ValueError("Explorer API returned empty source code.")

    source_content = _extract_source_content(source_code)
    temp_dir = Path(tempfile.mkdtemp(prefix="bounty_source_"))
    output_file = temp_dir / f"{target_contract}.sol"
    output_file.write_text(source_content, encoding="utf-8")
    return output_file


def _extract_source_content(source_code: str) -> str:
    trimmed = source_code.strip()
    if trimmed.startswith("{{") and trimmed.endswith("}}"):
        trimmed = trimmed[1:-1]
    if trimmed.startswith("{") and trimmed.endswith("}"):
        try:
            payload = json.loads(trimmed)
        except json.JSONDecodeError:
            return source_code
        sources = payload.get("sources")
        if isinstance(sources, dict) and sources:
            first_source = next(iter(sources.values()))
            content = first_source.get("content") if isinstance(first_source, dict) else None
            if content:
                return content
    return source_code
