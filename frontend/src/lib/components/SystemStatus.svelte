<script lang="ts">
  interface AgentState {
    agent_id: string;
    old_state: string | null;
    new_state: string;
  }

  interface CostSnapshot {
    run_total_usd: number;
    max_per_run_usd: number;
    max_per_rule_usd: number;
    rule_totals_usd: Record<string, number>;
  }

  export let agents: Record<string, AgentState> = {};
  export let cost: CostSnapshot = {
    run_total_usd: 0,
    max_per_run_usd: 0.5,
    max_per_rule_usd: 0.1,
    rule_totals_usd: {}
  };
  export let deadTaskCount = 0;
  export let activeRunId = '';

  const stateDotClasses: Record<string, string> = {
    IDLE: 'bg-slate-400',
    ACTIVE: 'bg-emerald-500',
    DRAINING: 'bg-amber-500',
    TERMINATED: 'bg-red-500',
    REGISTERED: 'bg-blue-500'
  };

  $: agentList = Object.values(agents);
  $: ruleCostEntries = Object.entries(cost?.rule_totals_usd ?? {});

  function dotClass(state: string): string {
    return stateDotClasses[state] ?? 'bg-slate-300';
  }
</script>

<section class="card p-4">
  <h2 class="mb-3 text-lg font-bold">System status</h2>

  <div class="mb-4">
    <h3 class="mb-2 text-sm font-bold text-slate-800">Agents</h3>
    {#if agentList.length === 0}
      <p class="text-sm text-slate-700">No agent state yet</p>
    {:else}
      <div class="space-y-2">
        {#each agentList as agent (agent.agent_id)}
          <div class="flex items-center gap-2 rounded-lg border border-slate-200 bg-white/70 px-3 py-2">
            <span class={`h-2.5 w-2.5 rounded-full ${dotClass(agent.new_state)}`}></span>
            <span class="mono text-xs text-slate-700">{agent.agent_id}</span>
            <span class="text-xs text-slate-700">{agent.new_state}</span>
          </div>
        {/each}
      </div>
    {/if}
  </div>

  <div class="mb-4">
    <h3 class="mb-2 text-sm font-bold text-slate-800">Cost</h3>
    <p class="mono text-xs text-slate-700">
      ${Number(cost?.run_total_usd ?? 0).toFixed(4)} / ${Number(cost?.max_per_run_usd ?? 0).toFixed(4)}
    </p>

    {#if ruleCostEntries.length > 0}
      <div class="mt-2 space-y-1">
        {#each ruleCostEntries as [ruleId, value]}
          <div class="mono text-xs text-slate-600">{ruleId}: ${Number(value).toFixed(4)}</div>
        {/each}
      </div>
    {/if}
  </div>

  <div class="mb-2 flex items-center justify-between gap-3">
    <span class="text-sm font-bold text-slate-800">Dead tasks</span>
    <span class={deadTaskCount > 0 ? 'mono text-sm font-bold text-red-700' : 'mono text-sm text-slate-700'}>{deadTaskCount}</span>
  </div>

  {#if activeRunId}
    <div class="pt-1">
      <span class="text-sm font-bold text-slate-800">Active run:</span>
      <span class="mono ml-2 text-xs text-slate-600">{activeRunId}</span>
    </div>
  {/if}
</section>