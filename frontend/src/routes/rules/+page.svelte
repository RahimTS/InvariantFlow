<script lang="ts">
  import { onMount } from 'svelte';
  import RuleCard from '$lib/components/RuleCard.svelte';
  import { approveRule, getPendingRules, rejectRule } from '$lib/api';
  import { ruleStore } from '$lib/stores/rules';

  let loading = false;
  let error = '';

  async function refresh() {
    loading = true;
    error = '';
    try {
      const payload = await getPendingRules();
      ruleStore.setRules(payload.rules);
    } catch (err) {
      error = err instanceof Error ? err.message : 'Failed to load rules';
    } finally {
      loading = false;
    }
  }

  async function approve(ruleId: string) {
    await approveRule(ruleId, 'dashboard');
    await refresh();
  }

  async function reject(ruleId: string) {
    await rejectRule(ruleId, 'rejected from dashboard');
    await refresh();
  }

  onMount(refresh);
</script>

<section class="mb-4 card p-4">
  <h2 class="text-lg font-bold">Rule Management</h2>
  <p class="text-sm text-slate-700">Review proposed rules and move them through the human approval gate.</p>
</section>

{#if error}
  <p class="mb-4 rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-800">{error}</p>
{/if}

{#if loading}
  <p class="text-sm text-slate-600">Loading rules...</p>
{:else}
  <div class="space-y-3">
    {#if $ruleStore.length === 0}
      <p class="text-sm text-slate-600">No pending rules.</p>
    {/if}

    {#each $ruleStore as rule}
      <div class="space-y-2">
        <RuleCard {rule} />
        <div class="flex flex-wrap gap-2">
          <button class="badge ok" on:click={() => approve(String(rule.rule_id || ''))}>Approve</button>
          <button class="badge bad" on:click={() => reject(String(rule.rule_id || ''))}>Reject</button>
          <a class="badge" href={`/rules/${String(rule.rule_id || '')}`}>History</a>
        </div>
      </div>
    {/each}
  </div>
{/if}
