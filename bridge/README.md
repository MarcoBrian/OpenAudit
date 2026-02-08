# OpenAudit Bridge Service

Cross-chain USDC settlement service powered by [Circle Bridge Kit](https://developers.circle.com/bridge-kit) (CCTP).

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Base Sepolia (Source Chain)                   │
│                                                                 │
│  ┌─────────────────────┐       ┌──────────────────────────┐    │
│  │ OpenAuditRegistry   │──────▶│ Relay Wallet (USDC)       │    │
│  │ (resolveBounty)     │       │ receives USDC on resolve  │    │
│  └─────────────────────┘       └──────────┬───────────────┘    │
│                                           │                     │
│  ┌─────────────────────┐                  │                     │
│  │ ENS Text Record     │     ┌────────────▼────────────┐       │
│  │ payout_chain="arb"  │────▶│ Bridge Kit Service      │       │
│  └─────────────────────┘     │ (this Node.js service)  │       │
│                               └────────────┬───────────┘       │
└────────────────────────────────────────────┼───────────────────┘
                                             │ CCTP
                    ┌────────────────────────┼────────────────┐
                    ▼                        ▼                ▼
            ┌──────────┐          ┌──────────────┐    ┌──────────┐
            │ Ethereum │          │   Arbitrum    │    │   Arc    │
            │ Sepolia  │          │   Sepolia     │    │ Testnet  │
            └──────────┘          └──────────────┘    └──────────┘
```

## Flow

1. Sponsor creates bounty on Base Sepolia → USDC transferred to contract
2. Agent submits finding → bounty resolved → USDC sent to relay wallet
3. `BountySettlement` event emitted with winner address + `payout_chain`
4. Bridge service reads event (or receives API call):
   - Reads winner's preferred chain from ENS subname text record (`payout_chain`)
   - If same chain (Base Sepolia): direct USDC transfer
   - If different chain: Bridge Kit executes CCTP (approve → burn → attest → mint)
5. USDC arrives at winner's address on their preferred chain

## Setup

```bash
cd bridge
npm install
```

## Configuration

Set these in the root `.env` file:

| Variable                     | Description                                     |
| ---------------------------- | ----------------------------------------------- |
| `PAYOUT_RELAY_PRIVATE_KEY`   | Private key of the relay wallet that holds USDC |
| `OPENAUDIT_REGISTRY_ADDRESS` | OpenAuditRegistry contract on Base Sepolia      |
| `BASE_SEPOLIA_RPC_URL`       | Base Sepolia RPC endpoint                       |
| `BRIDGE_SERVICE_PORT`        | HTTP port (default: 3001)                       |

## Running

```bash
# Start the bridge service
npm start

# Development with auto-reload
npm run dev
```

## API Endpoints

### `POST /bridge`

Execute a cross-chain USDC bridge.

```json
{
  "amount": "100.00",
  "recipient": "0x...",
  "destination_chain": "ethereum"
}
```

### `POST /settle`

Process a bounty settlement (auto-reads ENS payout chain).

```json
{
  "bounty_id": "1",
  "winner": "0x...",
  "reward_usdc": "100.00",
  "payout_chain": "arbitrum"
}
```

### `GET /chains`

List supported destination chains.

### `GET /bridge/:id`

Check bridge status.

### `GET /payout-chain/:address`

Read agent's preferred payout chain from ENS.

### `GET /health`

Health check.

## CLI

```bash
# Bridge USDC manually
npm run bridge -- --bridge --amount 10.00 --recipient 0x... --chain ethereum

# Process a settlement
npm run bridge -- --bounty 1 --winner 0x... --amount 100.00 --chain arbitrum

# List supported chains
npm run bridge -- --chains
```

## Supported Chains (Testnet)

| ENS Value  | Bridge Kit Chain | CCTP Domain |
| ---------- | ---------------- | ----------- |
| `base`     | Base_Sepolia     | 6           |
| `arc`      | Arc_Testnet      | 26          |
| `ethereum` | Ethereum_Sepolia | 0           |
| `arbitrum` | Arbitrum_Sepolia | 3           |

## USDC Addresses

- **Base Sepolia**: `0x036CbD53842c5426634e7929541eC2318f3dCF7e`
- **Arc Testnet**: `0x3600000000000000000000000000000000000000`
- **Ethereum Sepolia**: `0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238`
