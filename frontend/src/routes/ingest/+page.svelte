<script lang="ts">
  import { ingestText } from '$lib/api';

  let source = 'ticket-demo';
  let text = 'Shipment weight must not exceed vehicle capacity.';
  let loading = false;
  let result: Record<string, unknown> | null = null;
  let error = '';

  async function submit() {
    loading = true;
    error = '';
    result = null;
    try {
      result = await ingestText(source, text);
    } catch (err) {
      error = err instanceof Error ? err.message : 'Ingestion failed';
    } finally {
      loading = false;
    }
  }
</script>

<section class="mb-4 card p-4">
  <h2 class="text-lg font-bold">Ingest Rules</h2>
  <p class="text-sm text-slate-700">Paste raw spec text and push it through extractor -> normalizer -> validator.</p>
</section>

<section class="card space-y-3 p-4">
  <label class="block">
    <span class="mb-1 block text-sm">Source</span>
    <input class="w-full rounded-lg border border-black/20 bg-white p-2" bind:value={source} />
  </label>

  <label class="block">
    <span class="mb-1 block text-sm">Text</span>
    <textarea class="min-h-40 w-full rounded-lg border border-black/20 bg-white p-2" bind:value={text}></textarea>
  </label>

  <button class="badge" disabled={loading} on:click={submit}>Ingest</button>

  {#if error}
    <p class="rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-800">{error}</p>
  {/if}

  {#if result}
    <pre class="max-h-96 overflow-auto rounded-lg bg-black/90 p-3 text-xs text-emerald-200">{JSON.stringify(result, null, 2)}</pre>
  {/if}
</section>
