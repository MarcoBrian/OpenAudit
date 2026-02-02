# OpenAudit Architecture (Agent MVP)

This document captures the week-1 architecture and implementation plan for the AI agent MVP.

## Goals
- Analyze a single Solidity file with Aderyn and/or Slither.
- Triage findings (LLM if available, heuristic fallback if not).
- Ground findings with Solodit references.
- Output a canonical submission JSON object.

## System Overview
The MVP is a local CLI pipeline that takes one `.sol` file and produces a structured vulnerability submission.

```
User Input (.sol)
  → Aderyn or Slither Static Analysis
  → Raw Findings (report.json)
  → Triage (LLM or heuristic)
  → Solodit References
  → Submission JSON
```

## Components
### CLI Entry
- `agents/cli.py`
- Handles argument parsing, orchestration, output writing.

### Static Analysis Runner
- `agents/aderyn_runner.py`
- `agents/slither_runner.py`
- Executes Aderyn or Slither, stores JSON output, loads results.

### Triage Engine
- `agents/triage.py`
- Extracts findings, scores them, optionally calls LLM.
- Heuristic ranking is used when no API key is present or LLM fails.

### Solodit Reference Builder
- `agents/solodit.py`
- Produces Solodit search links for the top issue.

### Submission Schema
- `agents/schema.py`
- Defines the canonical output object and validation.

## Data Flow
1. User runs the CLI with `--file`.
2. Aderyn and/or Slither run and return report JSON.
3. Findings are normalized and ranked.
4. Top issue is selected and expanded.
5. Solodit search link is attached as reference.
6. Output is saved to `submission.json`.

## LangGraph Orchestration (Optional)
When `--use-graph` is set, the same pipeline runs through a LangGraph state
machine with the following nodes:
- Scan
- Extract
- Triage
- Finalize

## Configuration
Environment variables (optional):
- `ADERYN_CMD`: override the Aderyn command. Use `{target}` and `{output}` placeholders.
- `OPENAI_API_KEY`: enables LLM triage.
- `OPENAI_MODEL`: defaults to `gpt-4o-mini`.
- `OPENAI_BASE_URL`: defaults to `https://api.openai.com/v1`.

## Tool Selection
Use `--tools` to select one or both scanners:
- `--tools aderyn`
- `--tools slither`
- `--tools aderyn,slither`

## Non-Goals (Week-1)
- Repo-scale or multi-file analysis.
- Automated exploit generation.
- On-chain bounty distribution.
- Multi-agent orchestration.

## Week-1 Implementation Plan
### Day 1
- Lock schema and CLI interface.
- Confirm Aderyn version and basic run script.

### Day 2
- Build detector extraction and ranking.
- Add LLM prompt and fallback logic.

### Day 3
- Integrate Solodit references.
- Generate first submission JSON end-to-end.

### Day 4
- CLI stability and error handling.
- Sample contract testing.

### Day 5
- Refine prompts and scoring.
- Cache a demo output.

### Day 6–7
- Demo polish and documentation.

## Future Extensions
- Multi-file or repo analysis.
- Multiple findings per submission.
- Formal verification integrations.
- Agent competition and reputation.

