import { writable } from 'svelte/store';

export interface ExecutionStep {
  step_number: number;
  endpoint: string;
  status_code: number;
  latency_ms: number;
  rule_id?: string;
  scenario_id?: string;
  timestamp?: string;
}

interface ExecutionEventEnvelope {
  event_type?: string;
  timestamp?: string;
  data?: Record<string, unknown>;
}

const MAX_STEPS = 200;

function asObject(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null ? (value as Record<string, unknown>) : {};
}

function asString(value: unknown): string | undefined {
  return typeof value === 'string' && value.length > 0 ? value : undefined;
}

function asNumber(value: unknown): number {
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : 0;
  }

  if (typeof value === 'string') {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }

  return 0;
}

const internal = writable<ExecutionStep[]>([]);

function handleEvent(event: ExecutionEventEnvelope): void {
  const data = asObject(event.data);
  const endpoint = asString(data.endpoint);

  if (!endpoint) {
    return;
  }

  const step: ExecutionStep = {
    step_number: asNumber(data.step_number),
    endpoint,
    status_code: asNumber(data.status_code),
    latency_ms: asNumber(data.latency_ms),
    rule_id: asString(data.rule_id),
    scenario_id: asString(data.scenario_id),
    timestamp: asString(data.timestamp) ?? event.timestamp
  };

  internal.update((steps) => [...steps, step].slice(-MAX_STEPS));
}

function clear(): void {
  internal.set([]);
}

export default internal;

export const executionStore = {
  subscribe: internal.subscribe,
  handleEvent,
  clear
};