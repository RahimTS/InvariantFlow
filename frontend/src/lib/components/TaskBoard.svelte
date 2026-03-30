<script lang="ts">
  interface Task {
    task_id: string;
    type: string;
    status: string;
    agent_id?: string;
    rule_id?: string;
    error?: string;
    [key: string]: any;
  }

  export let tasks: Task[] = [];

  const statusClasses: Record<string, string> = {
    posted: 'bg-slate-100 text-slate-700 border border-slate-200',
    claimed: 'bg-blue-100 text-blue-700 border border-blue-200',
    in_progress: 'bg-amber-100 text-amber-700 border border-amber-200',
    completed: 'bg-emerald-100 text-emerald-700 border border-emerald-200',
    dead: 'bg-red-100 text-red-700 border border-red-200'
  };

  function truncateId(value: string): string {
    if (value.length <= 18) {
      return value;
    }

    return `${value.slice(0, 8)}...${value.slice(-6)}`;
  }

  function badgeClass(status: string): string {
    return statusClasses[status] ?? statusClasses.posted;
  }
</script>

<section class="card p-4">
  <div class="mb-3 flex items-center justify-between">
    <h2 class="text-lg font-bold">Task board</h2>
    <span class="mono text-xs text-slate-600">{tasks.length}</span>
  </div>

  <div class="max-h-80 space-y-2 overflow-y-auto pr-1">
    {#if tasks.length === 0}
      <p class="text-sm text-slate-700">No tasks yet</p>
    {/if}

    {#each tasks as task (task.task_id)}
      <article class="rounded-xl border border-slate-200 bg-white/75 p-3">
        <div class="mb-1 flex items-center justify-between gap-2">
          <strong class="mono text-xs text-slate-700">{truncateId(String(task.task_id ?? ''))}</strong>
          <span class={`rounded-full px-2 py-0.5 text-xs font-medium ${badgeClass(String(task.status ?? 'posted'))}`}>
            {String(task.status ?? 'posted')}
          </span>
        </div>

        <div class="text-sm font-medium text-slate-800">{String(task.type ?? 'unknown')}</div>

        {#if task.agent_id}
          <div class="mono mt-1 text-xs text-slate-600">agent: {task.agent_id}</div>
        {/if}

        {#if task.error}
          <div class="mono mt-1 text-xs text-red-700">{task.error}</div>
        {/if}
      </article>
    {/each}
  </div>
</section>