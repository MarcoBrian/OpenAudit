from __future__ import annotations

from dataclasses import dataclass

from web3 import Web3


BOUNTY_SUBMISSION_ABI = [
    {
        "inputs": [
            {"internalType": "uint256", "name": "bountyId", "type": "uint256"},
            {"internalType": "bytes32", "name": "reportHash", "type": "bytes32"},
        ],
        "name": "commitFinding",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "bountyId", "type": "uint256"},
            {"internalType": "string", "name": "reportCID", "type": "string"},
            {"internalType": "string", "name": "pocTestCID", "type": "string"},
            {"internalType": "uint256", "name": "salt", "type": "uint256"},
        ],
        "name": "revealFinding",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "address", "name": "submitter", "type": "address"},
            {"internalType": "string", "name": "reportCID", "type": "string"},
            {"internalType": "uint256", "name": "salt", "type": "uint256"},
        ],
        "name": "computeCommitmentHash",
        "outputs": [{"internalType": "bytes32", "name": "", "type": "bytes32"}],
        "stateMutability": "pure",
        "type": "function",
    },
]


@dataclass(frozen=True)
class SubmissionInputs:
    bounty_id: int
    submitter: str
    report_cid: str
    poc_cid: str
    salt: int


class BountySubmissionClient:
    def __init__(self, rpc_url: str, bounty_hive: str) -> None:
        if not rpc_url:
            raise ValueError("RPC URL is required to access BountyHive.")
        if not bounty_hive:
            raise ValueError("BountyHive address is required.")
        self.web3 = Web3(Web3.HTTPProvider(rpc_url))
        if not self.web3.is_connected():
            raise ConnectionError("Unable to connect to RPC endpoint.")
        self.contract = self.web3.eth.contract(
            address=self.web3.to_checksum_address(bounty_hive),
            abi=BOUNTY_SUBMISSION_ABI,
        )

    def compute_commitment_hash(self, submitter: str, report_cid: str, salt: int) -> bytes:
        return self.contract.functions.computeCommitmentHash(
            self.web3.to_checksum_address(submitter),
            report_cid,
            salt,
        ).call()

    def commit_finding(
        self,
        *,
        private_key: str,
        bounty_id: int,
        report_hash: bytes,
    ) -> str:
        account = self.web3.eth.account.from_key(private_key)
        nonce = self.web3.eth.get_transaction_count(account.address)
        tx = self.contract.functions.commitFinding(
            bounty_id,
            report_hash,
        ).build_transaction(
            {
                "from": account.address,
                "nonce": nonce,
                "chainId": self.web3.eth.chain_id,
                "gas": 300_000,
            }
        )
        signed = account.sign_transaction(tx)
        tx_hash = self.web3.eth.send_raw_transaction(signed.rawTransaction)
        return tx_hash.hex()

    def reveal_finding(
        self,
        *,
        private_key: str,
        bounty_id: int,
        report_cid: str,
        poc_cid: str,
        salt: int,
    ) -> str:
        account = self.web3.eth.account.from_key(private_key)
        nonce = self.web3.eth.get_transaction_count(account.address)
        tx = self.contract.functions.revealFinding(
            bounty_id,
            report_cid,
            poc_cid,
            salt,
        ).build_transaction(
            {
                "from": account.address,
                "nonce": nonce,
                "chainId": self.web3.eth.chain_id,
                "gas": 500_000,
            }
        )
        signed = account.sign_transaction(tx)
        tx_hash = self.web3.eth.send_raw_transaction(signed.rawTransaction)
        return tx_hash.hex()
