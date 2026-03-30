<script lang="ts">
  export let rule: Record<string, unknown>;
</script>

<article class="card p-4">
  <div class="mb-2 flex items-start justify-between gap-3">
    <div>
      <h3 class="font-bold">{String(rule.rule_id || 'unknown')}</h3>
      <p class="text-sm text-slate-700">{String(rule.description || '')}</p>
    </div>
    <span class="badge">{String(rule.status || 'proposed')}</span>
  </div>
  <p class="mono text-xs text-slate-600">version {String(rule.version || '?')}</p>
</article>
