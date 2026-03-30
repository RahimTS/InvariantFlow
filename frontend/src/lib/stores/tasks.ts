import { writable } from 'svelte/store';

export interface Task {
  task_id: string;
  type: string;
  status: string;
  agent_id?: string;
  rule_id?: string;
  error?: string;
  [key: string]: any;
}

interface TaskEventEnvelope {
  event_type?: string;
  data?: Record<string, unknown>;
}

const MAX_TASKS = 100;

function asObject(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null ? (value as Record<string, unknown>) : {};
}

function asString(value: unknown): string | undefined {
  return typeof value === 'string' && value.length > 0 ? value : undefined;
}

function statusFromEvent(eventType: string): string {
  switch (eventType) {
    case 'TASK_POSTED':
      return 'posted';
    case 'TASK_CLAIMED':
      return 'claimed';
    case 'TASK_COMPLETED':
      return 'completed';
    case 'TASK_DEAD':
      return 'dead';
    default:
      return 'posted';
  }
}

const internal = writable<Task[]>([]);

function handleEvent(event: TaskEventEnvelope): void {
  const eventType = event.event_type ?? '';
  const data = asObject(event.data);
  const taskId = asString(data.task_id);

  if (!taskId) {
    return;
  }

  const baseTask: Task = {
    ...data,
    task_id: taskId,
    type: asString(data.type) ?? 'unknown',
    status: statusFromEvent(eventType),
    agent_id: asString(data.agent_id),
    rule_id: asString(data.rule_id),
    error: asString(data.error)
  };

  internal.update((tasks) => {
    if (eventType === 'TASK_POSTED') {
      return [baseTask, ...tasks.filter((task) => task.task_id !== taskId)].slice(0, MAX_TASKS);
    }

    const index = tasks.findIndex((task) => task.task_id === taskId);
    if (index === -1) {
      return [baseTask, ...tasks].slice(0, MAX_TASKS);
    }

    const next = [...tasks];
    const current = next[index];
    const patch: Partial<Task> = { ...data };

    if (eventType === 'TASK_CLAIMED') {
      patch.status = 'claimed';
      patch.agent_id = asString(data.agent_id);
    } else if (eventType === 'TASK_COMPLETED') {
      patch.status = 'completed';
    } else if (eventType === 'TASK_DEAD') {
      patch.status = 'dead';
      patch.error = asString(data.error);
    }

    next[index] = {
      ...current,
      ...patch,
      task_id: current.task_id,
      type: asString((patch as Record<string, unknown>).type) ?? current.type,
      status: asString((patch as Record<string, unknown>).status) ?? current.status
    };

    return next.slice(0, MAX_TASKS);
  });
}

function clear(): void {
  internal.set([]);
}

export default internal;

export const taskStore = {
  subscribe: internal.subscribe,
  handleEvent,
  clear
};