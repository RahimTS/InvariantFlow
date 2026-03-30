<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { getRun } from '$lib/api';

  let run: Record<string, unknown> | null = null;
  let error = '';

  $: runId = $page.params.id;

  async function load() {
    if (!runId) return;
    error = '';
    try {
      run = await getRun(runId);
    } catch (err) {
      error = err instanceof Error ? err.message : 'Failed to load run';
    }
  }

  onMount(load);
</script>

<section class="mb-4 card p-4">
  <h2 class="text-lg font-bold">Run Detail</h2>
  <p class="mono text-xs text-slate-600">{runId}</p>
</section>

{#if error}
  <p class="rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-800">{error}</p>
{:else if run}
  <pre class="card max-h-[70vh] overflow-auto p-4 text-xs">{JSON.stringify(run, null, 2)}</pre>
{:else}
  <p class="text-sm text-slate-600">Loading...</p>
{/if}
