<script lang="ts">
  import type { AgentStateItem } from '$lib/types';

  export let agent: AgentStateItem;

  const colorFor = (state: string) => {
    if (state === 'ACTIVE') return 'ok';
    if (state === 'DRAINING') return 'warn';
    if (state === 'TERMINATED') return 'bad';
    return '';
  };
</script>

<span class={`badge ${colorFor(agent.new_state)}`}>
  <span class="mono">{agent.agent_id}</span>
  <span>{agent.new_state}</span>
</span>
