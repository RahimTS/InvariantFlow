<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { getRule, getRuleHistory } from '$lib/api';

  let rule: Record<string, unknown> | null = null;
  let versions: Record<string, unknown>[] = [];
  let error = '';

  $: ruleId = $page.params.id;

  async function load() {
    if (!ruleId) return;
    error = '';
    try {
      const [rulePayload, historyPayload] = await Promise.all([getRule(ruleId), getRuleHistory(ruleId)]);
      rule = rulePayload.rule;
      versions = historyPayload.versions;
    } catch (err) {
      error = err instanceof Error ? err.message : 'Failed to load rule';
    }
  }

  onMount(load);
</script>

<section class="mb-4 card p-4">
  <h2 class="text-lg font-bold">Rule Detail</h2>
  <p class="mono text-xs text-slate-600">{ruleId}</p>
</section>

{#if error}
  <p class="rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-800">{error}</p>
{:else}
  {#if rule}
    <section class="mb-4 card p-4">
      <h3 class="mb-2 font-bold">Current Version</h3>
      <pre class="max-h-80 overflow-auto rounded-lg bg-black/90 p-3 text-xs text-emerald-200">{JSON.stringify(rule, null, 2)}</pre>
    </section>
  {/if}

  <section class="card p-4">
    <h3 class="mb-2 font-bold">History</h3>
    {#if versions.length === 0}
      <p class="text-sm text-slate-600">No versions found.</p>
    {:else}
      <div class="space-y-3">
        {#each versions as version}
          <article class="rounded-xl border border-black/10 bg-white/70 p-3">
            <div class="mb-2 flex items-center justify-between">
              <strong>v{String(version.version || '?')}</strong>
              <span class="badge">{String(version.status || '')}</span>
            </div>
            <div class="text-sm">{String(version.description || '')}</div>
          </article>
        {/each}
      </div>
    {/if}
  </section>
{/if}
