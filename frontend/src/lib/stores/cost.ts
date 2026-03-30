import { writable } from 'svelte/store';

export interface CostSnapshot {
  run_total_usd: number;
  max_per_run_usd: number;
  max_per_rule_usd: number;
  rule_totals_usd: Record<string, number>;
}

interface CostEventEnvelope {
  event_type?: string;
  data?: Record<string, unknown>;
}

const INITIAL_COST: CostSnapshot = {
  run_total_usd: 0,
  max_per_run_usd: 0.5,
  max_per_rule_usd: 0.1,
  rule_totals_usd: {}
};

function asObject(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null ? (value as Record<string, unknown>) : {};
}

function asNumber(value: unknown, fallback = 0): number {
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : fallback;
  }

  if (typeof value === 'string') {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  return fallback;
}

function normalizeRuleTotals(value: unknown): Record<string, number> {
  const record = asObject(value);
  const totals: Record<string, number> = {};

  for (const [key, raw] of Object.entries(record)) {
    totals[key] = asNumber(raw);
  }

  return totals;
}

const internal = writable<CostSnapshot>(INITIAL_COST);

function handleEvent(event: CostEventEnvelope): void {
  const data = asObject(event.data);

  const next: CostSnapshot = {
    run_total_usd: asNumber(data.run_total_usd),
    max_per_run_usd: asNumber(data.max_per_run_usd, INITIAL_COST.max_per_run_usd),
    max_per_rule_usd: asNumber(data.max_per_rule_usd, INITIAL_COST.max_per_rule_usd),
    rule_totals_usd: normalizeRuleTotals(data.rule_totals_usd)
  };

  internal.set(next);
}

function clear(): void {
  internal.set(INITIAL_COST);
}

export default internal;

export const costStore = {
  subscribe: internal.subscribe,
  handleEvent,
  clear
};