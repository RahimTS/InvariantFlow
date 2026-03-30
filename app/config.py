from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_timeout_seconds: float = 30.0
    openrouter_max_retries: int = 2

    # Where the mock API lives (used by Executor in production)
    mock_api_base_url: str = "http://localhost:8000"

    # LLM model routing (ARCHITECTURE.md assignments)
    extractor_model: str = "deepseek/deepseek-chat"
    normalizer_model: str = "google/gemini-2.5-flash"
    scenario_generator_model: str = "google/gemini-2.5-flash"
    flow_planner_model: str = "google/gemini-2.5-flash"
    oracle_fallback_model: str = "google/gemini-2.5-flash"
    critic_model: str = "anthropic/claude-sonnet-4"

    # Appendix B defaults
    max_feedback_iterations: int = 3
    max_scenarios_per_rule: int = 20
    max_cost_per_rule_usd: float = 0.10
    max_cost_per_run_usd: float = 0.50
    blackboard_task_timeout_seconds: int = 60
    blackboard_max_retries: int = 3
    oracle_llm_confidence_threshold: float = 0.7
    rule_confidence_review_threshold: float = 0.5
    heartbeat_interval_seconds: int = 30
    heartbeat_missed_limit: int = 3

    sqlite_db_path: str = "invariantflow.db"

    # V2 storage/profile selection
    storage_backend: Literal["local", "docker"] = "local"
    postgres_dsn: str = "postgresql://invariantflow:invariantflow@localhost:5432/invariantflow"
    redis_url: str = "redis://localhost:6379/0"
    redis_state_ttl_seconds: int = 3600
    redis_events_channel: str = "events:testing"
    frontend_url: str = "http://localhost:5173"


settings = Settings()
