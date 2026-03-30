from __future__ import annotations

from dataclasses import dataclass
import inspect
import logging
from typing import Any

from app.llm.models import LLMUsage
from app.runtime.events import make_event

logger = logging.getLogger(__name__)


class CostLimitExceeded(RuntimeError):
    pass


@dataclass(frozen=True)
class ModelPricing:
    input_per_1k: float
    output_per_1k: float


# Approximate defaults for budgeting purposes in V1.
MODEL_PRICING_USD_PER_1K: dict[str, ModelPricing] = {
    "deepseek/deepseek-chat": ModelPricing(input_per_1k=0.0003, output_per_1k=0.0005),
    "google/gemini-2.5-flash": ModelPricing(input_per_1k=0.0003, output_per_1k=0.0006),
    "anthropic/claude-sonnet-4": ModelPricing(input_per_1k=0.0030, output_per_1k=0.0150),
}

DEFAULT_PRICING = ModelPricing(input_per_1k=0.0010, output_per_1k=0.0020)


class CostTracker:
    def __init__(
        self,
        max_per_rule_usd: float,
        max_per_run_usd: float,
        event_emitter: Any | None = None,
        run_id: str | None = None,
    ) -> None:
        self._max_per_rule = max_per_rule_usd
        self._max_per_run = max_per_run_usd
        self._run_total_usd = 0.0
        self._rule_totals_usd: dict[str, float] = {}
        self._event_emitter = event_emitter
        self._run_id = run_id

    def ensure_can_call(self, rule_id: str) -> None:
        if self._run_total_usd >= self._max_per_run:
            raise CostLimitExceeded(
                f"run cost limit exceeded: {self._run_total_usd:.6f} >= {self._max_per_run:.6f}"
            )
        if self._rule_totals_usd.get(rule_id, 0.0) >= self._max_per_rule:
            raise CostLimitExceeded(
                f"rule cost limit exceeded for {rule_id}: "
                f"{self._rule_totals_usd.get(rule_id, 0.0):.6f} >= {self._max_per_rule:.6f}"
            )

    def add_usage(self, *, rule_id: str, model: str, usage: LLMUsage) -> float:
        pricing = MODEL_PRICING_USD_PER_1K.get(model, DEFAULT_PRICING)
        estimated = (
            (usage.prompt_tokens / 1000.0) * pricing.input_per_1k
            + (usage.completion_tokens / 1000.0) * pricing.output_per_1k
        )
        self._run_total_usd += estimated
        self._rule_totals_usd[rule_id] = self._rule_totals_usd.get(rule_id, 0.0) + estimated
        self._emit_cost_update(rule_id=rule_id, model=model, estimated=estimated)
        self.ensure_can_call(rule_id)
        return estimated

    def is_exceeded(self, rule_id: str | None = None) -> bool:
        if self._run_total_usd >= self._max_per_run:
            return True
        if rule_id is None:
            return False
        return self._rule_totals_usd.get(rule_id, 0.0) >= self._max_per_rule

    def snapshot(self) -> dict:
        return {
            "run_total_usd": round(self._run_total_usd, 6),
            "max_per_run_usd": self._max_per_run,
            "max_per_rule_usd": self._max_per_rule,
            "rule_totals_usd": {k: round(v, 6) for k, v in self._rule_totals_usd.items()},
        }

    def bind_run(self, run_id: str) -> None:
        self._run_id = run_id

    def _emit_cost_update(self, *, rule_id: str, model: str, estimated: float) -> None:
        if self._event_emitter is None:
            return
        event = make_event(
            "COST_UPDATE",
            {
                "rule_id": rule_id,
                "model": model,
                "estimated_call_usd": round(estimated, 8),
                "snapshot": self.snapshot(),
            },
            run_id=self._run_id,
        )
        try:
            result = self._event_emitter(event)
            if inspect.isawaitable(result):
                # Cost accounting runs inside async request contexts.
                import asyncio

                asyncio.get_running_loop().create_task(result)
        except Exception:
            logger.exception("cost update event emission failed")
