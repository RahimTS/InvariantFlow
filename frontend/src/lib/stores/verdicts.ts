import { writable } from 'svelte/store';

export interface Verdict {
  rule_id: string;
  scenario_id: string;
  result: 'pass' | 'fail' | 'inconclusive';
  violated_conditions: string[];
  evaluation_method: string;
  [key: string]: any;
}

export interface CriticFinding {
  type: string;
  target: string;
  detail: string;
  action?: string;
  rule_id?: string;
  [key: string]: any;
}

export type VerdictStoreValue = Verdict[] & { findings?: CriticFinding[] };

interface VerdictEventEnvelope {
  event_type?: string;
  data?: Record<string, unknown>;
}

const MAX_VERDICTS = 100;
const MAX_FINDINGS = 100;

function asObject(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null ? (value as Record<string, unknown>) : {};
}

function asString(value: unknown): string | undefined {
  return typeof value === 'string' && value.length > 0 ? value : undefined;
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value.map((item) => String(item));
}

function normalizeResult(value: unknown): 'pass' | 'fail' | 'inconclusive' {
  if (value === 'pass' || value === 'fail' || value === 'inconclusive') {
    return value;
  }

  return 'inconclusive';
}

function withFindings(verdicts: Verdict[], findings: CriticFinding[]): VerdictStoreValue {
  const next = [...verdicts] as VerdictStoreValue;
  next.findings = [...findings];
  return next;
}

const internal = writable<VerdictStoreValue>(withFindings([], []));

function handleEvent(event: VerdictEventEnvelope): void {
  const eventType = event.event_type ?? '';
  const data = asObject(event.data);

  internal.update((current) => {
    const findings = [...(current.findings ?? [])];

    if (eventType === 'CRITIC_FINDING') {
      const finding: CriticFinding = {
        ...data,
        type: asString(data.type) ?? 'unknown',
        target: asString(data.target) ?? 'unknown',
        detail: asString(data.detail) ?? '',
        action: asString(data.action),
        rule_id: asString(data.rule_id)
      };

      findings.push(finding);
      return withFindings(current, findings.slice(-MAX_FINDINGS));
    }

    if (eventType !== 'VERDICT') {
      return current;
    }

    const verdict: Verdict = {
      ...data,
      rule_id: asString(data.rule_id) ?? 'unknown',
      scenario_id: asString(data.scenario_id) ?? 'unknown',
      result: normalizeResult(data.result),
      violated_conditions: asStringArray(data.violated_conditions),
      evaluation_method: asString(data.evaluation_method) ?? 'oracle'
    };

    return withFindings([verdict, ...current].slice(0, MAX_VERDICTS), findings);
  });
}

function clear(): void {
  internal.set(withFindings([], []));
}

export default internal;

export const verdictStore = {
  subscribe: internal.subscribe,
  handleEvent,
  clear
};