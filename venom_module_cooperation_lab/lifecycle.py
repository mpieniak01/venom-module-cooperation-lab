"""Bounded optional lifecycle; no model work, downloads or automatic runs."""

from __future__ import annotations

import asyncio
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


class LabLifecycle:
    def __init__(self, factory: Callable[[], LabStore]) -> None:
        self.factory = factory
        self.store: LabStore | None = None
        self.state = "disabled"
        self.reason = "module_disabled"

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

            from .adapters.registry import create_adapter, list_model_specs
            from .runner import LabRunner

            runner = LabRunner(
                lifecycle.store,
                get_runtime_admission(),
                list_model_specs,
                create_adapter,
            )
        app.state.cooperation_lab_runner = runner
        yield
    finally:
        runner = getattr(app.state, "cooperation_lab_runner", None)
        if runner is not None:
            await runner.close()
        await asyncio.wait_for(lifecycle.close(), timeout=1.5)
