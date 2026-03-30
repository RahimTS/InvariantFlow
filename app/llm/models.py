from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class LLMUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float | None = None


class LLMResponse(BaseModel):
    model: str
    content: str
    raw: dict = Field(default_factory=dict)
    usage: LLMUsage = Field(default_factory=LLMUsage)


class AgentModelRoute(BaseModel):
    extractor: str = "deepseek/deepseek-chat"
    normalizer: str = "google/gemini-2.5-flash"
    scenario_generator: str = "google/gemini-2.5-flash"
    flow_planner: str = "google/gemini-2.5-flash"
    oracle_fallback: str = "google/gemini-2.5-flash"
    critic: str = "anthropic/claude-sonnet-4"


MODEL_ROUTES = AgentModelRoute()

