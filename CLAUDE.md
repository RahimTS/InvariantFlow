# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**InvariantFlow** — a multi-agent swarm that validates API behavior against structured business rules. The full design is in `ARCHITECTURE.md`. Python 3.13, uv-managed.

## Commands

```bash
# Install dependencies
uv add <package>
uv sync

# Run the app
uv run uvicorn app.main:app --reload

# Run all tests
uv run pytest

# Run a single test file
uv run pytest tests/test_oracle.py

# Run a single test
uv run pytest tests/test_oracle.py::test_weight_violation -v

# Lint
uv run ruff check .
uv run ruff check --fix .

# Type check
uv run mypy app/
```

## Architecture

The system has three layers. Read `ARCHITECTURE.md` for the full spec.

### Layer 1 — Ingestion (LangGraph pipeline)
`Extractor → Normalizer → Rule Validator → Human Approval → Business Memory`

Rules start as raw text and exit as approved `BusinessRule` Pydantic objects stored in SQLite. Human approval is a hard gate — never skip it.

### Layer 2 — Business Memory (Blackboard pattern)
- **Rule Store** (`app/memory/rule_store.py`): SQLite. Approved rules with versioning and conflict detection.
- **State Store** (`app/memory/state_store.py`): In-memory dict scoped by `test_run_id`. Only the Executor writes here.
- **Execution Log** (`app/memory/exec_log.py`): Append-only `ExecutionRecord` list.
- **Blackboard** (`app/memory/blackboard.py`): Task board with atomic `claim_task()`. Agents watch for tasks and self-assign — no central coordinator. Tasks: `posted → claimed → in_progress → completed → dead`.

### Layer 3 — Testing Swarm (Blackboard-driven)
`Scenario Generator → Flow Planner → Executor → Oracle → Critic`

No agent calls another directly. They post tasks and claim tasks from the blackboard.

### Key design invariants

**The schema is the control mechanism.** Every agent boundary is a Pydantic model. Nothing crosses without validation. Models live in `app/schemas/`.

**Oracle must be deterministic first.** Four condition patterns (numeric comparison, equality, null check, state membership). LLM fallback only when none match. `requires_llm: True` on a rule is a quality smell.

**Context shape is fixed.** `build_eval_context()` always produces `{"entities": {...}, "scenario": {...}, "response": {...}}`. All condition dot-paths use these three top-level keys.

**Critic never modifies approved rules.** Rule changes go through proposal → Rule Validator → human approval. Critic can update `confidence` and post `edge_cases` automatically; everything else needs approval.

### LLM routing
All LLM calls go through OpenRouter (not the Anthropic SDK directly). Agent→model assignments:
- Extractor: `deepseek/deepseek-chat`
- Normalizer, Scenario Generator, Flow Planner, Oracle fallback: `google/gemini-2.5-flash`
- Critic: `anthropic/claude-sonnet-4`

### Build order (Phase 1 first)
Phase 1 is pure Python — no LLM, no agents. Steps 0–4 must work and catch the intentional weight bug before adding any LLM agents. The mock logistics API at `app/mock_api/` has an intentional bug: dispatch does NOT check `shipment_weight > vehicle_capacity`.

Phases: 1=Foundation, 2=First Agents (LangGraph), 3=Ingestion Chain, 4=Protocol Integration (A2A/MCP/SSE), 5=V2 infra (Redis+Postgres).

## Environment

Requires `OPENROUTER_API_KEY` in `.env`. See `.env.example` once created.
