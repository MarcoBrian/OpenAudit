# OpenAudit

Built at ETHGlobal Hack Money 2026. ENS Prize Pool 🏅  
Showcase: https://ethglobal.com/showcase/openaudit-m94b2

## One-Sentence Vision
OpenAudit is an AI-agent security ecosystem where autonomous agents analyze smart-contract code, submit reproducible vulnerability findings, and earn bounties for high-quality security work.

## Problem Statement
- Static tools are noisy and produce false positives.
- LLMs often hallucinate without verifiable proof.
- Incentives are fragmented and not agent-native.

## Core Idea
- Agent layer: one strong AI security agent that can do real vulnerability work.
- Platform layer: a thin coordination layer to accept findings and show rewards.

## Open Audit Agent  

### Inputs
- Single Solidity file (`.sol`) provided by local path or upload.
- No repo cloning, no multi-file analysis, no dependency resolution.

### Agent Workflow
```
Solidity File
 → Aderyn/Slither Static Analysis
 → Raw Findings (report.json)
 → AI Triage (filter to top 1–2 real issues)
 → Logic Review (LLM reasoning for drain/flow bugs)
 → Solodit Precedent Lookup (grounding)
 → Structured Vulnerability Submission (canonical JSON)
```

### Outputs
The agent returns a single structured vulnerability submission object that the platform can consume.

### Success Criteria
- Finds at least one real vulnerability from the single file.
- Grounds the finding with at least one Solodit precedent.
- Produces a clear remediation recommendation.

### Explicit Non-Goals (Week-1)
- Multi-agent orchestration or competition (single agent workflow only).
- Repository-scale analysis.
- On-chain bounty distribution or governance.
- Automated exploit generation.

## Canonical Submission Schema (MVP)
```json
{
  "title": "Reentrancy in withdraw()",
  "severity": "HIGH",
  "confidence": 0.85,
  "description": "Clear explanation of the bug and root cause.",
  "impact": "What an attacker can do and why it matters.",
  "references": [
    {
      "source": "Solodit",
      "url": "https://solodit.xyz/...",
      "note": "Similar historical case"
    }
  ],
  "remediation": "Suggested fix or mitigation.",
  "repro": "Optional steps to reproduce or verify.",
  "evidence": {
    "static_tool": "aderyn+slither",
    "raw_findings": ["..."],
    "file_path": "Contract.sol"
  }
}
```

## Installation

### Requirements
- Python 3.10+
- Aderyn installed and available in PATH
- Slither installed and available in PATH (optional, if using `--tools slither`)
- LangGraph (optional, for workflow orchestration)
- LangChain (optional, for agent chat mode)

### Install Dependencies
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Install Aderyn following the [official guide](https://github.com/Cyfrin/aderyn) for your OS.

## Configuration

### Environment Variables
Copy `env.template` to `.env` and configure as needed:

```bash
cp env.template .env
```

#### LLM Configuration (OpenAI)
```bash
OPENAI_API_KEY=your_key
OPENAI_MODEL=gpt-4o-mini
OPENAI_BASE_URL=https://api.openai.com/v1
```

#### LLM Configuration (Ollama - Local)
```bash
OLLAMA_MODEL=llama3
OLLAMA_BASE_URL=http://localhost:11434
```

If no LLM is configured, the agent falls back to heuristic ranking.

#### Solodit API (Optional)
```bash
SOLODIT_API_KEY=your_key
SOLODIT_BASE_URL=https://solodit.cyfrin.io/api/v1/solodit
SOLODIT_FINDINGS_ENDPOINT=/findings
SOLODIT_PAGE=1
SOLODIT_PAGE_SIZE=10
```

Additional Solodit filters:
- `SOLODIT_IMPACTS` (comma-separated: HIGH,MEDIUM,LOW,GAS)
- `SOLODIT_SORT_FIELD` (Recency, Quality, Rarity)
- `SOLODIT_SORT_DIRECTION` (Asc, Desc)
- `SOLODIT_QUALITY_SCORE` (0-5)
- `SOLODIT_RARITY_SCORE` (0-5)
- `SOLODIT_TAGS` (comma-separated tag names)
- `SOLODIT_PROTOCOL_CATEGORIES` (comma-separated category names)
- `SOLODIT_FILTERS_JSON` (raw JSON to merge into filters)

#### Coinbase AgentKit Wallet (Optional)
```bash
CDP_API_KEY_ID=your_key_id
CDP_API_KEY_SECRET=your_secret
CDP_WALLET_SECRET=your_wallet_secret
CDP_NETWORK_ID=base-sepolia
CDP_WALLET_ADDRESS=your_wallet_address
```

Or use a local EVM wallet:
```bash
OPENAUDIT_WALLET_PRIVATE_KEY=your_private_key
OPENAUDIT_WALLET_NETWORK=base-sepolia
OPENAUDIT_WALLET_CHAIN_ID=84532
OPENAUDIT_WALLET_RPC_URL=https://sepolia.base.org
```

#### OpenAudit Registry (On-chain)
```bash
OPENAUDIT_REGISTRY_ADDRESS=0xYourRegistryAddress
RPC_URL=http://localhost:8545
```

#### Bounty Workflow (CLI)
```bash
BOUNTY_SOURCE_MAP=./bounty_sources.json
BOUNTY_SUBMITTER_PRIVATE_KEY=your_private_key
ETHERSCAN_API_URL=https://api-sepolia.etherscan.io/api
ETHERSCAN_API_KEY=your_key
```

#### Pinata IPFS (Optional)
```bash
PINATA_JWT=your_pinata_jwt
PINATA_GATEWAY_URL=https://gateway.pinata.cloud
NEXT_PUBLIC_PINATA_GATEWAY=https://your-gateway.mypinata.cloud
```

#### Tool Overrides (Optional)
```bash
# Aderyn command override
ADERYN_CMD="aderyn --output {output} {target}"

# Solidity compiler version
SOLC_VERSION=0.6.12
# Or full binary path
SOLC_BIN=/path/to/solc
```

## CLI Usage

### Full Pipeline (Recommended)
Run the complete audit workflow:

```bash
python -m agents run --file sample_contracts/CoinFlip.sol --out submission.json
```

#### Options
- `--file`: Path to Solidity file (required)
- `--out`: Output JSON file (default: `submission.json`)
- `--tools`: Comma-separated tools to run: `aderyn`, `slither` (default: `aderyn`)
- `--max-issues`: Max issues to output (default: `2`)
- `--no-llm`: Disable LLM triage and use heuristic ranking
- `--use-graph`: Run the workflow via LangGraph
- `--reports-dir`: Directory for intermediate reports (default: `reports`)
- `--dump-intermediate`: Write intermediate outputs to `reports/` for debugging

#### Examples
```bash
# Basic run with Aderyn
python -m agents run --file sample_contracts/CoinFlip.sol

# Run with both tools
python -m agents run --file sample_contracts/CoinFlip.sol --tools aderyn,slither

# Run with LangGraph orchestration
python -m agents run --file sample_contracts/CoinFlip.sol --use-graph --tools aderyn,slither

# Debug mode (saves intermediate outputs)
python -m agents run --file sample_contracts/CoinFlip.sol --tools aderyn,slither --dump-intermediate

# Heuristic-only (no LLM)
python -m agents run --file sample_contracts/CoinFlip.sol --no-llm
```

### Bounty Workflow (Agent)

List bounties from a deployed `OpenAuditRegistry`:

```bash
export RPC_URL=http://localhost:8545
export OPENAUDIT_REGISTRY_ADDRESS=0xYourRegistryAddress

python -m agents bounty list
```

Analyze a bounty target using a local source map (for local testing):

```bash
export RPC_URL=http://localhost:8545
export OPENAUDIT_REGISTRY_ADDRESS=0xYourRegistryAddress

# JSON mapping: { "0xTargetAddress": "path/to/Target.sol" }
python -m agents bounty analyze --bounty-id 1 --source-map bounty_sources.json --out submission.json
```

Analyze a bounty target via an Etherscan-compatible API:

```bash
export RPC_URL=$SEPOLIA_RPC_URL
export OPENAUDIT_REGISTRY_ADDRESS=0xYourRegistryAddress
export ETHERSCAN_API_URL=https://api-sepolia.etherscan.io/api
export ETHERSCAN_API_KEY=your_key

python -m agents bounty analyze --bounty-id 1 --use-etherscan --out submission.json
```

Submit a finding for a bounty:

```bash
export RPC_URL=http://localhost:8545
export OPENAUDIT_REGISTRY_ADDRESS=0xYourRegistryAddress
export BOUNTY_SUBMITTER_PRIVATE_KEY=your_private_key

python -m agents bounty submit \
  --bounty-id 1 \
  --report-cid QmReportCID
```

### Step-by-Step Commands
Run each stage independently for debugging:

```bash
# 1. Run static analysis tools
python -m agents scan --file sample_contracts/CoinFlip.sol --tools aderyn,slither

# 2. Extract and normalize findings
python -m agents extract

# 3. Triage findings (rank and filter)
python -m agents triage --max-issues 2

# 4. Run logic review (LLM-based deep analysis)
python -m agents logic --file sample_contracts/CoinFlip.sol --max-issues 1
```

### LangChain Agent (Interactive Chat Mode)
Run an interactive agent that can answer questions and run audits:

```bash
python -m agents agent --mode chat
```

#### Agent Options
- `--mode`: Agent runtime mode: `chat` or `auto` (default: `chat`)
- `--interval`: Seconds between autonomous actions in `auto` mode (default: `10`)
- `--no-wallet-tools`: Disable AgentKit wallet tools
- `--verbose`: Enable verbose agent logging
- `--system-prompt`: Override the default agent system prompt

#### Examples
```bash
# Interactive chat mode
python -m agents agent --mode chat

# Autonomous mode (runs audits periodically)
python -m agents agent --mode auto --interval 30

# Chat mode with custom prompt
python -m agents agent --mode chat --system-prompt "You are a security expert..."
```

In chat mode, you can:
- Ask questions about Solidity security
- Request audits: `run_audit file=sample_contracts/CoinFlip.sol`
- Get help with audit workflows
- List bounties: `list_bounties limit=10`
- Analyze a bounty: `analyze_bounty bounty_id=1`
- Submit a bounty finding: `submit_bounty bounty_id=1 report_cid=QmReportCID`

Notes for bounty tools:
- `analyze_bounty` uses an Etherscan-compatible API by default. Set `ETHERSCAN_API_URL` and `ETHERSCAN_API_KEY`.
- To use a local source map instead: `analyze_bounty bounty_id=1 source_map=./bounty_sources.json use_etherscan=false`
- `submit_bounty` uses `OPENAUDIT_WALLET_PRIVATE_KEY` by default (agent POV).

### Wallet Commands
Check AgentKit wallet configuration:

```bash
# Show wallet details
python -m agents wallet

# Show wallet details as JSON
python -m agents wallet --json
```

## Intermediate Reports

When using `--dump-intermediate`, the following files are written to `reports/`:

- `aderyn_report.json`: Raw Aderyn output
- `slither_report.json`: Raw Slither output
- `static_analysis_summary.json`: Normalized findings from all tools
- `triage.json`: Top-ranked findings after triage
- `logic.json`: Additional logic issues found by LLM
- `solodit.json`: Solodit reference lookups
- `progress.json` / `progress.jsonl`: Progress tracking (if using dashboard)

## LangGraph vs Linear Pipeline

OpenAudit supports two execution modes:

### Linear Pipeline (Default)
- Simple, sequential execution
- No additional dependencies beyond core requirements
- Easier to debug and modify
- Use: `python -m agents run --file ...`

### LangGraph Orchestration
- Stateful workflow with explicit nodes and edges
- Better for complex workflows, parallel execution, and future extensions
- Requires `langgraph` package
- Use: `python -m agents run --file ... --use-graph`

**When to use LangGraph:**
- You want to extend the workflow with custom nodes
- You need parallel tool execution
- You want to add human-in-the-loop checkpoints
- You're building multi-contract analysis workflows

## Platform UI (FastAPI + Next.js)

The repo includes a web dashboard with a backend API and React/Next.js frontend that streams progress.

### Backend API
```bash
cd dashboard/server
uvicorn app:app --reload
```

The API runs on `http://localhost:8000` by default.

### Frontend (Next.js)
```bash
cd dashboard/frontend
npm install
NEXT_PUBLIC_API_BASE=http://localhost:8000 npm run dev
```

Open `http://localhost:3000` to:
- Upload a `.sol` file
- Run the agent with real-time progress updates
- View the final submission JSON
- Browse audit history

### API Endpoints
- `POST /api/audit`: Start a new audit
- `GET /api/audit/{run_id}`: Get audit status and results
- `GET /api/audit/{run_id}/progress`: Stream progress updates
- `GET /api/runs`: List all audit runs

## Architecture

### Core Components
- **Static Analysis Runners**: `aderyn_runner.py`, `slither_runner.py`
- **Triage System**: `triage.py` (filtering, ranking, LLM-based selection)
- **Logic Review**: `logic.py` (LLM-based deep analysis)
- **Reference Lookup**: `solodit.py` (grounding with historical cases)
- **Submission Builder**: `submission.py` (canonical JSON generation)
- **Workflow Orchestration**: `graph.py` (LangGraph), `cli.py` (linear)
- **LangChain Agent**: `langchain_agent.py` (interactive chat mode)
- **Wallet Integration**: `wallet.py` (Coinbase AgentKit)

### Workflow Stages
1. **Scan**: Run static analysis tools (Aderyn, Slither)
2. **Extract**: Normalize findings from different tools
3. **Triage**: Filter and rank findings (heuristic or LLM-based)
4. **Logic Review**: Deep LLM analysis for logic bugs
5. **Reference Lookup**: Find similar historical cases (Solodit)
6. **Finalize**: Build structured submission JSON

## Development

### Project Structure
```
OpenAudit/
├── agents/              # Core agent logic
│   ├── cli.py          # CLI entry point
│   ├── graph.py         # LangGraph workflow
│   ├── langchain_agent.py  # Interactive agent
│   ├── triage.py        # Finding triage system
│   └── ...
├── dashboard/           # Web UI
│   ├── server/          # FastAPI backend
│   └── frontend/        # Next.js frontend
├── sample_contracts/    # Example Solidity files
├── reports/             # Intermediate outputs
└── requirements.txt    # Python dependencies
```

### Running Tests
```bash
# Run static analysis on sample contracts
python -m agents run --file sample_contracts/CoinFlip.sol --dump-intermediate
python -m agents run --file sample_contracts/Fallback.sol --dump-intermediate
python -m agents run --file sample_contracts/Recovery.sol --dump-intermediate
```

### Debugging
1. Use `--dump-intermediate` to inspect each stage
2. Check `reports/` directory for intermediate outputs
3. Use step-by-step commands to isolate issues
4. Enable verbose logging: `python -m agents agent --mode chat --verbose`

## Troubleshooting

### Aderyn Not Found
Ensure Aderyn is installed and in your PATH:
```bash
aderyn --version
```

### Slither Errors
Check Solidity compiler version compatibility:
```bash
solc-select install 0.8.20
solc-select use 0.8.20
```

### LLM Not Working
- Check environment variables: `OPENAI_API_KEY` or `OLLAMA_MODEL`
- For Ollama, ensure the server is running: `ollama serve`
- The agent falls back to heuristic ranking if LLM is unavailable

### Import Errors
If you see `nest_asyncio` errors with uvicorn, this is expected when the dashboard server imports the agent module. The wallet tools are lazy-loaded to avoid this issue.

## License

[Add your license here]

## Contributing
