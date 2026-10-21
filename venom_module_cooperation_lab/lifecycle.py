"""Bounded optional lifecycle; no model work, downloads or automatic runs."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import Any

from .storage import LabStore


def enabled() -> bool:
    return os.getenv("FEATURE_COOPERATION_LAB", "false").lower() in {"1", "true"}


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
            self.store.open()
            await asyncio.sleep(0)
        except Exception:
            self.state, self.reason = "not_ready", "storage_unavailable"
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
        def deny(_owner: str, _operation: str) -> None:
            raise PermissionError("host_access_policy_required")

        return LabStore.from_host(deny)

    lifecycle = LabLifecycle(factory)
    app.state.cooperation_lab = lifecycle
    try:
        await asyncio.wait_for(lifecycle.start(enabled()), timeout=1.5)
        yield
    finally:
        await asyncio.wait_for(lifecycle.close(), timeout=1.5)
