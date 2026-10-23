"""Local operator evaluation routes; inherit module guards and error policy."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Header, Query, Request, Response

from .config import EvaluationRequest
from .model_settings import ModelBudgets, read_budgets, save_budgets
from .reports import export
from .service import EvaluationService


def register(router: APIRouter, require_runner: Callable[[Request], Any]) -> None:
    def service(request: Request) -> EvaluationService:
        runner = require_runner(request)
        value = getattr(request.app.state, "cooperation_lab_evaluations", None)
        if value is None:
            value = EvaluationService(runner)
            request.app.state.cooperation_lab_evaluations = value
        return value

    async def refreshed(request: Request) -> EvaluationService:
        value = service(request)
        catalog = value.runner.catalog_service
        if catalog is not None:
            await catalog.refresh()
        return value

    @router.get("/evaluations/capabilities")
    async def capabilities(request: Request) -> dict[str, Any]:
        return (await refreshed(request)).capabilities()

    @router.post("/evaluations/preflight")
    async def preflight(request: Request, payload: EvaluationRequest) -> dict[str, Any]:
        return (await refreshed(request)).preflight(payload)

    @router.get("/evaluations")
    async def listed(request: Request) -> dict[str, Any]:
        return {"evaluations": service(request).list()}

    @router.post("/evaluations", status_code=202)
    async def start(
        request: Request,
        payload: EvaluationRequest,
        idempotency_key: Annotated[str, Header(min_length=1, max_length=128)],
    ) -> dict[str, Any]:
        value, created = await (await refreshed(request)).start(
            payload, idempotency_key
        )
        return {"evaluation": value, "created": created}

    @router.get("/evaluations/model-settings/{model_id}")
    async def model_settings(request: Request, model_id: str) -> dict[str, Any]:
        value = await refreshed(request)
        model = value.runner._runnable_model(model_id)
        return read_budgets(value.runner.store, model)

    @router.put("/evaluations/model-settings/{model_id}")
    async def store_model_settings(
        request: Request, model_id: str, payload: ModelBudgets
    ) -> dict[str, Any]:
        value = await refreshed(request)
        model = value.runner._runnable_model(model_id)
        return save_budgets(value.runner.store, model, payload)

    @router.get("/evaluations/{eid}")
    async def snapshot(request: Request, eid: str) -> dict[str, Any]:
        return {"evaluation": service(request).snapshot(eid)}

    @router.post("/evaluations/{eid}/recover", status_code=200)
    async def recover(request: Request, eid: str) -> dict[str, Any]:
        return {"evaluation": await service(request).recover_quiescent(eid)}

    @router.post("/evaluations/{eid}/cancel", status_code=202)
    async def cancel(request: Request, eid: str) -> dict[str, Any]:
        return {"evaluation": await service(request).cancel(eid)}

    @router.post("/evaluations/{eid}/resume", status_code=202)
    async def resume(request: Request, eid: str) -> dict[str, Any]:
        return {"evaluation": await (await refreshed(request)).resume(eid)}

    @router.delete("/evaluations/{eid}")
    async def deleted(request: Request, eid: str) -> dict[str, bool]:
        await service(request).delete(eid)
        return {"deleted": True}

    @router.get("/evaluations/{eid}/export")
    async def exported(
        request: Request,
        eid: str,
        format: Literal["json", "jsonl", "csv"] = Query("json"),
    ) -> Response:
        snapshot = service(request).snapshot(eid)
        content, mime = export(snapshot, format)
        if len(content.encode()) > service(request).runner.store.limits.run_bytes * 2:
            from ..errors import LabError

            raise LabError("export_too_large", 413)
        filename = f"evaluation-{snapshot['id']}.{format}"
        return Response(
            content,
            media_type=mime,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "no-store",
            },
        )
