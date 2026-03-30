CREATE TABLE IF NOT EXISTS business_rules (
    pk          TEXT PRIMARY KEY,
    rule_id     TEXT NOT NULL,
    version     INTEGER NOT NULL,
    status      TEXT NOT NULL,
    data        JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(rule_id, version)
);

CREATE INDEX IF NOT EXISTS idx_rules_status ON business_rules(status);
CREATE INDEX IF NOT EXISTS idx_rules_rule_id ON business_rules(rule_id);

CREATE TABLE IF NOT EXISTS execution_traces (
    trace_id    TEXT PRIMARY KEY,
    rule_id     TEXT NOT NULL,
    scenario_id TEXT NOT NULL,
    flow_id     TEXT NOT NULL,
    run_id      TEXT,
    data        JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_traces_rule_id ON execution_traces(rule_id);
CREATE INDEX IF NOT EXISTS idx_traces_run_id ON execution_traces(run_id);

CREATE TABLE IF NOT EXISTS run_history (
    run_id      TEXT PRIMARY KEY,
    status      TEXT NOT NULL,
    metadata    JSONB,
    summary     JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

