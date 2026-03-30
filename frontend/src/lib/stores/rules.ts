import { writable } from 'svelte/store';

const { subscribe, set } = writable<Record<string, unknown>[]>([]);

export const ruleStore = {
  subscribe,
  setRules: (rules: Record<string, unknown>[]) => set(rules),
  clear: () => set([])
};
