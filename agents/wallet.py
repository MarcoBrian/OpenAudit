from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

try:
    from coinbase_agentkit import (
        AgentKit,
        AgentKitConfig,
        CdpEvmWalletProvider,
        CdpEvmWalletProviderConfig,
        EthAccountWalletProvider,
        EthAccountWalletProviderConfig,
        wallet_action_provider,
    )
    from coinbase_agentkit.network import NETWORK_ID_TO_CHAIN
except ImportError as exc:  # pragma: no cover - optional dependency
    AgentKit = None  # type: ignore[assignment]
    AgentKitConfig = None  # type: ignore[assignment]
    CdpEvmWalletProvider = None  # type: ignore[assignment]
    CdpEvmWalletProviderConfig = None  # type: ignore[assignment]
    EthAccountWalletProvider = None  # type: ignore[assignment]
    EthAccountWalletProviderConfig = None  # type: ignore[assignment]
    wallet_action_provider = None  # type: ignore[assignment]
    NETWORK_ID_TO_CHAIN = {}  # type: ignore[assignment]
    _AGENTKIT_IMPORT_ERROR = exc
else:
    _AGENTKIT_IMPORT_ERROR = None

try:
    from eth_account import Account  # type: ignore
except ImportError as exc:  # pragma: no cover - optional dependency
    Account = None  # type: ignore[assignment]
    _ETH_ACCOUNT_IMPORT_ERROR = exc
else:
    _ETH_ACCOUNT_IMPORT_ERROR = None


class WalletInitError(RuntimeError):
    pass


@dataclass
class WalletDetails:
    address: Optional[str] = None
    network_id: Optional[str] = None
    provider: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "address": self.address,
            "network_id": self.network_id,
            "provider": self.provider,
            "raw": self.raw or {},
        }


def _require_agentkit() -> None:
    if _AGENTKIT_IMPORT_ERROR is not None:
        raise WalletInitError(
            "coinbase-agentkit is not installed. "
            "Install it with: pip install coinbase-agentkit"
        ) from _AGENTKIT_IMPORT_ERROR


def _build_cdp_evm_wallet_provider() -> Any:
    api_key_id = os.getenv("CDP_API_KEY_ID")
    api_key_secret = os.getenv("CDP_API_KEY_SECRET")
    wallet_secret = os.getenv("CDP_WALLET_SECRET")
    network_id = os.getenv("CDP_NETWORK_ID", "base-sepolia")
    wallet_address = os.getenv("CDP_WALLET_ADDRESS")
    idempotency_key = os.getenv("CDP_IDEMPOTENCY_KEY")

    if not (api_key_id and api_key_secret and wallet_secret):
        raise WalletInitError(
            "Missing CDP credentials. Set CDP_API_KEY_ID, CDP_API_KEY_SECRET, "
            "and CDP_WALLET_SECRET to enable the AgentKit wallet provider."
        )

    config = CdpEvmWalletProviderConfig(
        api_key_id=api_key_id,
        api_key_secret=api_key_secret,
        wallet_secret=wallet_secret,
        network_id=network_id,
        address=wallet_address,
        idempotency_key=idempotency_key,
    )
    return CdpEvmWalletProvider(config)


def _build_eth_account_wallet_provider() -> Any:
    private_key = os.getenv("OPENAUDIT_WALLET_PRIVATE_KEY")
    if not private_key:
        raise WalletInitError(
            "Missing OPENAUDIT_WALLET_PRIVATE_KEY for EthAccountWalletProvider."
        )
    if Account is None:
        raise WalletInitError(
            "eth-account is required for OPENAUDIT_WALLET_PRIVATE_KEY support."
        ) from _ETH_ACCOUNT_IMPORT_ERROR

    network_id = os.getenv("OPENAUDIT_WALLET_NETWORK", "base-sepolia")
    chain_id = os.getenv("OPENAUDIT_WALLET_CHAIN_ID")
    rpc_url = os.getenv("OPENAUDIT_WALLET_RPC_URL")

    if not chain_id:
        chain = NETWORK_ID_TO_CHAIN.get(network_id)
        if chain is None:
            raise WalletInitError(
                "Unknown OPENAUDIT_WALLET_NETWORK. "
                "Set OPENAUDIT_WALLET_CHAIN_ID explicitly (e.g., 84532 for base-sepolia)."
            )
        chain_id = str(chain.id)

    account = Account.from_key(private_key)
    if EthAccountWalletProviderConfig is None:
        raise WalletInitError("EthAccountWalletProviderConfig is unavailable.")
    config = EthAccountWalletProviderConfig(
        account=account,
        chain_id=str(chain_id),
        rpc_url=rpc_url,
    )
    return EthAccountWalletProvider(config)


def _select_wallet_provider() -> Any:
    if os.getenv("CDP_API_KEY_ID"):
        return _build_cdp_evm_wallet_provider()
    if os.getenv("OPENAUDIT_WALLET_PRIVATE_KEY"):
        return _build_eth_account_wallet_provider()
    raise WalletInitError(
        "No wallet credentials found. "
        "Set CDP_API_KEY_ID/CDP_API_KEY_SECRET/CDP_WALLET_SECRET "
        "or OPENAUDIT_WALLET_PRIVATE_KEY."
    )


def create_agentkit() -> Any:
    _require_agentkit()
    if wallet_action_provider is None:
        raise WalletInitError("wallet_action_provider is unavailable in AgentKit.")

    wallet_provider = _select_wallet_provider()
    action_providers = [wallet_action_provider()]

    config = AgentKitConfig(
        wallet_provider=wallet_provider,
        action_providers=action_providers,
    )
    return AgentKit(config)


def _coerce_details(raw: Any) -> Dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    for attr in ("model_dump", "dict"):
        fn = getattr(raw, attr, None)
        if callable(fn):
            try:
                return fn()
            except Exception:
                pass
    return {"value": str(raw)}


def get_wallet_details() -> WalletDetails:
    agent = create_agentkit()
    provider = getattr(agent, "wallet_provider", None)
    details: Dict[str, Any] = {}

    if provider is not None:
        for attr in ("get_wallet_details", "get_details", "get_address", "address"):
            value = getattr(provider, attr, None)
            if callable(value):
                try:
                    details = _coerce_details(value())
                except Exception:
                    details = {}
                break
            if value is not None:
                details = {"address": value}
                break

    address = (
        details.get("address")
        or details.get("wallet_address")
        or os.getenv("CDP_WALLET_ADDRESS")
    )
    network_id = details.get("network_id") or os.getenv("CDP_NETWORK_ID")

    return WalletDetails(
        address=address,
        network_id=network_id,
        provider=provider.__class__.__name__ if provider is not None else None,
        raw=details,
    )
