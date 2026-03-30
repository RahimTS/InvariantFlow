<script lang="ts">
  interface Verdict {
    rule_id: string;
    scenario_id: string;
    result: 'pass' | 'fail' | 'inconclusive';
    violated_conditions: string[];
    evaluation_method: string;
    [key: string]: any;
  }

  interface CriticFinding {
    type: string;
    target: string;
    detail: string;
    action?: string;
    rule_id?: string;
    [key: string]: any;
  }

  type VerdictList = Verdict[] & { findings?: CriticFinding[] };

  export let verdicts: VerdictList = [];

  $: findings = verdicts.findings ?? [];

  function resultLabel(result: Verdict['result']): string {
    if (result === 'pass') return 'PASS';
    if (result === 'fail') return 'FAIL';
    return 'INCONCLUSIVE';
  }

  function resultClass(result: Verdict['result']): string {
    if (result === 'pass') {
      return 'bg-emerald-100 text-emerald-700 border border-emerald-200';
    }

    if (result === 'fail') {
      return 'bg-red-100 text-red-700 border border-red-200';
    }

    return 'bg-amber-100 text-amber-700 border border-amber-200';
  }
</script>

<section class="card p-4">
  <div class="mb-3 flex items-center justify-between">
    <h2 class="text-lg font-bold">Verdicts</h2>
    <span class="mono text-xs text-slate-600">{verdicts.length}</span>
  </div>

  <div class="max-h-80 space-y-2 overflow-y-auto pr-1">
    {#if verdicts.length === 0}
      <p class="text-sm text-slate-700">No verdicts yet</p>
    {/if}

    {#each verdicts as verdict, idx (`${verdict.rule_id}-${verdict.scenario_id}-${idx}`)}
      <article class="rounded-xl border border-slate-200 bg-white/75 p-3">
        <div class="mb-1 flex items-center justify-between gap-2">
          <div class="text-sm font-medium text-slate-800">{verdict.rule_id}</div>
          <span class={`rounded-full px-2 py-0.5 text-xs font-medium ${resultClass(verdict.result)}`}>
            {resultLabel(verdict.result)}
          </span>
        </div>

        <div class="mono text-xs text-slate-600">scenario: {verdict.scenario_id}</div>
        <div class="mono mt-1 text-xs text-slate-600">method: {verdict.evaluation_method}</div>

        {#if verdict.violated_conditions.length > 0}
          <div class="mt-1 text-xs text-slate-700">
            violated: {verdict.violated_conditions.join(', ')}
          </div>
        {/if}
      </article>
    {/each}

    {#if findings.length > 0}
      <div class="pt-2">
        <h3 class="mb-2 text-sm font-bold text-slate-800">Critic findings</h3>
        <div class="space-y-2">
          {#each findings as finding, idx (`${finding.type}-${finding.target}-${idx}`)}
            <article class="rounded-xl border border-amber-200 bg-amber-50 p-3">
              <div class="mb-1 text-sm font-medium text-amber-900">{finding.type} -> {finding.target}</div>
              <div class="text-xs text-amber-800">{finding.detail}</div>
            </article>
          {/each}
        </div>
      </div>
    {/if}
  </div>
</section>