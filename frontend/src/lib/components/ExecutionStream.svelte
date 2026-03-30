<script lang="ts">
  interface ExecutionStep {
    step_number: number;
    endpoint: string;
    status_code: number;
    latency_ms: number;
    rule_id?: string;
    scenario_id?: string;
    timestamp?: string;
  }

  export let steps: ExecutionStep[] = [];

  $: displaySteps = [...steps].reverse();

  function statusClass(code: number): string {
    if (code >= 200 && code < 300) {
      return 'bg-emerald-100 text-emerald-700 border border-emerald-200';
    }

    if (code >= 400) {
      return 'bg-red-100 text-red-700 border border-red-200';
    }

    return 'bg-slate-100 text-slate-700 border border-slate-200';
  }
</script>

<section class="card p-4">
  <div class="mb-3 flex items-center justify-between">
    <h2 class="text-lg font-bold">Execution stream</h2>
    <span class="mono text-xs text-slate-600">{steps.length}</span>
  </div>

  <div class="max-h-80 space-y-2 overflow-y-auto pr-1">
    {#if displaySteps.length === 0}
      <p class="text-sm text-slate-700">Waiting for execution...</p>
    {/if}

    {#each displaySteps as step, idx (`${step.step_number}-${idx}-${step.endpoint}`)}
      <article class="rounded-xl border border-slate-200 bg-white/75 p-3">
        <div class="mb-1 flex items-center justify-between gap-2">
          <strong class="mono text-xs text-slate-700">step {step.step_number}</strong>
          <span class={`rounded-full px-2 py-0.5 text-xs font-medium ${statusClass(step.status_code)}`}>
            {step.status_code}
          </span>
        </div>

        <div class="mono break-all text-xs text-slate-800">{step.endpoint}</div>
        <div class="mono mt-1 text-xs text-slate-600">{Number(step.latency_ms || 0).toFixed(1)} ms</div>
      </article>
    {/each}
  </div>
</section>