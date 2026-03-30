<script lang="ts">
  import { onMount } from 'svelte';
  import { listRuns } from '$lib/api';

  let runs: Record<string, unknown>[] = [];
  let loading = false;
  let error = '';

  async function refresh() {
    loading = true;
    error = '';
    try {
      const payload = await listRuns();
      runs = payload.runs;
    } catch (err) {
      error = err instanceof Error ? err.message : 'Failed to load runs';
    } finally {
      loading = false;
    }
  }

  onMount(refresh);
</script>

<section class="mb-4 card p-4">
  <h2 class="text-lg font-bold">Run History</h2>
  <p class="text-sm text-slate-700">Completed and in-flight runs from the backend run registry.</p>
</section>

{#if error}
  <p class="rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-800">{error}</p>
{:else if loading}
  <p class="text-sm text-slate-600">Loading...</p>
{:else}
  <div class="space-y-3">
    {#if runs.length === 0}
      <p class="text-sm text-slate-600">No runs available.</p>
    {/if}

    {#each runs as run}
      <article class="card p-4">
        <div class="mb-2 flex flex-wrap items-center justify-between gap-2">
          <strong class="mono text-xs">{String(run.run_id || '')}</strong>
          <span class="badge">{String(run.status || '')}</span>
        </div>
        <a class="badge" href={`/runs/${String(run.run_id || '')}`}>Open</a>
      </article>
    {/each}
  </div>
{/if}
