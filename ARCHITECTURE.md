# SwarmProbe — Business Logic API Validator Swarm

## Architecture & Design Document (v0.3 — Final, All Review Feedback Incorporated)

**Author**: Rahim + Claude  
**Date**: March 2026  
**Status**: Pre-implementation review (FINAL)  
**Lineage**: Evolved from SpringGuard (multi-agent code review platform)

---

## 0. Mental Model (Read This First)

This system **tests API behavior against structured assumptions derived from business intent**.

It does NOT understand business logic. It has structured assumptions (rules) and mechanically tests whether the API violates them. If the assumption is wrong, the Critic catches it. If the API is wrong, the Oracle catches it. The system never claims to understand — it claims to test.

**Inputs**: Messy specs + running APIs  
**Outputs**: Violations, traceability, test coverage reports

**The core principle**: Agents operate within the schema, not outside it. The schema is the control mechanism. Without it, the system becomes vague and untestable. With it, you get flexibility in meaning but rigidity in execution.

---

## 1. The Business Rule Schema (The Backbone)

This Pydantic model is the contract that every agent must follow. Nothing enters or leaves an agent boundary without conforming to it.

```python
from pydantic import BaseModel, Field
from typing import Literal, Optional
from datetime import datetime


class RuleTrigger(BaseModel):
    action: Optional[str] = None
    endpoint: Optional[str] = None


class BusinessRule(BaseModel):
    rule_id: str
    version: int = 1
    type: Literal[
        "constraint",
        "state_transition",
        "precondition",
        "postcondition",
        "derived"
    ]
    description: str
    entities: list[str]
    conditions: list[str]
    trigger: Optional[RuleTrigger] = None
    expected_effect: list[str]
    invalid_scenarios: list[str]
    edge_cases: list[str] = []
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    source: list[str] = []

    # Lifecycle fields
    status: Literal["proposed", "approved", "deprecated"] = "proposed"
    previous_version: Optional[int] = None
    created_by: str = ""
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    conflicts_with: list[str] = []
    change_reason: Optional[str] = None

    # Evaluation metadata (set by Rule Validator during validation)
    requires_llm: bool = False             # True if any condition is not machine-evaluable
```

### 1.1 Schema Design Decisions

**Why `conditions` is `list[str]` not a formal AST**: Business rules range from `"shipment_weight <= vehicle_capacity"` (easily parseable) to `"delivery address must be within service area"` (needs LLM interpretation). A string list handles both. The Oracle decides at evaluation time whether to parse deterministically or delegate to LLM.

**Why `requires_llm` exists**: The Rule Validator runs each condition through the four-pattern matcher during validation. If any condition fails to match a supported pattern, `requires_llm` is set to `True`. This doesn't block the rule — it flags it. The Oracle knows upfront whether it can go fully deterministic or will need the LLM path. This also serves as a quality metric: if a high percentage of rules require LLM evaluation, the team should tighten their condition language.

**Why `confidence` exists**: The Critic updates this. A rule that catches violations consistently gets confidence bumped toward 1.0. A rule that produces false positives gets confidence dropped. Below 0.5, the rule gets flagged for human review.

**Why `conflicts_with`**: Detected at insertion time. When a new rule's entities overlap with an existing rule's entities and conditions create contradiction, the conflict is flagged. Both rules stay, but the Oracle knows to check which applies given the context. For V1, conflict resolution is passive — humans decide during approval whether conflicting rules can coexist. In V2, the Oracle will check `conflicts_with` before evaluation and determine which rule applies given the current context.

---

## 2. All Pydantic Models (Agent Boundary Contracts)

Every piece of data that crosses an agent boundary has a strict schema.

```python
# --- Ingestion Layer ---

class RawExtraction(BaseModel):
    source: str
    raw_rules: list[str]
    extraction_confidence: float


class ValidationVerdict(BaseModel):
    rule_id: str
    verdict: Literal["approved", "rejected", "needs_revision"]
    issues: list[dict]
    checks_passed: list[str]
    checks_failed: list[str]


# --- Testing Layer ---

class Scenario(BaseModel):
    scenario_id: str
    rule_id: str
    label: str                                        # "valid", "boundary", "invalid", "edge"
    inputs: dict
    expected_outcome: Literal["pass", "fail"]
    rationale: str


class FlowStep(BaseModel):
    step_number: int
    endpoint: str
    method: str
    path_params: dict = {}                            # {"shipment_id": "$state.shipment_id"}
    payload_map: dict = {}                            # {"weight": "$scenario.shipment_weight"}
    extract: dict = {}                                # {"shipment_id": "$.response.shipment_id"}
    expected_status: list[int] = [200, 201]


class FlowPlan(BaseModel):
    flow_id: str
    rule_id: str
    name: str
    steps: list[FlowStep]
    description: str


class ExecutionRecord(BaseModel):
    step_number: int
    endpoint: str
    request_payload: dict
    response_body: dict
    status_code: int
    latency_ms: float
    timestamp: datetime


class ExecutionTrace(BaseModel):
    trace_id: str
    rule_id: str
    scenario_id: str
    flow_id: str
    records: list[ExecutionRecord]
    final_state: dict
    overall_status: Literal["completed", "error", "timeout"]


# --- Validation Layer ---

class OracleVerdict(BaseModel):
    trace_id: str
    rule_id: str
    scenario_id: str
    result: Literal["pass", "fail", "inconclusive"]
    violated_conditions: list[str]
    evaluation_method: Literal["deterministic", "llm_assisted"]
    reproducible: bool                                # False when evaluation_method is llm_assisted
    evidence: dict
    confidence: float


# --- Feedback Layer ---

class CriticFinding(BaseModel):
    type: Literal[
        "missing_edge_case",
        "rule_confidence_update",
        "flow_gap",
        "false_positive",
        "false_negative",
        "rule_revision_suggestion"
    ]
    target: Literal[
        "scenario_generator",
        "flow_planner",
        "oracle",
        "business_memory"
    ]
    detail: str
    action: str
    payload: dict = {}


class CriticFeedback(BaseModel):
    test_run_id: str
    rule_id: str
    findings: list[CriticFinding]
    summary: str
    iterations_remaining: int
```

---

## 3. System Architecture — Three Layers

### 3.1 Layer 1: Ingestion & Understanding (LLM-Powered)

**Purpose**: Convert messy human specs into validated, approved business rules.

**Agent chain**: Extractor → Normalizer → Rule Validator → Human Approval → Business Memory

**Internal communication**: LangGraph Swarm with bidirectional handoff tools. Any agent can reject back to its predecessor with structured issues.

#### 3.1.1 Extractor Agent

- **Type**: LLM-powered (cheap model: `deepseek/deepseek-chat`)
- **Input**: Raw text (Jira ticket body, PRD section, free text)
- **Output**: `RawExtraction`
- **Does NOT**: Enforce schema. Its job is to find rule-like statements in messy text.

#### 3.1.2 Normalizer Agent

- **Type**: LLM-powered (mid-tier: `google/gemini-2.5-flash`)
- **Input**: `RawExtraction`
- **Output**: `BusinessRule` (proposed status)
- **Critical job**: Maps natural language to schema fields. Determines the `type`, writes testable `conditions`, fills `expected_effect` and `invalid_scenarios`.
- **Constraint**: Output MUST pass Pydantic validation. Retries up to 3 times before rejecting back to Extractor.

#### 3.1.3 Rule Validator Agent

- **Type**: Mostly deterministic with optional LLM fallback
- **Input**: `BusinessRule` (proposed)
- **Output**: `ValidationVerdict`
- **Deterministic checks**:
  - All required fields present and non-empty
  - `type` is valid enum value
  - `conditions` list is non-empty
  - `entities` reference known domain objects
  - `expected_effect` and `invalid_scenarios` are non-empty
- **Semantic checks** (lightweight LLM):
  - Is condition evaluable? (contains comparison operator or known state reference)
  - Does `expected_effect` align with `type`?
  - Do `invalid_scenarios` actually violate `conditions`?
- **Rejection**: Sends `ValidationVerdict` with `needs_revision` back to Normalizer via handoff.
- **Escalation**: After 3 rejection cycles, escalates to human review with accumulated context.

#### 3.1.4 Human Approval

- **Type**: API endpoint, not an agent
- **Endpoints**:
  - `GET /api/v1/rules/pending` — list rules awaiting approval
  - `POST /api/v1/rules/{id}/approve` — approve with optional edits
  - `POST /api/v1/rules/{id}/reject` — reject with reason
- **Non-negotiable**: Do not skip this gate, even during development. Auto-approve guarantees garbage in Business Memory.

### 3.2 Layer 2: Business Memory (Blackboard Pattern)

**Purpose**: Controlled knowledge base that all testing agents read from. Not a dump.

Agents are not assigned tasks by a coordinator. They watch the board and autonomously decide whether to act.

#### 3.2.1 Rule Store

- **Storage**: SQLite (V1) → Postgres (V2)
- **What**: All approved business rules with full version history
- **Key operations**:
  - `get_active_rules(entity: str)` — all approved rules for an entity
  - `get_rule(rule_id: str, version: int = None)` — specific rule (latest if no version)
  - `get_conflicts(rule_id: str)` — rules that contradict
  - `get_rules_by_status(status: str)` — for approval queue
  - `get_rule_history(rule_id: str)` — all versions with change reasons
- **Versioning**: New version created when Critic suggests a revision AND human approves. Old version transitions to `deprecated`.
- **Conflict tracking**: At insertion, check existing approved rules with overlapping entities. If conditions contradict, populate `conflicts_with` on both rules.

#### 3.2.2 State Store

- **Storage**: In-memory dict (V1) → Redis (V2)
- **Scoped by**: `test_run_id` — each test run gets isolated state
- **Entity structure** (standardized for type-based filtering):
  ```
  state[test_run_id][entity_id] = {
      "id": "SHIP_123",
      "type": "Shipment",
      "status": "ASSIGNED",
      "status_history": ["CREATED", "ASSIGNED"],
      "weight": 1200,
      "assigned_vehicle": "VH_001",
      "vehicle_capacity": 1000,
      "created_at": "...",
  }
  ```
- **Interface**:
  ```python
  class StateStore(Protocol):
      async def get_entity(self, run_id: str, entity_id: str) -> dict | None: ...
      async def update_entity(self, run_id: str, entity_id: str, fields: dict) -> None: ...
      async def get_status_history(self, run_id: str, entity_id: str) -> list[str]: ...
      async def get_entities_by_type(self, run_id: str, entity_type: str) -> list[dict]: ...
      async def get_related_entities(self, run_id: str, entity_id: str) -> list[dict]: ...
      async def snapshot(self, run_id: str) -> dict: ...
      async def clear(self, run_id: str) -> None: ...
  ```
- **`get_related_entities` V1 implementation**: Simple scan — iterate all entities in the run, return any that reference `entity_id` in any field value. No graph store needed yet.
- **Who writes**: Only the Executor Agent
- **Who reads**: Executor (inject state into subsequent API calls), Oracle (check transitions), Critic (understand failure context)

#### 3.2.3 Execution Log

- **Storage**: Append-only list (V1) → Postgres (V2)
- **Structure**: List of `ExecutionRecord` objects
- **Indexed by**: `rule_id`, `scenario_id`, `trace_id`
- **LLM-assisted verdicts**: Marked with `reproducible: false` in the log. Re-running the same test may produce different LLM evaluation.

#### 3.2.4 Blackboard (Task Board)

- **Storage**: In-memory dict with asyncio event callbacks (V1) → Redis Streams (V2)
- **Task structure**:
  ```
  board[task_id] = {
      "type": "test_rule",
      "rule_id": "SHIP_001",
      "status": "posted",           # posted → claimed → in_progress → completed → dead
      "claimed_by": None,
      "posted_at": "...",
      "claimed_at": None,
      "retry_count": 0,
      "data": {}
  }
  ```
- **Safety mechanisms** (prevents silent misbehavior):
  - **Atomic claim**: `claim_task()` does compare-and-swap — checks `status == "posted"` AND atomically sets to `"claimed"`. Two agents cannot claim the same task.
  - **Stuck task timeout**: If a task stays `"claimed"` or `"in_progress"` for > 60s without completion, it reverts to `"posted"` and `retry_count` increments.
  - **Max retries**: After 3 retries, task transitions to `"dead"` and is logged for human review.
  - **Dead task logging**: Dead tasks are surfaced in the API (`GET /api/v1/tasks/dead`) so failures are visible, not silent.
- **Flow**:
  1. New approved rule enters Rule Store → task posted: `"test_rule:SHIP_001"`
  2. Scenario Generator claims it, generates scenarios
  3. Posts new tasks: `"execute:SHIP_001:scenario_001"`, etc.
  4. Executor claims and runs them
  5. Posts results → Oracle claims and validates
  6. Posts verdicts → Critic claims and analyzes
  7. Critic may post new tasks (refinements) → loop continues

### 3.3 Layer 3: Testing Swarm (Where Swarm Intelligence Emerges)

**Communication**: Blackboard-driven. No central coordinator.

#### 3.3.1 Scenario Generator Agent

- **Type**: LLM-powered (`google/gemini-2.5-flash`)
- **Watches for**: `test_rule` tasks on blackboard
- **Input**: `BusinessRule` from Rule Store
- **Output**: List of `Scenario` objects
- **Generation strategy**:
  - Read `conditions` → valid inputs (well within bounds)
  - Read `conditions` → boundary inputs (exact limits)
  - Read `invalid_scenarios` → violating inputs
  - Read `edge_cases` → edge inputs (zero, negative, null, max int)
  - If Critic feedback exists → incorporate suggested scenarios
- **Constraint**: Output validated against `Scenario` Pydantic model. Invalid output = retry.
- **Hard limit**: Max 20 scenarios per rule (configurable). Prevents unbounded generation.

#### 3.3.2 Flow Planner Agent

- **Type**: Deterministic for `constraint` rules. LLM for `state_transition` / `precondition` / `postcondition`.
- **Watches for**: `generate_flow` tasks on blackboard
- **Input**: `BusinessRule` + `Scenario`
- **Output**: `FlowPlan`
- **For simple constraints**: Returns hardcoded template (create → assign → dispatch). No LLM.
- **For state transitions**: Generates flow variations:
  - Happy path (correct order)
  - Skip-step (omit prerequisite)
  - Double-step (repeat)
  - Reverse-step (out of order)
- **Field mapping per step**:
  - `$scenario.` prefix → references test data from Scenario
  - `$state.` prefix → references values extracted from previous API responses
  - `$.response.` prefix → JSONPath into current response for extraction
- **Output validation** (deterministic, runs after every LLM-generated flow):
  - Every `endpoint` in every `FlowStep` must match a known API route (checked against FastAPI's `app.routes`). Unknown endpoint → reject flow, retry.
  - Data dependency check: if a step uses `$state.shipment_id` in `path_params`, a prior step must have `shipment_id` in its `extract` dict. Missing dependency → reject flow with specific issue.
  - This is ~20 lines of deterministic Python. Invalid flows get rejected back to the Flow Planner with structured errors.

#### 3.3.3 Executor Agent

- **Type**: Fully deterministic. No LLM. Pure Python.
- **Watches for**: `execute` tasks on blackboard
- **Input**: `FlowPlan` + `Scenario`
- **Process**:
  1. Initialize state store for this test run
  2. For each step in flow plan:
     a. Resolve `$state.` references via dot-path lookup from state store
     b. Build request payload by resolving `$scenario.` references from scenario inputs
     c. Fire HTTP request via `httpx.AsyncClient`
     d. Record `ExecutionRecord`
     e. Extract values specified in `extract` and write to state store
     f. Update entity state
  3. Take final state snapshot
  4. Assemble `ExecutionTrace`
- **Error handling**: 5xx or timeout → record as `overall_status: "error"`, continue to Oracle.

#### 3.3.4 Oracle / Validator Agent

- **Type**: Primarily deterministic. LLM fallback for ambiguous conditions only.
- **Watches for**: `validate` tasks on blackboard
- **Input**: `ExecutionTrace` + `BusinessRule`

##### Condition Evaluator (The Core Engine)

The Oracle evaluates conditions using a minimal deterministic evaluator. No `eval()`, no AST library. Four supported patterns:

| Pattern | Example | Resolution |
|---------|---------|------------|
| Numeric comparison | `shipment_weight <= vehicle_capacity` | Resolve both sides from context, compare |
| Equality check | `shipment.status == 'ASSIGNED'` | Dot-path resolve left, literal right, compare |
| Null check | `shipment.dispatched_at != null` | Dot-path resolve, check None |
| State check | `shipment.status in ['CREATED', 'ASSIGNED']` | Dot-path resolve, membership check |

##### Value Resolution Layer

Conditions reference values that live in the execution context. Resolution works by dot-path lookup:

```
condition: "entities.shipment.status == 'ASSIGNED'"

context = {
    "entities": {
        "shipment": {
            "id": "SHIP_123",
            "type": "Shipment",
            "status": "ASSIGNED",
            "weight": 1200
        },
        "vehicle": {
            "id": "VH_001",
            "type": "Vehicle",
            "capacity": 1000
        }
    },
    "scenario": {
        "shipment_weight": 1200,
        "vehicle_capacity": 1000
    },
    "response": {
        "status": "DISPATCHED",
        "dispatched_at": "2026-03-30T10:00:00Z"
    }
}

resolve("entities.shipment.status", context) → "ASSIGNED"
resolve("entities.vehicle.capacity", context) → 1000
resolve("scenario.shipment_weight", context) → 1200
resolve("response.status", context) → "DISPATCHED"
```

##### Context Construction (Standardized)

The context is always built by a single function with a fixed shape. This prevents collisions between entity fields, scenario fields, and response fields.

```python
def build_eval_context(
    state_snapshot: dict,
    scenario: Scenario,
    last_response: dict
) -> dict:
    """
    Always produces the same shape:
    - entities.*  → current entity states from state store
    - scenario.*  → original test inputs
    - response.*  → latest API response data

    All condition paths resolve against this structure.
    """
    # Flatten entities by type name (lowercase) for cleaner paths
    # e.g., state_snapshot["SHIP_123"] = {"type": "Shipment", ...}
    # becomes entities["shipment"] = {"id": "SHIP_123", ...}
    entities = {}
    for entity_id, entity_data in state_snapshot.items():
        type_key = entity_data.get("type", "unknown").lower()
        entities[type_key] = entity_data

    return {
        "entities": entities,
        "scenario": scenario.inputs,
        "response": last_response,
    }
```

This function is called by the Executor after every API step and passed to the Oracle alongside the trace. The three top-level keys (`entities`, `scenario`, `response`) are guaranteed — no ambiguity about where a value lives.

##### Resolution Function

```python
def resolve(path: str, context: dict) -> any:
    """Dot-path lookup. 'entities.shipment.status' → context['entities']['shipment']['status']"""
    parts = path.split(".")
    current = context
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None  # unresolvable → route to LLM fallback
    return current
```

##### Evaluation Flow

1. Parse condition string → identify pattern (comparison, equality, null, state)
2. Resolve left-side value via dot-path from context
3. Resolve right-side (literal value or dot-path)
4. Apply operator
5. Compare result against actual API behavior (did it accept/reject correctly?)

If condition doesn't match any of the four patterns → LLM fallback with `reproducible: false`.

##### LLM Fallback Rules

- Only triggered when deterministic parsing fails
- Output is structured: `{"violated": bool, "confidence": float, "reasoning": str}`
- Confidence < 0.7 → verdict is `inconclusive`, escalated to Critic
- All LLM verdicts logged with `reproducible: false`
- LLM reasoning is ALWAYS logged for audit trail

#### 3.3.5 Critic Agent

- **Type**: LLM-powered (strong model: `anthropic/claude-sonnet-4`)
- **Watches for**: `critique` tasks on blackboard
- **Input**: All `OracleVerdict` objects + `BusinessRule` + `ExecutionTrace` objects
- **Analysis**:
  - True bug? → confirmed finding
  - False positive? → suggest rule revision (goes through human approval)
  - Bad test? → suggest better scenarios
  - Missing coverage? → suggest new edge cases
  - Flow gap? → suggest new flow variation

##### Feedback Routing

Each `CriticFinding` has an explicit `target`:

| Target | Action | Who Executes |
|--------|--------|-------------|
| `scenario_generator` | Append to rule's `edge_cases` | Automatic |
| `business_memory` | Update `confidence` score | Automatic |
| `business_memory` | `rule_revision_suggestion` → new proposed version | Human approval required |
| `flow_planner` | Add flow variation | Automatic |
| `oracle` | Adjust eval config (e.g., accepted status codes) | Automatic |

**What Critic NEVER does**: Directly modify an approved rule's `conditions` or `expected_effect`. Changes go through proposal → validation → human approval.

##### Loop Termination (Hard Limits)

The feedback loop stops at the FIRST condition met:

| Limit | Default | Purpose |
|-------|---------|---------|
| Max iterations per rule | 3 | Prevent infinite refinement |
| Max scenarios per rule | 20 | Diminishing returns on test count |
| Max cost per rule | $0.10 | Stop money burn |
| Empty findings | N/A | Nothing to improve → stop |
| Diminishing returns | N/A | If iteration N produces same findings as N-1 → stop |

---

## 4. LLM Layer — OpenRouter Model Routing

Every LLM call goes through OpenRouter's unified API.

| Agent | Model | Cost | LLM? |
|-------|-------|------|------|
| Extractor | `deepseek/deepseek-chat` | Low | Yes |
| Normalizer | `google/gemini-2.5-flash` | Medium | Yes |
| Rule Validator (fallback) | `google/gemini-2.5-flash` | Medium | Partial |
| Scenario Generator | `google/gemini-2.5-flash` | Medium | Yes |
| Flow Planner | `google/gemini-2.5-flash` | Medium | Partial |
| Critic | `anthropic/claude-sonnet-4` | High | Yes |
| Executor | None | Zero | No |
| Oracle (deterministic) | None | Zero | No |
| Oracle (LLM fallback) | `google/gemini-2.5-flash` | Medium | Rare |

**Cost tracking**: OpenRouter returns token usage in every response. Per-agent and per-run cost aggregated. Max budget per test run: configurable (default $0.50).

**Model override**: Request-level via API:
```json
{"model_overrides": {"critic": "anthropic/claude-sonnet-4"}}
```

---

## 5. Agent Lifecycle

### 5.1 Agent States

```
REGISTERED → IDLE → ACTIVE → DRAINING → TERMINATED
```

### 5.2 Always-On vs On-Demand

**Always-on**: Executor, Oracle, Blackboard watcher  
**On-demand**: Extractor, Normalizer, Rule Validator, Scenario Generator, Flow Planner, Critic

### 5.3 Health Monitoring (V1)

Simple heartbeat every 30s. 3 missed heartbeats → DRAINING → tasks redistributed.

### 5.4 Spawn Criteria (V2 Only — Not in V1)

V1 has a fixed set of agents. Dynamic spawning is a V2 feature:
- Demand signal (unclaimed task > 30s)
- Agent self-spawn (depth limit: 3)
- Complexity-based model selection

---

## 6. V1 Domain: Logistics

### 6.1 Entities

| Entity | Key Fields |
|--------|-----------|
| Shipment | id, weight, origin, destination, status, status_history |
| Vehicle | id, capacity, assigned_shipments |

### 6.2 Mock API Endpoints

```
POST /api/v1/shipments
  Request:  {"weight": int, "origin": str, "destination": str}
  Response: {"shipment_id": str, "status": "CREATED", "weight": int}
  Status:   201

POST /api/v1/shipments/{shipment_id}/assign
  Request:  {"vehicle_id": str}
  Response: {"shipment_id": str, "vehicle_id": str,
             "vehicle_capacity": int, "status": "ASSIGNED"}
  Status:   200

POST /api/v1/shipments/{shipment_id}/dispatch
  Request:  {}
  Response: {"shipment_id": str, "status": "DISPATCHED",
             "dispatched_at": str}
  Status:   200
```

### 6.3 Intentional Bug

The dispatch endpoint does NOT check `shipment_weight > vehicle_capacity`. It dispatches overweight shipments. The swarm must catch this.

### 6.4 Starter Rules

**Rule 1 — Constraint**:
```json
{
    "rule_id": "SHIP_001",
    "type": "constraint",
    "description": "Shipment weight must not exceed assigned vehicle capacity",
    "entities": ["Shipment", "Vehicle"],
    "conditions": ["scenario.shipment_weight <= entities.vehicle.capacity"],
    "expected_effect": ["dispatch should be rejected if weight exceeds capacity"],
    "invalid_scenarios": ["shipment_weight > vehicle_capacity should fail dispatch"],
    "edge_cases": ["shipment_weight == vehicle_capacity", "vehicle_capacity == 0"],
    "requires_llm": false
}
```

**Rule 2 — Precondition**:
```json
{
    "rule_id": "SHIP_002",
    "type": "precondition",
    "description": "Shipment must be ASSIGNED before dispatch",
    "entities": ["Shipment"],
    "conditions": ["entities.shipment.status == 'ASSIGNED'"],
    "trigger": {"endpoint": "POST /shipments/{id}/dispatch"},
    "expected_effect": ["dispatch should fail if not ASSIGNED"],
    "invalid_scenarios": ["dispatch a CREATED shipment without assigning"],
    "requires_llm": false
}
```

**Rule 3 — Postcondition**:
```json
{
    "rule_id": "SHIP_003",
    "type": "postcondition",
    "description": "After dispatch, status must be DISPATCHED and dispatched_at set",
    "entities": ["Shipment"],
    "conditions": ["entities.shipment.status == 'DISPATCHED'", "entities.shipment.dispatched_at != null"],
    "trigger": {"endpoint": "POST /shipments/{id}/dispatch"},
    "expected_effect": ["status transitions to DISPATCHED", "dispatched_at is populated"],
    "requires_llm": false
}
```

---

## 7. Storage Architecture

### 7.1 V1 (Zero Infrastructure)

| Store | Implementation |
|-------|---------------|
| Rule Store | SQLite |
| State Store | Python dict behind `StateStore` protocol |
| Execution Log | Append-only list → JSON dump |
| Blackboard | Python dict with asyncio callbacks + atomic claim |
| Artifacts | Local filesystem `./artifacts/{run_id}/` |

### 7.2 V2 (Production)

| Store | Implementation |
|-------|---------------|
| Rule Store | Postgres |
| State Store | Redis hashes |
| Execution Log | Postgres |
| Blackboard | Redis Streams + pub/sub |
| Artifacts | Postgres JSONB or S3 |

---

## 8. Build Order (Bottom-Up, No Uncertainty)

Each step is testable independently.

### Phase 1: Foundation (No LLM, No Agents)

| Step | What | Test |
|------|------|------|
| 0 | Lock Pydantic models (Section 2) | mypy passes |
| 1 | Mock logistics API, 3 endpoints, intentional bug | curl tests pass |
| 2 | Execution engine + state store, hardcoded scenarios | Traces logged correctly |
| 3 | Rule engine / Oracle, hardcoded rules | Deterministic eval works |
| 4 | End-to-end: rule → scenario → execute → validate | Catches the weight bug |

**Gate**: If Step 4 doesn't catch the bug, everything above is broken. Fix before proceeding.

### Phase 2: First Agents

| Step | What | Test |
|------|------|------|
| 5 | Scenario Generator as first LLM agent | Produces valid `Scenario` objects |
| 6 | Wire Scenario Gen → Executor → Oracle in LangGraph | Agent loop runs end-to-end |
| 7 | Flow Planner for Rule 2 (state transition) | Multi-step flows work |
| 8 | Critic Agent + feedback loop | Loop runs, terminates, produces findings |

### Phase 3: Full Ingestion

| Step | What | Test |
|------|------|------|
| 9 | Extractor + Normalizer + Rule Validator chain | Messy text → valid rule |
| 10 | Human approval API endpoints | Rules enter memory only after approval |

### Phase 4: Protocol Integration (Post-V1)

| Step | What |
|------|------|
| 11 | A2A Agent Cards for all agents, discovery endpoints |
| 12 | MCP tool exposure via fastapi-mcp |
| 13 | SSE streaming for live execution visibility |

### Phase 5: Hardening (V2)

| Step | What |
|------|------|
| 14 | Swap stores to Redis + Postgres |
| 15 | AG-UI protocol for frontend |
| 16 | Dynamic agent spawning |
| 17 | Mem0 for cross-run agent memory |

---

## 9. Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.12+ |
| API | FastAPI |
| Agent orchestration | LangGraph + langgraph-swarm |
| LLM access | OpenRouter |
| Schema validation | Pydantic v2 |
| HTTP client | httpx |
| Storage V1 | SQLite + in-memory dicts |
| Storage V2 | Postgres + Redis |
| Package manager | uv |
| Linting | ruff |
| Type checking | mypy or ty |
| Containerization | Docker + Compose |

---

## 10. Project Structure

```
swarmprobe/
├── app/
│   ├── main.py
│   ├── config.py
│   │
│   ├── schemas/
│   │   ├── rules.py
│   │   ├── scenarios.py
│   │   ├── execution.py
│   │   ├── validation.py
│   │   └── feedback.py
│   │
│   ├── agents/
│   │   ├── ingestion/
│   │   │   ├── extractor.py
│   │   │   ├── normalizer.py
│   │   │   └── rule_validator.py
│   │   ├── testing/
│   │   │   ├── scenario_generator.py
│   │   │   ├── flow_planner.py
│   │   │   ├── executor.py
│   │   │   ├── oracle.py
│   │   │   └── critic.py
│   │   └── graph.py
│   │
│   ├── memory/
│   │   ├── rule_store.py
│   │   ├── state_store.py
│   │   ├── exec_log.py
│   │   └── blackboard.py
│   │
│   ├── eval/
│   │   ├── condition_parser.py       # 4-pattern evaluator
│   │   └── resolver.py               # dot-path value resolution
│   │
│   ├── mock_api/
│   │   ├── router.py
│   │   ├── models.py
│   │   └── store.py
│   │
│   ├── llm/
│   │   ├── client.py
│   │   ├── models.py
│   │   └── structured_output.py
│   │
│   └── api/
│       ├── routes.py
│       └── sse.py
│
├── tests/
│   ├── test_schemas.py
│   ├── test_mock_api.py
│   ├── test_executor.py
│   ├── test_oracle.py
│   ├── test_condition_parser.py
│   ├── test_resolver.py
│   ├── test_flow_validation.py
│   └── test_pipeline.py
│
├── artifacts/
├── docs/
│   └── ARCHITECTURE.md
├── .env.example
├── pyproject.toml
├── ruff.toml
├── Dockerfile
├── docker-compose.yml
└── README.md
```

---

## 11. What You Will Learn

1. **Where swarm helps vs hurts**: Feedback loop is genuine swarm value. Ingestion chain is simpler as orchestrated pipeline.
2. **Coordination problems**: Blackboard contention, feedback divergence, cascading failures from bad rules.
3. **State handling**: Multi-step testing is impossible without proper state tracking.
4. **LLM limits**: Oracle must be deterministic wherever possible. LLMs hallucinate on numeric comparisons.
5. **Schema as control**: The schema IS the architecture. Without it, agents produce incompatible garbage.
6. **Cost management**: When to use $0.001/call models vs $0.01/call models.

---

## Appendix A: Protocol Stack (Phase 4+)

These protocols are NOT used in V1. They are documented here for Phase 4+ integration.

### A.1 MCP (Model Context Protocol) — Agent-to-Tool

Standardizes how agents connect to tools. The mock logistics APIs can be exposed as MCP tools via `fastapi-mcp`, letting the Executor discover API tools at runtime. Each agent can also expose its capabilities as MCP tools.

### A.2 A2A (Agent-to-Agent Protocol) — Agent Discovery

Each agent publishes an Agent Card at `/.well-known/agent-card.json`. Enables cross-process agent communication and third-party agent integration. Built on HTTP, SSE, JSON-RPC. Now at v0.3 under the Linux Foundation.

### A.3 AG-UI (Agent-User Interaction Protocol) — Agent-to-Frontend

Event-based protocol for streaming agent updates to frontends. Supports SSE and WebSockets. Enables live test execution visibility. Frontend: Next.js + CopilotKit or SvelteKit.

### A.4 Mem0 — Cross-Run Agent Memory

Persistent memory layer that survives across test runs. Scoped by `agent_id` and `run_id`. Enables the Critic to remember past test patterns and avoid redundant work. Uses vector + graph storage.

---

## Appendix B: Configuration Defaults

```python
# config.py defaults
MAX_FEEDBACK_ITERATIONS = 3
MAX_SCENARIOS_PER_RULE = 20
MAX_COST_PER_RULE_USD = 0.10
MAX_COST_PER_RUN_USD = 0.50
BLACKBOARD_TASK_TIMEOUT_SECONDS = 60
BLACKBOARD_MAX_RETRIES = 3
ORACLE_LLM_CONFIDENCE_THRESHOLD = 0.7
RULE_CONFIDENCE_REVIEW_THRESHOLD = 0.5
HEARTBEAT_INTERVAL_SECONDS = 30
HEARTBEAT_MISSED_LIMIT = 3
```

---

## Appendix C: Implementation Notes (Where Each Fix Lands in Code)

These are not architectural changes — they are implementation details to be aware of while building.

### C.1 Condition Language Drift Detection

**Problem**: Schema allows natural language conditions that the parser can't handle. LLM fallback triggers too often.

**Fix**: `requires_llm` field on `BusinessRule` (already added to model in Section 1). The Rule Validator Agent sets this during validation by running each condition through the four-pattern matcher. If any condition fails to match → `requires_llm = True`.

**Quality metric**: Track `% of rules where requires_llm == True`. High percentage = team should tighten condition language.

**Where in code**: `app/agents/ingestion/rule_validator.py` — call `condition_parser.can_evaluate(condition)` for each condition during validation. `app/eval/condition_parser.py` — expose a `can_evaluate(condition: str) -> bool` function.

### C.2 Standardized Context Construction

**Problem**: Context assembled inconsistently → subtle resolver bugs.

**Fix**: `build_eval_context()` function (specified in Section 3.3.4). Always produces `{"entities": {...}, "scenario": {...}, "response": {...}}`. All condition paths use the `entities.`, `scenario.`, `response.` prefixes.

**Where in code**: `app/eval/resolver.py` — the `build_eval_context()` and `resolve()` functions. Called by Executor after each API step, passed to Oracle.

### C.3 Flow Planner Output Validation

**Problem**: LLM-generated flow plans may reference non-existent endpoints or have broken data dependencies.

**Fix**: Deterministic validation pass after every LLM-generated `FlowPlan` (~20 lines). Checks: (1) every endpoint matches a known API route, (2) every `$state.` reference in `path_params`/`payload_map` has a corresponding `extract` in a prior step. Invalid flows → reject back to Flow Planner with specific issues.

**Where in code**: `app/agents/testing/flow_planner.py` — `validate_flow_plan(plan: FlowPlan, known_routes: list[str]) -> ValidationVerdict`. Called after LLM generation, before posting to blackboard.

### C.4 Rule Conflict Resolution (V1: Passive, V2: Active)

**Problem**: `conflicts_with` is tracked but nothing uses it.

**V1 behavior**: Passive. Conflicts are displayed during human approval. Humans decide whether conflicting rules can coexist. No code needed beyond detection at insertion time.

**V2 behavior**: Oracle checks `conflicts_with` before evaluation. If conflicting rules exist, Oracle determines which applies given the current context (e.g., "is this a priority shipment?"). This requires a conflict resolution strategy per rule pair.

**Where in code**: `app/memory/rule_store.py` — conflict detection at `insert_rule()`. V2: `app/agents/testing/oracle.py` — filter applicable rules before evaluation.

---

*End of document. No more design. Build Phase 1.*
