import { writable } from 'svelte/store';

export interface AgentState {
  agent_id: string;
  old_state: string | null;
  new_state: string;
}

interface AgentEventEnvelope {
  event_type?: string;
  data?: Record<string, unknown>;
}

function asObject(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null ? (value as Record<string, unknown>) : {};
}

function asString(value: unknown): string | undefined {
  return typeof value === 'string' && value.length > 0 ? value : undefined;
}

const internal = writable<Record<string, AgentState>>({});

function handleEvent(event: AgentEventEnvelope): void {
  const data = asObject(event.data);
  const agentId = asString(data.agent_id);

  if (!agentId) {
    return;
  }

  const nextState: AgentState = {
    agent_id: agentId,
    old_state: asString(data.old_state) ?? null,
    new_state: asString(data.new_state) ?? 'UNKNOWN'
  };

  internal.update((agents) => ({
    ...agents,
    [agentId]: nextState
  }));
}

function setSnapshot(snapshot: Record<string, AgentState>): void {
  internal.set({ ...snapshot });
}

function clear(): void {
  internal.set({});
}

export default internal;

export const agentStore = {
  subscribe: internal.subscribe,
  handleEvent,
  setSnapshot,
  clear
};