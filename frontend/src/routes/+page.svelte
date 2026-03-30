<script lang="ts">
  import { onMount } from 'svelte';
  import ExecutionStream from '$lib/components/ExecutionStream.svelte';
  import SystemStatus from '$lib/components/SystemStatus.svelte';
  import TaskBoard from '$lib/components/TaskBoard.svelte';
  import VerdictPanel from '$lib/components/VerdictPanel.svelte';
  import { getAgentStatus, getDeadTasks, runTesting } from '$lib/api';
  import { agentStore } from '$lib/stores/agents';
  import { costStore } from '$lib/stores/cost';
  import { executionStore } from '$lib/stores/execution';
  import { taskStore } from '$lib/stores/tasks';
  import { verdictStore } from '$lib/stores/verdicts';

  let isRunning = false;
  let latestRunId = '';
  let deadTaskCount = 0;
  let error = '';

  async function refreshStatus() {
    try {
      const [agentsRes, deadRes] = await Promise.all([getAgentStatus(), getDeadTasks()]);
      const snapshot: Record<string, { agent_id: string; old_state: string | null; new_state: string }> = {};
      for (const agent of agentsRes.agents) {
        const id = String(agent.agent_id || '');
        if (!id) continue;
        snapshot[id] = {
          agent_id: id,
          old_state: null,
          new_state: String(agent.state || 'UNKNOWN')
        };
      }
      agentStore.setSnapshot(snapshot);
      deadTaskCount = Number(deadRes.count || 0);
    } catch (err) {
      console.warn('status refresh failed', err);
    }
  }

  async function startRun(mode: 'direct' | 'blackboard' | 'langgraph') {
    isRunning = true;
    error = '';
    try {
      const result = await runTesting({
        mode,
        seed_starter: true,
        entity: 'Shipment'
      });
      latestRunId = String(result.run_id || '');
      await refreshStatus();
    } catch (err) {
      error = err instanceof Error ? err.message : 'Unknown error';
    } finally {
      isRunning = false;
    }
  }

  onMount(async () => {
    await refreshStatus();
  });
</script>

<section class="mb-4 card p-4">
  <div class="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
    <div>
      <h2 class="text-lg font-bold">Run Testing Swarm</h2>
      <p class="text-sm text-slate-700">Kick off a seeded run and watch task flow, execution steps, verdicts, and costs stream live.</p>
    </div>
    <div class="flex flex-wrap gap-2">
      <button class="badge" disabled={isRunning} on:click={() => startRun('direct')}>Run Direct</button>
      <button class="badge" disabled={isRunning} on:click={() => startRun('blackboard')}>Run Blackboard</button>
      <button class="badge" disabled={isRunning} on:click={() => startRun('langgraph')}>Run LangGraph</button>
    </div>
  </div>
  {#if latestRunId}
    <p class="mono mt-2 text-xs text-slate-600">latest run: {latestRunId}</p>
  {/if}
  {#if error}
    <p class="mono mt-2 text-xs text-red-700">{error}</p>
  {/if}
</section>

<div class="grid-panels">
  <TaskBoard tasks={$taskStore} />
  <ExecutionStream steps={$executionStore} />
  <VerdictPanel verdicts={$verdictStore} />
  <SystemStatus agents={$agentStore} cost={$costStore} {deadTaskCount} activeRunId={latestRunId} />
</div>
