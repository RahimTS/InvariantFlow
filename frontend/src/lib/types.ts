export type TaskStatus = 'posted' | 'claimed' | 'in_progress' | 'completed' | 'dead';

export interface TaskItem {
  task_id: string;
  type: string;
  status?: TaskStatus;
  claimed_by?: string | null;
  claimed_at?: string | null;
  completed_at?: string | null;
  retry_count?: number;
  data?: Record<string, unknown>;
  error?: string;
  result?: Record<string, unknown>;
}

export interface ExecutionStep {
  run_id?: string;
  scenario_id?: string;
  step_number: number;
  endpoint: string;
  status_code: number;
  latency_ms: number;
}

export interface VerdictItem {
  trace_id: string;
  rule_id: string;
  scenario_id: string;
  result: 'pass' | 'fail' | 'inconclusive';
  violated_conditions: string[];
}

export interface AgentStateItem {
  agent_id: string;
  old_state?: string | null;
  new_state: string;
}

export interface CostSnapshot {
  run_total_usd: number;
  max_per_run_usd: number;
  max_per_rule_usd: number;
  rule_totals_usd: Record<string, number>;
}

export interface SseEvent<T = Record<string, unknown>> {
  event?: string;
  event_type?: string;
  run_id?: string;
  timestamp?: string;
  data: T;
}
