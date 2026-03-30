import { agentStore } from './stores/agents';
import { costStore } from './stores/cost';
import { executionStore } from './stores/execution';
import { taskStore } from './stores/tasks';
import { verdictStore } from './stores/verdicts';

interface StreamEnvelope {
  event_type?: string;
  event?: string;
  timestamp?: string;
  data?: Record<string, unknown>;
}

const env = import.meta.env as Record<string, string | undefined>;
const API_BASE = (env.VITE_API_URL ?? env.PUBLIC_API_URL ?? 'http://localhost:8000').replace(/\/+$/, '');

function asObject(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null ? (value as Record<string, unknown>) : {};
}

function normalizeEvent(raw: unknown): StreamEnvelope {
  const parsed = asObject(raw);
  const eventType = String(parsed.event_type ?? parsed.event ?? '');

  return {
    event_type: eventType,
    timestamp: typeof parsed.timestamp === 'string' ? parsed.timestamp : undefined,
    data: asObject(parsed.data)
  };
}

function routeEvent(envelope: StreamEnvelope): void {
  switch (envelope.event_type) {
    case 'TASK_POSTED':
    case 'TASK_CLAIMED':
    case 'TASK_COMPLETED':
    case 'TASK_DEAD':
      taskStore.handleEvent(envelope);
      break;
    case 'EXECUTION_STEP':
      executionStore.handleEvent(envelope);
      break;
    case 'VERDICT':
    case 'CRITIC_FINDING':
      verdictStore.handleEvent(envelope);
      break;
    case 'COST_UPDATE':
      costStore.handleEvent(envelope);
      break;
    case 'AGENT_STATE':
      agentStore.handleEvent(envelope);
      break;
    case 'run_started':
    case 'run_completed':
    case 'run_failed':
    default:
      break;
  }
}

export function connectSSE(): EventSource {
  const source = new EventSource(`${API_BASE}/api/v1/stream/testing`);
  let retryCount = 0;

  source.onopen = () => {
    if (retryCount > 0) {
      console.info(`SSE reconnected after ${retryCount} retries`);
    }
    retryCount = 0;
  };

  source.onmessage = (message) => {
    try {
      const parsed = JSON.parse(message.data) as unknown;
      const envelope = normalizeEvent(parsed);
      if (!envelope.event_type) {
        return;
      }
      routeEvent(envelope);
    } catch (error) {
      console.warn('Unable to parse SSE payload', error);
    }
  };

  source.onerror = () => {
    retryCount += 1;
    console.warn(`SSE connection interrupted; reconnect attempt ${retryCount}`);
  };

  return source;
}