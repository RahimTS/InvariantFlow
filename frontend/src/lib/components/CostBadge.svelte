<script lang="ts">
  import type { CostSnapshot } from '$lib/types';

  export let cost: CostSnapshot | null = null;
</script>

{#if cost}
  <div class="flex flex-wrap gap-2">
    <span class="badge mono">run ${cost.run_total_usd.toFixed(6)}</span>
    <span class="badge mono">max run ${cost.max_per_run_usd.toFixed(2)}</span>
    <span class="badge mono">max rule ${cost.max_per_rule_usd.toFixed(2)}</span>
  </div>
{:else}
  <span class="text-sm text-slate-600">No cost data yet.</span>
{/if}
