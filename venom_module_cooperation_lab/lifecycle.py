"""Bounded optional lifecycle; no model work, downloads or automatic runs."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from contextlib import AbstractContextManager, asynccontextmanager, nullcontext
from typing import Any

from .storage import LabStore


def setting_enabled(name: str) -> bool:
    from venom_core.config import SETTINGS

    return bool(getattr(SETTINGS, name, False))


def enabled() -> bool:
    return setting_enabled("FEATURE_COOPERATION_LAB")


def admission_enabled() -> bool:
    return setting_enabled("RUNTIME_ADMISSION_ENABLED")


def _quarantine_owner_is_gone(snapshot: dict[str, Any]) -> bool:
    """Permit recovery-only startup after the quarantined API owner has exited."""
    if (
        snapshot.get("status") != "quarantined"
        or snapshot.get("active_operations") != 0
        or snapshot.get("owner") != "cooperation_lab"
        or snapshot.get("engine") != "ollama"
    ):
        return False
    pid = snapshot.get("owner_pid")
    if type(pid) is not int or pid <= 1:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except (PermissionError, OSError):
        return False
    return False


class LabLifecycle:
    def __init__(self, factory: Callable[[], LabStore]) -> None:
        self.factory = factory
        self.store: LabStore | None = None
        self.state = "disabled"
        self.reason = "module_disabled"
        self.recovery_only = False

    async def start(self, is_enabled: bool) -> None:
        if not is_enabled:
            return
        self.state, self.reason = "not_ready", "model_not_qualified"
        try:
            self.store = self.factory()
            # SQLite operations have a one-second lock timeout. No executor worker
            # can survive a cancelled lifecycle and secretly mutate after shutdown.
            admission_check: AbstractContextManager[None] = nullcontext()
            if admission_enabled():
                from venom_core.services.runtime_admission import get_runtime_admission

                admission = get_runtime_admission()
                if not admission.enabled:
                    from .errors import LabError

                    raise LabError("runtime_admission_disabled", 503)
                runtime = admission.snapshot()
                if _quarantine_owner_is_gone(runtime):
                    # The prior API PID is gone and no backend operation remains.
                    # Open state for the explicit recovery action; keep the
                    # runtime itself quarantined until Ollama is checked.
                    self.recovery_only = True
                else:
                    admission_check = admission.operation(kind="module_startup_check")
            # Own the host namespace before any module DB open/restart recovery.
            # A second API process must not mark the live worker's run interrupted.
            with admission_check:
                self.store.open()
            await asyncio.sleep(0)
        except Exception as exc:
            code = getattr(exc, "code", None)
            reason = (
                code
                if code
                in {
                    "runtime_topology_unsupported",
                    "runtime_busy",
                    "runtime_admission_disabled",
                }
                else "storage_unavailable"
            )
            self.state, self.reason = "not_ready", reason
            await self.close()

    async def close(self) -> None:
        if self.store is not None:
            self.store.close()
            self.store = None


@asynccontextmanager
async def lifespan(app: Any):
    def factory() -> LabStore:
        # Lifecycle owns only schema recovery. Requests must supply a trusted host
        # access policy before persisted run data is exposed in the later runner.
        def deny(owner: str, _operation: str) -> None:
            # Actor is selected by trusted host transport, never body/model JSON.
            if owner != "local_operator":
                raise PermissionError("host_access_policy_required")

        return LabStore.from_host(deny)

    lifecycle = LabLifecycle(factory)
    app.state.cooperation_lab = lifecycle
    try:
        await asyncio.wait_for(lifecycle.start(enabled()), timeout=1.5)
        runner = None
        if lifecycle.store and lifecycle.store.opened and admission_enabled():
            from venom_core.services.runtime_admission import get_runtime_admission

            from .catalog import ModelCatalog
            from .runner import LabRunner

            catalog = ModelCatalog()
            runner = LabRunner(
                lifecycle.store,
                get_runtime_admission(),
                catalog.specs,
                catalog.adapter,
                catalog_service=catalog,
            )
        app.state.cooperation_lab_runner = runner
        if runner is not None:
            from .evaluation.service import EvaluationService

            evaluations = EvaluationService(runner)
            evaluations.store.recover()
            app.state.cooperation_lab_evaluations = evaluations
        yield
    finally:
        evaluation_service = getattr(app.state, "cooperation_lab_evaluations", None)
        if evaluation_service is not None:
            await evaluation_service.close()
        runner = getattr(app.state, "cooperation_lab_runner", None)
        if runner is not None:
            await runner.close()
        await asyncio.wait_for(lifecycle.close(), timeout=1.5)
