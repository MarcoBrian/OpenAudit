# OpenAudit

## One-Sentence Vision
OpenAudit is an AI-agent security ecosystem where autonomous agents analyze smart-contract code, submit reproducible vulnerability findings, and earn bounties for high-quality security work.

## Problem Statement
- Static tools are noisy and produce false positives.
- LLMs often hallucinate without verifiable proof.
- Incentives are fragmented and not agent-native.

## Core Idea
- Agent layer: one strong AI security agent that can do real vulnerability work.
- Platform layer: a thin coordination layer to accept findings and show rewards.

## Agent MVP (Week-1 Scope)
This MVP is strictly scoped for a 1-week hackathon build.

### Inputs
- Single Solidity file (`.sol`) provided by local path or upload.
- No repo cloning, no multi-file analysis, no dependency resolution.

### Agent Workflow (Suggested)
```
Solidity File
 → Aderyn Static Analysis
 → Raw Findings (report.json)
 → AI Triage (filter to top 1–2 real issues)
 → Solodit Precedent Lookup (grounding)
 → Structured Vulnerability Submission (canonical JSON)
```

### Outputs
The agent must return a single structured vulnerability submission object that the platform can consume.

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
```ts
{
  title: "Reentrancy in withdraw()",
  severity: "HIGH",
  confidence: 0.0 - 1.0,
  description: "Clear explanation of the bug and root cause.",
  impact: "What an attacker can do and why it matters.",
  references: [
    {
      source: "Solodit",
      url: "https://solodit.xyz/...",
      note: "Similar historical case"
    }
  ],
  remediation: "Suggested fix or mitigation.",
  repro: "Optional steps to reproduce or verify.",
  evidence: {
    static_tool: "aderyn",
    raw_findings: ["..."],
    file_path: "Contract.sol"
  }
}
```

## 1-Week Build Schedule
### Day 1
- Finalize Agent MVP scope and output schema.
- Set up Aderyn run script for a single `.sol` input.

### Day 2
- Implement Aderyn parsing into raw findings.
- Draft AI triage prompt and scoring rubric (precision over recall).

### Day 3
- Implement Solodit lookup for similar cases.
- Integrate references into the output object.

### Day 4
- Produce end-to-end pipeline: file → output JSON.
- Add basic CLI or minimal API endpoint to run the agent.

### Day 5
- Evaluate on 1–2 sample contracts and refine prompts.
- Create a cached demo output for reliability.

### Day 6
- Add minimal platform stub to display the output.
- Prepare a short demo flow and slides.

### Day 7
- Final testing, polish, and pitch rehearsal.

## Agent CLI (Prototype)
### Requirements
- Python 3.10+
- Aderyn installed and available in PATH
- Slither installed and available in PATH (if using `--tools slither`)
- LangGraph (optional, for workflow orchestration)

Install Aderyn following the official guide for your OS.

### Install
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Run (Aderyn pipeline)
```bash
python -m agents --file path/to/Contract.sol --out submission.json
```

### Run with Slither
```bash
python -m agents --file path/to/Contract.sol --out submission.json --tools slither
```

### Run with Both Tools
```bash
python -m agents --file path/to/Contract.sol --out submission.json --tools aderyn,slither
```

### Run with LangGraph
```bash
python -m agents --file path/to/Contract.sol --out submission.json --use-graph --tools aderyn,slither
```

### Optional LLM Triage
Set these environment variables to enable LLM-based triage:
```
OPENAI_API_KEY=your_key
OPENAI_MODEL=gpt-4o-mini
OPENAI_BASE_URL=https://api.openai.com/v1
```

If unset, the agent falls back to heuristic ranking.

### Aderyn Command Override (Optional)
If your Aderyn CLI uses different flags, you can override the command:
```
ADERYN_CMD="aderyn --output {output} {target}"
```

### Slither Compiler Override (Optional)
Slither auto-selects a compatible compiler from `~/.solc-select/artifacts`.
You can override manually if needed:
```
SOLC_VERSION=0.6.12
```
Or pass a full binary path:
```
SOLC_BIN=/path/to/solc
```