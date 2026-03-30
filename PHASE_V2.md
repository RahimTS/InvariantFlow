# InvariantFlow — Phase V2: Production Hardening + Frontend

## Design Document (v1.0)

**Author**: Rahim + Claude  
**Date**: March 2026  
**Status**: Pre-implementation  
**Depends on**: ARCHITECTURE.md v0.3 (all phases 1-5 groundwork complete)

---

## 0. What This Phase Delivers

Two things that don't exist yet:

1. **Real infrastructure** — Redis for state/blackboard, Postgres for rules/logs, real MCP/A2A protocol endpoints (replacing shims). Docker Compose for one-command startup.

2. **A frontend you can demo** — SvelteKit dashboard where someone pastes a business rule, watches agents claim tasks from the blackboard in real-time, sees API calls fire, watches the Oracle flag violations, and sees the Critic feedback loop iterate. All streaming via SSE.

**What this does NOT change**: The core agent logic, schemas, condition parser, Oracle, or Critic. Those are done and working. This phase swaps storage backends and adds visibility.

---

## 1. Frontend Recommendation: SvelteKit

### Why SvelteKit over the alternatives

**Not Next.js + Three.js**: Three.js adds significant complexity (scene setup, camera, lighting, mesh management) for what's fundamentally a 2D dashboard with streaming data. A 3D swarm visualization looks cool in a demo reel but doesn't help someone understand what the system is doing. The "wow" factor comes from watching agents work in real-time, not from spinning particles. If you want a graph visualization later, D3.js force-directed graphs inside Svelte are simpler and more informative than Three.js.

**Not Next.js + CopilotKit**: CopilotKit gives you AG-UI integration for free, but it locks you into a chat-widget UI paradigm. InvariantFlow is not a chatbot — it's a testing swarm. The natural UI is a dashboard with multiple live panels (task board, execution trace, verdicts, cost), not a chat thread. CopilotKit's React components don't map well to this layout.

**SvelteKit wins because**:

- **Native SSE handling**: `EventSource` is trivial in Svelte. The `sveltekit-sse` library adds reconnection, transforms, and JSON parsing out of the box. Your FastAPI backend already emits SSE events — the frontend just connects.
- **Reactive stores = streaming state**: Svelte's `$state` rune and stores update the DOM automatically when SSE events arrive. No `useEffect` chains, no state management library. An SSE event arrives, the store updates, the UI re-renders. That's it.
- **Lighter than React**: No virtual DOM diffing overhead. For a dashboard with many rapidly updating panels, Svelte's compiled reactivity is noticeably smoother.
- **FastAPI + SvelteKit is a proven stack**: Multiple production examples and tutorials exist for exactly this pattern (real-time dashboards with FastAPI SSE + Svelte frontend).
- **Portfolio differentiation**: Most AI projects use React/Next.js. A SvelteKit frontend signals that you pick tools based on fit, not habit.

### What the frontend shows

The dashboard has four main panels, all updating via SSE:

**Panel 1 — Task Board (Blackboard live view)**
Shows all tasks on the blackboard with their current status. Tasks flow through states: `posted → claimed → in_progress → completed`. Color-coded by status. Shows which agent claimed each task. New tasks appear at the top in real-time as agents post them.

**Panel 2 — Execution Stream**
As the Executor fires API calls, each request/response pair streams in. Shows: endpoint, payload, status code, latency. Violations are highlighted in red when the Oracle flags them. The execution trace builds up step by step.

**Panel 3 — Verdicts & Findings**
Oracle verdicts appear as they're produced. Pass/fail/inconclusive with evidence. When the Critic runs, its findings stream in with their targets and suggested actions. The feedback loop iteration count is visible.

**Panel 4 — System Status**
Agent states (idle/active/draining), cost tracker snapshot (per-rule and per-run USD), rule store summary (approved/proposed/deprecated counts), dead task count.

**Additional views** (separate routes):

- `/rules` — Rule management. List all rules, view history, approve/reject pending rules. The human gate UI.
- `/ingest` — Paste raw text (Jira/PRD), submit for ingestion, watch the extractor → normalizer → validator chain process it, see proposed rules appear.
- `/runs` — Historical run list with drill-down into past results.

---

## 2. Backend Hardening

### 2.1 Postgres — Rule Store + Execution Log

Replace SQLite with Postgres for rules and execution logs. The `RuleStore` class interface stays the same — swap the implementation behind it.

**Why Postgres over SQLite for V2**:
- Concurrent access from multiple workers (SQLite has write locking issues)
- Proper indexing on `rule_id`, `status`, `version`
- JSONB columns for flexible querying of rule data
- Foundation for future features (full-text search on rule descriptions, materialized views for analytics)

**Schema**:

```sql
CREATE TABLE business_rules (
    pk          TEXT PRIMARY KEY,          -- '{rule_id}_v{version}'
    rule_id     TEXT NOT NULL,
    version     INTEGER NOT NULL,
    status      TEXT NOT NULL,             -- 'proposed' | 'approved' | 'deprecated'
    data        JSONB NOT NULL,            -- full BusinessRule JSON
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(rule_id, version)
);

CREATE INDEX idx_rules_status ON business_rules(status);
CREATE INDEX idx_rules_rule_id ON business_rules(rule_id);

CREATE TABLE execution_traces (
    trace_id    TEXT PRIMARY KEY,
    rule_id     TEXT NOT NULL,
    scenario_id TEXT NOT NULL,
    flow_id     TEXT NOT NULL,
    run_id      TEXT,
    data        JSONB NOT NULL,            -- full ExecutionTrace JSON
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_traces_rule_id ON execution_traces(rule_id);
CREATE INDEX idx_traces_run_id ON execution_traces(run_id);

CREATE TABLE run_history (
    run_id      TEXT PRIMARY KEY,
    status      TEXT NOT NULL,             -- 'started' | 'completed' | 'failed'
    metadata    JSONB,
    summary     JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**Library**: `asyncpg` (async Postgres driver, fastest Python option). Connection pooling via `asyncpg.create_pool()`.

**Migration from SQLite**: The `RuleStore` class gets a `PostgresRuleStore` sibling. A config flag (`STORAGE_BACKEND=postgres`) selects which implementation to use. The existing `RuleStore` (SQLite) remains as the default for local dev without Docker.

### 2.2 Redis — State Store + Blackboard + SSE Pub/Sub

Replace in-memory dicts with Redis for state tracking, task board, and SSE event broadcasting.

**Why Redis**:
- State Store: Redis hashes with TTL for automatic cleanup of old test runs
- Blackboard: Redis Streams for ordered task delivery with consumer groups (true atomic claiming)
- SSE pub/sub: Redis pub/sub replaces the in-memory `asyncio.Queue` for broadcasting events to multiple SSE clients. This means the frontend SSE stream works even if the backend is restarted (clients reconnect and get new events).

**State Store mapping**:
```
Key pattern: state:{run_id}:{entity_id}
Type: Hash
Fields: id, type, status, status_history (JSON), weight, ...
TTL: 1 hour (configurable — test run state doesn't need to live forever)
```

**Blackboard mapping**:
```
Stream: blackboard:tasks
Consumer group: swarm_workers
Message fields: task_id, type, rule_id, status, claimed_by, data (JSON)
```

Redis Streams give us exactly what the in-memory blackboard does but with persistence and true atomic consumer group claiming (`XREADGROUP` with `XACK`). No more `asyncio.Lock` — Redis handles contention natively.

**SSE pub/sub mapping**:
```
Channel: events:testing
Payload: JSON event (same shape as current RunRegistry events)
```

The SSE endpoint subscribes to this Redis channel. When any backend component publishes an event (agent claimed a task, execution completed, verdict produced), all connected SSE clients receive it.

**Library**: `redis.asyncio` (redis-py async client).

**Migration**: Same pattern as Postgres — `RedisStateStore`, `RedisBlackboard` classes implementing the same protocols. Config flag selects implementation.

### 2.3 Storage Selection Config

```python
# config.py additions
storage_backend: Literal["local", "docker"] = "local"

# "local" = SQLite + in-memory (current behavior, no Docker needed)
# "docker" = Postgres + Redis (requires Docker Compose)

postgres_dsn: str = "postgresql://invariantflow:invariantflow@localhost:5432/invariantflow"
redis_url: str = "redis://localhost:6379/0"
redis_state_ttl_seconds: int = 3600
```

A factory function creates the right store instances based on config:
```python
def create_stores(settings: Settings) -> tuple[RuleStore, StateStore, Blackboard, ExecutionLog]:
    if settings.storage_backend == "docker":
        return (
            PostgresRuleStore(settings.postgres_dsn),
            RedisStateStore(settings.redis_url, ttl=settings.redis_state_ttl_seconds),
            RedisBlackboard(settings.redis_url),
            PostgresExecutionLog(settings.postgres_dsn),
        )
    return (
        RuleStore(settings.sqlite_db_path),
        InMemoryStateStore(),
        Blackboard(),
        ExecutionLog(),
    )
```

---

## 3. Real Protocol Integration

### 3.1 MCP via fastapi-mcp (Replace the shim)

The current `/api/v1/mcp/tools` and `/api/v1/mcp/call` endpoints are shims. Replace with real MCP using `fastapi-mcp`.

```python
from fastapi import FastAPI
from fastapi_mcp import FastApiMCP

app = FastAPI(title="InvariantFlow")
# ... include routers ...

mcp = FastApiMCP(app, name="InvariantFlow MCP")
mcp.mount()  # auto-generates MCP server at /mcp
```

This auto-exposes every FastAPI endpoint as an MCP tool. The mock logistics API endpoints become MCP-discoverable tools. Any MCP client (Claude Desktop, Cursor, etc.) can connect and invoke InvariantFlow operations.

**Selective exposure**: Not all endpoints should be MCP tools. Use `fastapi-mcp`'s filtering to expose only:
- `POST /api/v1/testing/run` — trigger a test run
- `POST /api/v1/ingestion/ingest` — ingest rules
- `GET /api/v1/rules/pending` — list pending rules
- `POST /api/v1/rules/{id}/approve` — approve a rule
- `GET /api/v1/stream/testing` — SSE stream

### 3.2 A2A Agent Cards (Replace static dict)

The current `/api/v1/agents/cards` returns a hardcoded list. Replace with proper A2A-compliant agent cards using the `a2a-sdk`.

Each agent gets a proper card at `/.well-known/agent-card.json` following the A2A spec:

```json
{
    "name": "InvariantFlow",
    "description": "Business logic API validator swarm",
    "version": "0.2.0",
    "url": "http://localhost:8000",
    "capabilities": {
        "streaming": true,
        "pushNotifications": false
    },
    "skills": [
        {
            "id": "test_rules",
            "name": "Test business rules against APIs",
            "description": "Execute test scenarios for approved business rules and report violations"
        },
        {
            "id": "ingest_rules",
            "name": "Ingest business specifications",
            "description": "Extract and normalize business rules from raw text"
        }
    ],
    "defaultInputModes": ["text/plain"],
    "defaultOutputModes": ["application/json"]
}
```

The per-agent cards at `/api/v1/agents/{agent_id}/card` provide individual agent metadata for discovery.

### 3.3 AG-UI Event Shaping

The current SSE stream emits raw events. Shape them to match AG-UI event types for frontend consumption:

```python
# AG-UI compatible event types we emit
EVENT_TYPES = {
    "RUN_START":        "lifecycle",    # run began
    "TASK_POSTED":      "tool_call",    # agent posted a task
    "TASK_CLAIMED":     "tool_call",    # agent claimed a task
    "EXECUTION_STEP":   "tool_result",  # single API call completed
    "VERDICT":          "tool_result",  # Oracle verdict produced
    "CRITIC_FINDING":   "text_delta",   # Critic finding streamed
    "RUN_COMPLETE":     "lifecycle",    # run finished
    "COST_UPDATE":      "state_delta",  # cost tracker updated
    "AGENT_STATE":      "state_delta",  # agent state changed
}
```

Each SSE event has a consistent envelope:
```json
{
    "event_type": "TASK_CLAIMED",
    "timestamp": "2026-03-30T...",
    "data": {
        "task_id": "...",
        "agent_id": "scenario_generator",
        "rule_id": "SHIP_001"
    }
}
```

The SvelteKit frontend consumes these and routes them to the appropriate panel.

---

## 4. Docker Compose

### 4.1 Services

```yaml
version: "3.9"

services:
  postgres:
    image: postgres:17-alpine
    environment:
      POSTGRES_USER: invariantflow
      POSTGRES_PASSWORD: invariantflow
      POSTGRES_DB: invariantflow
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./db/init.sql:/docker-entrypoint-initdb.d/init.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U invariantflow"]
      interval: 5s
      timeout: 3s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5

  backend:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    environment:
      STORAGE_BACKEND: docker
      POSTGRES_DSN: postgresql://invariantflow:invariantflow@postgres:5432/invariantflow
      REDIS_URL: redis://redis:6379/0
      OPENROUTER_API_KEY: ${OPENROUTER_API_KEY:-}
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    ports:
      - "5173:5173"
    environment:
      PUBLIC_API_URL: http://backend:8000
    depends_on:
      - backend

volumes:
  pgdata:
```

### 4.2 Startup

```bash
cp .env.example .env
# add OPENROUTER_API_KEY to .env (optional — deterministic mode works without it)
docker compose up --build
```

- Frontend: http://localhost:5173
- Backend API docs: http://localhost:8000/docs
- MCP endpoint: http://localhost:8000/mcp

### 4.3 Local dev (no Docker)

Everything still works without Docker:

```bash
# .env
STORAGE_BACKEND=local

uv run uvicorn app.main:app --reload
cd frontend && npm run dev
```

SQLite + in-memory stores. No Postgres or Redis needed. The config flag controls which backend is used.

---

## 5. SvelteKit Frontend Architecture

### 5.1 Project Structure

```
frontend/
├── src/
│   ├── lib/
│   │   ├── api.ts              # Fetch wrappers for backend API
│   │   ├── sse.ts              # SSE connection manager
│   │   ├── stores/
│   │   │   ├── tasks.ts        # Blackboard task state
│   │   │   ├── verdicts.ts     # Oracle verdicts
│   │   │   ├── execution.ts    # Execution trace stream
│   │   │   ├── agents.ts       # Agent status
│   │   │   ├── cost.ts         # Cost tracking
│   │   │   └── rules.ts        # Rule store state
│   │   ├── types.ts            # TypeScript types mirroring Python schemas
│   │   └── components/
│   │       ├── TaskBoard.svelte
│   │       ├── ExecutionStream.svelte
│   │       ├── VerdictPanel.svelte
│   │       ├── SystemStatus.svelte
│   │       ├── RuleCard.svelte
│   │       ├── CostBadge.svelte
│   │       └── AgentBadge.svelte
│   ├── routes/
│   │   ├── +page.svelte        # Main dashboard (4 panels)
│   │   ├── +layout.svelte      # Nav + SSE connection setup
│   │   ├── rules/
│   │   │   ├── +page.svelte    # Rule management
│   │   │   └── [id]/+page.svelte  # Rule detail + history
│   │   ├── ingest/
│   │   │   └── +page.svelte    # Text ingestion form
│   │   └── runs/
│   │       ├── +page.svelte    # Run history list
│   │       └── [id]/+page.svelte  # Run detail drill-down
│   └── app.html
├── static/
├── svelte.config.js
├── tailwind.config.js          # Tailwind for styling
├── package.json
├── Dockerfile
└── tsconfig.json
```

### 5.2 SSE Connection (Core Pattern)

The SSE connection is established once in the layout and events are routed to stores:

```typescript
// src/lib/sse.ts
import { taskStore } from './stores/tasks';
import { verdictStore } from './stores/verdicts';
import { executionStore } from './stores/execution';
import { costStore } from './stores/cost';
import { agentStore } from './stores/agents';

export function connectSSE(apiUrl: string) {
    const es = new EventSource(`${apiUrl}/api/v1/stream/testing`);

    es.addEventListener('message', (event) => {
        const data = JSON.parse(event.data);
        routeEvent(data);
    });

    es.onerror = () => {
        // Auto-reconnect is built into EventSource
        console.warn('SSE connection lost, reconnecting...');
    };

    return es;
}

function routeEvent(event: any) {
    switch (event.event_type || event.event) {
        case 'TASK_POSTED':
        case 'TASK_CLAIMED':
        case 'TASK_COMPLETED':
            taskStore.handleEvent(event);
            break;
        case 'EXECUTION_STEP':
            executionStore.handleEvent(event);
            break;
        case 'VERDICT':
            verdictStore.handleEvent(event);
            break;
        case 'COST_UPDATE':
            costStore.handleEvent(event);
            break;
        case 'AGENT_STATE':
            agentStore.handleEvent(event);
            break;
        case 'run_started':
        case 'run_completed':
        case 'run_failed':
            // Update all stores with run lifecycle
            break;
    }
}
```

### 5.3 Reactive Store Pattern

Each store is a Svelte `$state` rune that updates when SSE events arrive:

```typescript
// src/lib/stores/tasks.ts
let tasks = $state<Task[]>([]);

export const taskStore = {
    get tasks() { return tasks; },

    handleEvent(event: any) {
        const taskData = event.data;
        const idx = tasks.findIndex(t => t.task_id === taskData.task_id);
        if (idx >= 0) {
            tasks[idx] = { ...tasks[idx], ...taskData };
        } else {
            tasks = [taskData, ...tasks];
        }
    },

    clear() { tasks = []; }
};
```

### 5.4 Styling

Tailwind CSS for utility styling. Dark mode by default (matches most dev tool aesthetics). Minimal custom CSS — Tailwind handles layout, spacing, colors.

Color coding for task/verdict states:
- Posted → gray
- Claimed → blue
- In progress → amber
- Completed → green
- Failed → red
- Dead → dark red
- Pass verdict → green
- Fail verdict → red
- Inconclusive → amber

---

## 6. Backend SSE Event Enrichment

The current `RunRegistry.publish()` emits basic events. For the frontend to work, every significant action in the testing pipeline needs to emit an event.

### 6.1 Events to Add

| Event | Source | When | Data |
|-------|--------|------|------|
| `TASK_POSTED` | Blackboard | `post_task()` called | task_id, type, rule_id |
| `TASK_CLAIMED` | Blackboard | `claim_task()` called | task_id, agent_id |
| `TASK_COMPLETED` | Blackboard | `complete_task()` called | task_id, result summary |
| `TASK_DEAD` | Blackboard | Max retries exceeded | task_id, error |
| `EXECUTION_STEP` | Executor | After each API call | step_number, endpoint, status_code, latency_ms |
| `VERDICT` | Oracle | After evaluation | rule_id, scenario_id, result, violated_conditions |
| `CRITIC_FINDING` | Critic | Per finding produced | type, target, detail, action |
| `COST_UPDATE` | CostTracker | After each LLM call | run_total_usd, rule_totals |
| `AGENT_STATE` | Lifecycle Manager | State transition | agent_id, old_state, new_state |

### 6.2 Implementation

The Blackboard, Executor, Oracle, Critic, and CostTracker each get an optional `event_emitter` callback:

```python
class Blackboard:
    def __init__(self, ..., event_emitter=None):
        self._emit = event_emitter or (lambda e: None)

    async def post_task(self, task_id, task_type, data=None):
        # ... existing logic ...
        self._emit({"event_type": "TASK_POSTED", "data": {"task_id": task_id, "type": task_type, ...}})
```

The emitter publishes to either the in-memory `RunRegistry` (local mode) or Redis pub/sub (Docker mode). The SSE endpoint subscribes to the same source.

---

## 7. Build Order

### Step 1: Backend — Postgres stores

Implement `PostgresRuleStore` and `PostgresExecutionLog` using `asyncpg`. Add `db/init.sql` with the schema. Wire the factory function. Test with existing test suite against Postgres.

### Step 2: Backend — Redis stores

Implement `RedisStateStore` (Redis hashes) and `RedisBlackboard` (Redis Streams). Implement Redis pub/sub event emitter. Test with existing test suite against Redis.

### Step 3: Docker Compose

Write `docker-compose.yml` with Postgres, Redis, and backend services. Add backend `Dockerfile`. Verify `docker compose up` starts everything and the existing API works with Docker storage.

### Step 4: Backend — SSE event enrichment

Add event emission to Blackboard, Executor, Oracle, Critic, CostTracker. Add Redis pub/sub subscriber to SSE endpoint. Verify events stream correctly via `curl` to the SSE endpoint.

### Step 5: Backend — Real MCP + A2A

Install `fastapi-mcp`, replace shim with real MCP server. Update A2A agent card to spec. Test MCP discovery from an external client.

### Step 6: Frontend — SvelteKit scaffold

Initialize SvelteKit project, Tailwind config, TypeScript types matching Python schemas. SSE connection manager. Empty page shells for all routes.

### Step 7: Frontend — Dashboard panels

Build the four main panels (TaskBoard, ExecutionStream, VerdictPanel, SystemStatus). Connect to SSE stores. Style with Tailwind.

### Step 8: Frontend — Rule management

Rule list, detail, history, approve/reject UI. Ingestion page with text input.

### Step 9: Frontend — Docker integration

Add frontend `Dockerfile`. Add to `docker-compose.yml`. Verify full stack runs with one command.

### Step 10: Polish

README with screenshots/GIF, one-command demo instructions, .env.example with clear documentation.

---

## 8. Tech Stack Additions

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Postgres driver | asyncpg | Async Postgres, connection pooling |
| Redis driver | redis.asyncio | Async Redis, pub/sub, streams |
| MCP | fastapi-mcp | Auto-expose endpoints as MCP tools |
| A2A | a2a-sdk (or manual JSON) | Agent card spec compliance |
| Frontend | SvelteKit 2+ | Dashboard framework |
| Frontend styling | Tailwind CSS 4 | Utility-first styling |
| Frontend SSE | Native EventSource | SSE consumption (no library needed) |
| Containerization | Docker Compose | Local dev stack |

---

## 9. File Changes Summary

### New files

```
db/
  init.sql                          # Postgres schema

app/memory/
  postgres_rule_store.py            # asyncpg RuleStore
  postgres_exec_log.py              # asyncpg ExecutionLog
  redis_state_store.py              # Redis hash StateStore
  redis_blackboard.py               # Redis Streams Blackboard
  redis_events.py                   # Redis pub/sub event emitter
  factory.py                        # Store factory (local vs docker)

frontend/                           # Entire SvelteKit app (Section 5)
  Dockerfile
  package.json
  svelte.config.js
  tailwind.config.js
  src/...

docker-compose.yml
Dockerfile                          # Backend Dockerfile
.env.example
```

### Modified files

```
app/config.py                       # Add storage_backend, postgres_dsn, redis_url
app/main.py                         # Use factory for store creation, startup/shutdown hooks
app/memory/blackboard.py            # Add event_emitter callback
app/agents/testing/executor.py      # Add event_emitter for EXECUTION_STEP
app/agents/testing/oracle.py        # Add event_emitter for VERDICT
app/agents/testing/critic.py        # Add event_emitter for CRITIC_FINDING
app/llm/cost.py                     # Add event_emitter for COST_UPDATE
app/api/sse.py                      # Subscribe to Redis pub/sub in Docker mode
app/api/protocols.py                # Replace MCP shim with fastapi-mcp, update A2A cards
```

### Unchanged files (core logic stays as-is)

```
app/schemas/*                       # All Pydantic models — no changes
app/eval/*                          # Condition parser + resolver — no changes
app/agents/testing/scenario_generator.py  # Logic unchanged (event emission optional)
app/agents/testing/flow_planner.py  # Fully deterministic — no changes
app/agents/testing/rule_runner.py   # Phase 1 runner — preserved
app/agents/graph.py                 # LangGraph wiring — no changes to graph structure
app/agents/ingestion/*              # Ingestion chain — no changes
```

---

## 10. Configuration Defaults (Appendix)

```python
# New config additions for V2
storage_backend: Literal["local", "docker"] = "local"
postgres_dsn: str = "postgresql://invariantflow:invariantflow@localhost:5432/invariantflow"
redis_url: str = "redis://localhost:6379/0"
redis_state_ttl_seconds: int = 3600
redis_events_channel: str = "events:testing"
frontend_url: str = "http://localhost:5173"
```

---

## 11. What This Unlocks

After this phase:

1. **One-command demo**: `docker compose up` → open `http://localhost:5173` → paste a rule → watch the swarm work.
2. **MCP integration**: Connect Claude Desktop or Cursor to InvariantFlow's MCP endpoint and trigger test runs from your IDE.
3. **Persistent history**: Test runs survive backend restarts. Rule evolution is tracked in Postgres with full version history.
4. **Multi-client SSE**: Multiple browser tabs can watch the same test run in real-time (Redis pub/sub fans out to all subscribers).
5. **Portfolio piece**: A visual demo that shows the architecture in action, not just API responses in a terminal.

---

*End of document. Start with Step 1 (Postgres stores).*
