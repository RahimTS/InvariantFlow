from __future__ import annotations

import inspect
import logging
from typing import Any

from app.config import settings
from app.memory.blackboard import Blackboard
from app.memory.exec_log import ExecutionLog
from app.memory.postgres_exec_log import PostgresExecutionLog
from app.memory.postgres_rule_store import PostgresRuleStore
from app.memory.redis_blackboard import RedisBlackboard
from app.memory.redis_events import RedisEventEmitter
from app.memory.redis_state_store import RedisStateStore
from app.memory.rule_store import RuleStore
from app.memory.state_store import InMemoryStateStore, StateStore
from app.runtime import agent_registry, run_registry

logger = logging.getLogger(__name__)


async def init_app_storage(app: Any) -> None:
    if getattr(app.state, "_storage_initialized", False):
        return

    app.state.storage_backend = settings.storage_backend
    app.state.redis_event_emitter = None
    app.state.rule_store = None
    app.state.execution_log = None
    app.state.state_store = None

    agent_registry.set_event_emitter(lambda event: emit_app_event(app, event))

    if settings.storage_backend != "docker":
        app.state._storage_initialized = True
        return

    rule_store = PostgresRuleStore(settings.postgres_dsn)
    execution_log = PostgresExecutionLog(settings.postgres_dsn)
    state_store = RedisStateStore(
        settings.redis_url,
        ttl_seconds=settings.redis_state_ttl_seconds,
    )
    redis_emitter = RedisEventEmitter(
        settings.redis_url,
        channel=settings.redis_events_channel,
    )

    await rule_store.init()
    await execution_log.init()
    await state_store.init()
    await redis_emitter.init()

    app.state.rule_store = rule_store
    app.state.execution_log = execution_log
    app.state.state_store = state_store
    app.state.redis_event_emitter = redis_emitter
    app.state._storage_initialized = True


async def shutdown_app_storage(app: Any) -> None:
    agent_registry.set_event_emitter(None)
    for attr in ("redis_event_emitter", "state_store", "execution_log", "rule_store"):
        obj = getattr(app.state, attr, None)
        if obj is None:
            continue
        closer = getattr(obj, "close", None)
        if not callable(closer):
            continue
        try:
            result = closer()
            if inspect.isawaitable(result):
                await result
        except Exception:
            logger.exception("failed closing %s", attr)
    app.state._storage_initialized = False


async def emit_app_event(app: Any, event: dict[str, Any]) -> None:
    await run_registry.publish(event)
    redis_emitter = getattr(app.state, "redis_event_emitter", None)
    if redis_emitter is None:
        return
    await redis_emitter.emit(event)


async def get_rule_store(app: Any, db_path_override: str | None = None) -> Any:
    if settings.storage_backend == "docker":
        if getattr(app.state, "rule_store", None) is None:
            await init_app_storage(app)
        return app.state.rule_store
    store = RuleStore(db_path=db_path_override or settings.sqlite_db_path)
    await store.init()
    return store


def get_state_store(app: Any) -> StateStore:
    if settings.storage_backend == "docker":
        if getattr(app.state, "state_store", None) is None:
            raise RuntimeError("state_store is not initialized; app startup did not run")
        return app.state.state_store
    return InMemoryStateStore()


def get_execution_log(app: Any, artifacts_dir: str | None = None) -> Any:
    if settings.storage_backend == "docker":
        if getattr(app.state, "execution_log", None) is None:
            raise RuntimeError("execution_log is not initialized; app startup did not run")
        return app.state.execution_log
    return ExecutionLog(artifacts_dir=artifacts_dir or "artifacts")


async def create_blackboard(app: Any, run_id: str) -> Any:
    async def _emit(event: dict[str, Any]) -> None:
        await emit_app_event(app, event)

    if settings.storage_backend == "docker":
        blackboard = RedisBlackboard(
            redis_url=settings.redis_url,
            stream_key=f"blackboard:{run_id}:tasks",
            group_name=f"swarm_workers:{run_id}",
            task_prefix=f"task:{run_id}",
            max_retries=settings.blackboard_max_retries,
            event_emitter=_emit,
        )
        await blackboard.init()
        return blackboard

    blackboard = Blackboard(
        timeout_seconds=settings.blackboard_task_timeout_seconds,
        max_retries=settings.blackboard_max_retries,
        event_emitter=_emit,
    )
    blackboard.start_watcher()
    return blackboard


async def close_blackboard(blackboard: Any) -> None:
    stop_watcher = getattr(blackboard, "stop_watcher", None)
    if callable(stop_watcher):
        result = stop_watcher()
        if inspect.isawaitable(result):
            await result

    closer = getattr(blackboard, "close", None)
    if callable(closer):
        result = closer()
        if inspect.isawaitable(result):
            await result
