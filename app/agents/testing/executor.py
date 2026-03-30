"""
Deterministic flow executor for Phase 1.

Executes a FlowPlan step-by-step, records ExecutionRecord entries,
and updates the in-memory StateStore with extracted values.
"""

from __future__ import annotations

from datetime import datetime, timezone
from time import perf_counter
from uuid import uuid4
from typing import Any

import httpx
from fastapi import FastAPI

from app.config import settings
from app.memory.state_store import InMemoryStateStore, StateStore
from app.schemas.execution import ExecutionRecord, ExecutionTrace
from app.schemas.scenarios import FlowPlan, FlowStep, Scenario


class Executor:
    def __init__(
        self,
        state_store: StateStore | None = None,
        base_url: str | None = None,
        app: FastAPI | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._state_store = state_store or InMemoryStateStore()
        self._base_url = base_url or settings.mock_api_base_url
        self._app = app
        self._timeout_seconds = timeout_seconds

    async def execute(
        self,
        rule_id: str,
        scenario: Scenario,
        flow_plan: FlowPlan,
        run_id: str | None = None,
    ) -> ExecutionTrace:
        active_run_id = run_id or f"run_{uuid4().hex}"
        trace_id = f"trace_{uuid4().hex}"
        state_values: dict[str, Any] = {}
        records: list[ExecutionRecord] = []
        overall_status = "completed"

        async with self._client() as client:
            for step in flow_plan.steps:
                record, response_body, status_mismatch = await self._execute_step(
                    client=client,
                    run_id=active_run_id,
                    scenario=scenario,
                    step=step,
                    state_values=state_values,
                )
                records.append(record)
                if response_body is not None:
                    extracted = _extract_values(step.extract, response_body)
                    state_values.update(extracted)
                    await self._sync_entities(
                        run_id=active_run_id,
                        scenario=scenario,
                        response_body=response_body,
                        state_values=state_values,
                    )

                if record.status_code == 0:
                    overall_status = "timeout"
                    break

                if status_mismatch or record.status_code >= 500:
                    overall_status = "error"
                    break

        final_state = await self._state_store.snapshot(active_run_id)
        return ExecutionTrace(
            trace_id=trace_id,
            rule_id=rule_id,
            scenario_id=scenario.scenario_id,
            flow_id=flow_plan.flow_id,
            records=records,
            final_state=final_state,
            overall_status=overall_status,  # type: ignore[arg-type]
        )

    async def _execute_step(
        self,
        client: httpx.AsyncClient,
        run_id: str,
        scenario: Scenario,
        step: FlowStep,
        state_values: dict[str, Any],
    ) -> tuple[ExecutionRecord, dict | None, bool]:
        path_params = _resolve_map(step.path_params, scenario.inputs, state_values)
        endpoint = _render_endpoint(step.endpoint, path_params)
        payload = _resolve_map(step.payload_map, scenario.inputs, state_values)

        started = perf_counter()
        try:
            response = await client.request(
                method=step.method.upper(),
                url=endpoint,
                json=payload or None,
                timeout=self._timeout_seconds,
            )
            latency_ms = (perf_counter() - started) * 1000
            response_body = _parse_response_body(response)
            status_code = response.status_code
        except httpx.TimeoutException:
            latency_ms = (perf_counter() - started) * 1000
            response_body = {"error": "timeout"}
            status_code = 0
        except httpx.HTTPError as exc:
            latency_ms = (perf_counter() - started) * 1000
            response_body = {"error": str(exc)}
            status_code = 0

        record = ExecutionRecord(
            step_number=step.step_number,
            endpoint=endpoint,
            request_payload=payload,
            response_body=response_body,
            status_code=status_code,
            latency_ms=latency_ms,
            timestamp=datetime.now(timezone.utc),
        )
        status_mismatch = (
            status_code != 0 and bool(step.expected_status) and status_code not in step.expected_status
        )
        return record, response_body if isinstance(response_body, dict) else None, status_mismatch

    async def _sync_entities(
        self,
        run_id: str,
        scenario: Scenario,
        response_body: dict,
        state_values: dict[str, Any],
    ) -> None:
        shipment_id = (
            response_body.get("shipment_id")
            or state_values.get("shipment_id")
            or state_values.get("id")
        )
        vehicle_id = (
            response_body.get("vehicle_id")
            or state_values.get("vehicle_id")
            or scenario.inputs.get("vehicle_id")
        )

        if shipment_id:
            existing = await self._state_store.get_entity(run_id, str(shipment_id)) or {}
            status = response_body.get("status", existing.get("status"))
            history = list(existing.get("status_history", []))
            if status and status not in history:
                history.append(status)

            shipment_patch: dict[str, Any] = {
                "id": shipment_id,
                "type": "Shipment",
                "status_history": history,
            }
            if "shipment_weight" in scenario.inputs:
                shipment_patch["weight"] = scenario.inputs["shipment_weight"]
            if "weight" in response_body:
                shipment_patch["weight"] = response_body["weight"]
            if status:
                shipment_patch["status"] = status
            if vehicle_id:
                shipment_patch["assigned_vehicle"] = vehicle_id
            if "vehicle_capacity" in response_body:
                shipment_patch["vehicle_capacity"] = response_body["vehicle_capacity"]
            if "dispatched_at" in response_body:
                shipment_patch["dispatched_at"] = response_body["dispatched_at"]

            await self._state_store.update_entity(run_id, str(shipment_id), shipment_patch)

        if vehicle_id:
            vehicle_patch: dict[str, Any] = {"id": vehicle_id, "type": "Vehicle"}
            if "vehicle_capacity" in response_body:
                vehicle_patch["capacity"] = response_body["vehicle_capacity"]
            elif "vehicle_capacity" in state_values:
                vehicle_patch["capacity"] = state_values["vehicle_capacity"]

            await self._state_store.update_entity(run_id, str(vehicle_id), vehicle_patch)

    def _client(self) -> httpx.AsyncClient:
        if self._app is not None:
            transport = httpx.ASGITransport(app=self._app)
            return httpx.AsyncClient(transport=transport, base_url="http://testserver")
        return httpx.AsyncClient(base_url=self._base_url)


def _resolve_map(template: dict, scenario_inputs: dict, state_values: dict) -> dict:
    resolved: dict[str, Any] = {}
    for key, value in template.items():
        resolved[key] = _resolve_value(value, scenario_inputs, state_values)
    return resolved


def _resolve_value(value: Any, scenario_inputs: dict, state_values: dict) -> Any:
    if not isinstance(value, str):
        return value
    if value.startswith("$scenario."):
        return _dot_get(scenario_inputs, value.removeprefix("$scenario."))
    if value.startswith("$state."):
        return _dot_get(state_values, value.removeprefix("$state."))
    return value


def _dot_get(data: dict, path: str) -> Any:
    current: Any = data
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def _render_endpoint(endpoint_template: str, path_params: dict) -> str:
    return endpoint_template.format(**path_params) if path_params else endpoint_template


def _parse_response_body(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return {"raw": response.text}


def _extract_values(extract_map: dict, response_body: dict) -> dict[str, Any]:
    extracted: dict[str, Any] = {}
    for key, pointer in extract_map.items():
        if not isinstance(pointer, str):
            extracted[key] = pointer
            continue
        if pointer.startswith("$.response."):
            extracted[key] = _dot_get(response_body, pointer.removeprefix("$.response."))
            continue
        if pointer == "$.response":
            extracted[key] = response_body
            continue
        extracted[key] = pointer
    return extracted

