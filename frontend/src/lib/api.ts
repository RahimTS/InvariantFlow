type ApproveBody = { approved_by?: string; edits?: Record<string, any> };

const env = import.meta.env as Record<string, string | undefined>;
const API_BASE = (env.VITE_API_URL ?? env.PUBLIC_API_URL ?? 'http://localhost:8000').replace(/\/+$/, '');

async function requestJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers
  });

  const text = await response.text();
  let payload: unknown = null;

  if (text) {
    try {
      payload = JSON.parse(text) as unknown;
    } catch {
      payload = text;
    }
  }

  if (!response.ok) {
    const detail = typeof payload === 'object' && payload ? JSON.stringify(payload) : String(payload ?? response.statusText);
    throw new Error(`${response.status} ${response.statusText}: ${detail}`);
  }

  return payload as T;
}

export async function runTesting(opts: {
  mode: string;
  seed_starter: boolean;
  entity?: string;
}): Promise<any> {
  return requestJson<any>('/api/v1/testing/run', {
    method: 'POST',
    body: JSON.stringify(opts)
  });
}

export async function getAgentStatus(): Promise<{ count: number; agents: any[] }> {
  return requestJson<{ count: number; agents: any[] }>('/api/v1/agents/status');
}

export async function getDeadTasks(): Promise<{ count: number; tasks: any[] }> {
  return requestJson<{ count: number; tasks: any[] }>('/api/v1/tasks/dead');
}

export async function getPendingRules(): Promise<{ count: number; rules: any[] }> {
  return requestJson<{ count: number; rules: any[] }>('/api/v1/rules/pending');
}

export async function approveRule(ruleId: string, body?: ApproveBody | string): Promise<any> {
  const payload = typeof body === 'string' ? { approved_by: body } : body ?? {};
  return requestJson<any>(`/api/v1/rules/${encodeURIComponent(ruleId)}/approve`, {
    method: 'POST',
    body: JSON.stringify(payload)
  });
}

export async function rejectRule(ruleId: string, reason: string): Promise<any> {
  return requestJson<any>(`/api/v1/rules/${encodeURIComponent(ruleId)}/reject`, {
    method: 'POST',
    body: JSON.stringify({ reason })
  });
}

export async function getRule(ruleId: string): Promise<any> {
  return requestJson<any>(`/api/v1/rules/${encodeURIComponent(ruleId)}`);
}

export async function getRuleHistory(ruleId: string): Promise<any> {
  return requestJson<any>(`/api/v1/rules/${encodeURIComponent(ruleId)}/history`);
}

export async function ingestText(source: string, text: string): Promise<any> {
  return requestJson<any>('/api/v1/ingestion/ingest', {
    method: 'POST',
    body: JSON.stringify({ source, text })
  });
}

export async function listRuns(limit?: number): Promise<{ count: number; runs: any[] }> {
  const query = typeof limit === 'number' ? `?limit=${encodeURIComponent(String(limit))}` : '';
  return requestJson<{ count: number; runs: any[] }>(`/api/v1/testing/runs${query}`);
}

export async function getRun(runId: string): Promise<any> {
  return requestJson<any>(`/api/v1/testing/runs/${encodeURIComponent(runId)}`);
}