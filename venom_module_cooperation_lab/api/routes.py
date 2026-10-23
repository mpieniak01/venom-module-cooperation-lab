"""Bounded operator API; GET is observational, POST owns detached execution."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from dataclasses import asdict
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import StreamingResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..errors import LabError
from ..evaluation.api import register as register_evaluations
from ..lifecycle import LabLifecycle, admission_enabled, enabled, lifespan
from ..limits import Limits
from ..model_limits import output_token_limit
from ..run_config import MODES, Budgets, RunRequest
from ..runner import OWNER, LabRunner
from ..scenarios import SCENARIOS
from ..storage import TERMINAL, _identifier


class LabRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        async def handle(request: Request) -> Response:
            try:
                return await original(request)
            except RequestValidationError as exc:
                fields = sorted(
                    {
                        error["loc"][1]
                        for error in exc.errors()
                        if len(error["loc"]) > 1
                        and error["loc"][0] == "body"
                        and error["loc"][1] in RunRequest.model_fields
                    }
                )
                logging.getLogger(__name__).warning(
                    "cooperation_lab rejected experiment parameters: fields=%s", fields
                )
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "invalid_parameters",
                        "reason_code": "invalid_parameters",
                        "fields": fields,
                    },
                ) from exc
            except LabError as exc:
                raise HTTPException(
                    status_code=exc.status,
                    detail={"code": exc.code, "reason_code": exc.code},
                ) from exc
            except PermissionError as exc:
                raise HTTPException(
                    status_code=403,
                    detail={
                        "code": "environment_read_only",
                        "reason_code": "environment_read_only",
                    },
                ) from exc

        return handle


def access(request: Request) -> None:
    from venom_core.api.routes.system_config import require_localhost_request

    require_localhost_request(request)
    if request.method in {"POST", "DELETE", "PATCH", "PUT"}:
        from venom_core.core.module_data_policy import ensure_module_mutation_allowed

        ensure_module_mutation_allowed(
            module_id="cooperation_lab",
            operation_name=request.method.lower() + ":" + request.url.path,
        )
        if request.headers.get("sec-fetch-site") == "cross-site":
            raise LabError("origin_denied", 403)


router = APIRouter(
    prefix="/api/v1/cooperation-lab",
    tags=["cooperation-lab"],
    dependencies=[Depends(access)],
    lifespan=lifespan,
    route_class=LabRoute,
)


def require_runner(request: Request) -> LabRunner:
    runner = getattr(request.app.state, "cooperation_lab_runner", None)
    if not enabled() or runner is None:
        raise LabError("model_not_qualified", 503)
    return runner


def state(request: Request) -> dict[str, Any]:
    lifecycle: LabLifecycle | None = getattr(request.app.state, "cooperation_lab", None)
    if not enabled():
        return {"state": "disabled", "reason_code": "module_disabled", "ready": False}
    if not admission_enabled():
        return {
            "state": "not_ready",
            "reason_code": "runtime_admission_disabled",
            "ready": False,
        }
    runner = getattr(request.app.state, "cooperation_lab_runner", None)
    if runner and any(
        model.get("can_run", model["qualified"]) for model in runner.models()
    ):
        return {
            "state": "ready",
            "reason_code": "qualified",
            "ready": True,
            "runtime": runner.admission.snapshot(),
        }
    return {
        "state": lifecycle.state if lifecycle else "not_ready",
        "reason_code": lifecycle.reason if lifecycle else "lifecycle_not_started",
        "ready": False,
    }


@router.get("/health")
async def health(request: Request) -> dict[str, Any]:
    return {"module_id": "cooperation_lab", "schema_version": 1, **state(request)}


def catalog_metadata() -> dict[str, Any]:
    from ..adapters.registry import list_model_specs

    return {
        "models": [asdict(model) for model in list_model_specs()],
        "scenarios": [scenario.public() for scenario in SCENARIOS],
        "modes": list(MODES),
        "preset": asdict(Budgets()),
        "participant_count": 2,
        "auto_start": False,
        "limits": asdict(Limits()),
        "host_module_api": "1.0.0",
    }


@router.get("/capabilities")
async def capabilities(request: Request) -> dict[str, Any]:
    runner = getattr(request.app.state, "cooperation_lab_runner", None)
    catalog = runner.catalog_service if runner is not None else None
    if catalog is not None:
        await catalog.refresh()
    current = state(request)
    metadata = catalog_metadata()
    models = runner.models() if runner is not None else metadata["models"]
    if catalog is not None:
        models = catalog.public_models(models)
        metadata.update(engines=catalog.engines, catalog_error=catalog.error)
    return {
        **metadata,
        **current,
        "generation": current["ready"],
        "models": [{**m, "max_new_tokens": output_token_limit(m)} for m in models],
        "qualified_models": [m["model_id"] for m in models if m["qualified"]],
    }


@router.post("/runs", status_code=202)
async def create_run(
    request: Request,
    payload: RunRequest,
    idempotency_key: Annotated[str, Header(min_length=1, max_length=128)],
) -> dict[str, Any]:
    runner = require_runner(request)
    row, created = await runner.start(payload, idempotency_key)
    return {"run": row, "created": created}


class QualificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    model_id: str = Field(
        min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$"
    )


@router.post("/qualifications", status_code=202)
async def qualify_model(
    request: Request,
    payload: QualificationRequest,
    idempotency_key: Annotated[str, Header(min_length=1, max_length=128)],
) -> dict[str, Any]:
    runner = require_runner(request)
    row, created = await runner.start(
        RunRequest(model_id=payload.model_id, scenario_id="split_facts"),
        idempotency_key,
        qualification=True,
    )
    return {"run": row, "created": created}


class OperatorMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    content: str = Field(min_length=1, max_length=2000)

    @field_validator("content")
    @classmethod
    def nonempty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("empty_operator_message")
        return value


@router.post("/runs/{run_id}/messages", status_code=202)
async def operator_message(
    request: Request,
    run_id: str,
    payload: OperatorMessage,
    idempotency_key: Annotated[str, Header(min_length=1, max_length=128)],
) -> dict[str, Any]:
    _identifier(run_id)
    return require_runner(request).operator_message(
        run_id, payload.content, idempotency_key
    )


@router.get("/runs")
async def list_runs(
    request: Request, limit: int = Query(20, ge=1, le=100), after: str | None = None
) -> dict[str, Any]:
    return {
        "runs": require_runner(request).store.list_runs(
            owner=OWNER, limit=limit, after=after
        )
    }


@router.get("/runs/{run_id}")
async def snapshot(request: Request, run_id: str) -> dict[str, Any]:
    _identifier(run_id)
    return require_runner(request).snapshot(run_id)


@router.post("/runs/{run_id}/cancel", status_code=202)
async def cancel(request: Request, run_id: str) -> dict[str, Any]:
    _identifier(run_id)
    return await require_runner(request).cancel(run_id)


def replay(
    runner: LabRunner, run_id: str, after: int, limit: int = 100
) -> dict[str, Any]:
    row = runner.store.get_run(run_id, owner=OWNER)
    if after > row["last_seq"]:
        raise LabError("resync_required", 409)
    events = runner.store.events(run_id, owner=OWNER, after=after, limit=limit)
    return {"events": events, "last_seq": row["last_seq"], "resync": False}


@router.get("/runs/{run_id}/events")
async def events(
    request: Request,
    run_id: str,
    after: int = Query(0, ge=0, le=2**31 - 1),
    limit: int = Query(100, ge=1, le=100),
) -> dict[str, Any]:
    _identifier(run_id)
    return replay(require_runner(request), run_id, after, limit)


async def _journal(
    request: Request, runner: LabRunner, run_id: str, cursor: int
) -> AsyncIterator[str]:
    position = cursor
    idle = 0
    while not await request.is_disconnected():
        page = replay(runner, run_id, position)
        for event in page["events"]:
            position = event["seq"]
            yield (
                f"id: {position}\nevent: {event['kind']}\n"
                f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            )
        row = runner.store.get_run(run_id, owner=OWNER)
        if row["status"] in TERMINAL and position >= row["last_seq"]:
            return
        idle += 1
        if idle % 50 == 0:
            yield ": keepalive\n\n"
        await asyncio.sleep(0.1)


@router.get("/runs/{run_id}/events/stream")
async def stream(
    request: Request,
    run_id: str,
    after: int = Query(0, ge=0, le=2**31 - 1),
    last_event_id: Annotated[str | None, Header(max_length=16)] = None,
) -> StreamingResponse:
    _identifier(run_id)
    cursor = after
    if last_event_id is not None:
        if not last_event_id.isdecimal() or int(last_event_id) > 2**31 - 1:
            raise LabError("invalid_cursor", 400)
        cursor = max(cursor, int(last_event_id))
    runner = require_runner(request)
    replay(runner, run_id, cursor)

    return StreamingResponse(
        _journal(request, runner, run_id, cursor),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


@router.get("/runs/{run_id}/export")
async def export(request: Request, run_id: str) -> Response:
    _identifier(run_id)
    data = require_runner(request).store.export_run(run_id, owner=OWNER)
    return Response(
        data,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="cooperation-{run_id}.json"',
            "Cache-Control": "no-store",
        },
    )


@router.delete("/runs/{run_id}", status_code=204)
async def delete(request: Request, run_id: str) -> Response:
    _identifier(run_id)
    require_runner(request).store.delete_run(run_id, owner=OWNER)
    return Response(status_code=204)


register_evaluations(router, require_runner)
