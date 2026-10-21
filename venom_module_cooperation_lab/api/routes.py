"""Safe discovery endpoints. Generations are intentionally unavailable in L1."""

import os
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Request

from ..lifecycle import LabLifecycle, enabled, lifespan
from ..limits import Limits


def access(request: Request) -> None:
    # Reuse the actual administrative host policy, including its denied contract.
    from venom_core.api.routes.system_config import require_localhost_request

    require_localhost_request(request)


router = APIRouter(
    prefix="/api/v1/cooperation-lab",
    tags=["cooperation-lab"],
    dependencies=[Depends(access)],
    lifespan=lifespan,
)


def state(request: Request) -> dict[str, object]:
    lifecycle: LabLifecycle | None = getattr(request.app.state, "cooperation_lab", None)
    if not enabled():
        return {"state": "disabled", "reason_code": "module_disabled", "ready": False}
    if os.getenv("RUNTIME_ADMISSION_ENABLED", "false").lower() not in {"1", "true"}:
        return {
            "state": "not_ready",
            "reason_code": "runtime_admission_disabled",
            "ready": False,
        }
    return {
        "state": lifecycle.state if lifecycle else "not_ready",
        "reason_code": lifecycle.reason if lifecycle else "lifecycle_not_started",
        "ready": False,
    }


@router.get("/health")
async def health(request: Request) -> dict[str, object]:
    return {"module_id": "cooperation_lab", "schema_version": 1, **state(request)}


@router.get("/capabilities")
async def capabilities(request: Request) -> dict[str, object]:
    return {
        **state(request),
        "generation": False,
        "qualified_models": [],
        "participant_count": 2,
        "auto_start": False,
        "limits": asdict(Limits()),
        "host_module_api": "1.0.0",
    }


@router.post("/runs", status_code=503)
async def unavailable_run() -> None:
    from venom_core.core.module_data_policy import ensure_module_mutation_allowed

    ensure_module_mutation_allowed(
        module_id="cooperation_lab", operation_name="runs.create"
    )
    raise HTTPException(status_code=503, detail={"reason_code": "model_not_qualified"})
