from __future__ import annotations

from dataclasses import dataclass

from web3 import Web3


OPENAUDIT_SUBMISSION_ABI = [
    {
        "inputs": [
            {"internalType": "uint256", "name": "bountyId", "type": "uint256"},
            {"internalType": "string", "name": "reportCID", "type": "string"},
        ],
        "name": "submitFinding",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]


@dataclass(frozen=True)
class SubmissionInputs:
    bounty_id: int
    report_cid: str


class BountySubmissionClient:
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
            abi=OPENAUDIT_SUBMISSION_ABI,
        )

    def submit_finding(
        self,
        *,
        private_key: str,
        bounty_id: int,
        report_cid: str,
    ) -> str:
        account = self.web3.eth.account.from_key(private_key)
        nonce = self.web3.eth.get_transaction_count(account.address)
        tx = self.contract.functions.submitFinding(
            bounty_id,
            report_cid,
        ).build_transaction(
            {
                "from": account.address,
                "nonce": nonce,
                "chainId": self.web3.eth.chain_id,
                "gas": 300_000,
            }
        )
        signed = account.sign_transaction(tx)
        raw_tx = getattr(signed, "raw_transaction", None) or getattr(signed, "rawTransaction", None)
        if raw_tx is None:
            raise AttributeError("SignedTransaction missing raw transaction bytes")
        tx_hash = self.web3.eth.send_raw_transaction(raw_tx)
        return tx_hash.hex()


# Backwards-compatible alias
RegistrySubmissionClient = BountySubmissionClient
