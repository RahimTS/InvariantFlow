<script lang="ts">
  import '../app.css';
  import { onMount } from 'svelte';
  import { connectSSE } from '$lib/sse';

  let sse: EventSource | null = null;

  onMount(() => {
    sse = connectSSE();
    return () => {
      sse?.close();
    };
  });
</script>

<div class="mx-auto min-h-screen w-full max-w-[1280px] px-4 pb-8 pt-5 md:px-6">
  <header class="mb-5 card p-4">
    <div class="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
      <div>
        <h1 class="text-2xl font-bold">InvariantFlow Dashboard</h1>
        <p class="text-sm text-slate-700">Live rule-testing swarm with SSE event stream.</p>
      </div>
      <nav class="flex flex-wrap gap-2 text-sm">
        <a class="badge" href="/">Dashboard</a>
        <a class="badge" href="/rules">Rules</a>
        <a class="badge" href="/ingest">Ingest</a>
        <a class="badge" href="/runs">Runs</a>
      </nav>
    </div>
  </header>

  <slot />
</div>
