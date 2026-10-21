from __future__ import annotations

import threading
from dataclasses import asdict

import pytest
from venom_core.services.runtime_admission import RuntimeAdmission

from venom_module_cooperation_lab.adapters.base import GenerationResult, ModelSpec
from venom_module_cooperation_lab.runner import OWNER, LabRunner
from venom_module_cooperation_lab.storage import LabStore

SPEC = ModelSpec(
    model_id="test-0.4b",
    architecture="fixture",
    provider="local_component",
    artifact="fixture",
    revision="revision1",
    digest="digest1",
    tokenizer_hash="tokenizer1",
    template_hash="template1",
    runtime="fixture1",
    quantization="none",
)


class FakeAdapter:
    """A bounded CPU fixture, explicitly not model qualification/inference."""

    def __init__(self, lease):
        self.lease = lease
        self.recorded = []
        self.entered = threading.Event()
        self.released = threading.Event()
        self.block = False
        self.block_load = False
        self.responses = []
        self.cancelled = False
        self.closed = False
        self.busy = False
        self.fail = None
        self.unknown_usage = False
        self.ignore_cancel = False
        self.identity = []

    def load(self, deadline):
        with self.lease.operation(kind="generation"):
            if self.block_load:
                self._pause()
            return {"state": "ready"}

    def _pause(self):
        self.busy = True
        self.entered.set()
        self.released.wait(2)
        self.busy = False

    def reset(self):
        return {"state": "reset"}

    def generate(self, participant, messages, parameters, deadline):
        with self.lease.operation(kind="generation"):
            self.recorded.append((participant, messages, parameters))
            if self.fail:
                raise self.fail
            if self.block:
                self._pause()
            text = (
                self.responses.pop(0)
                if self.responses
                else f"Message from {participant}"
            )
            return GenerationResult(
                text=text,
                input_tokens=None if self.unknown_usage else 20,
                output_tokens=None if self.unknown_usage else 8,
                ttft_s=0.001,
                generation_s=0.002,
                stop_reason="length",
                effective_parameters={"max_new_tokens": parameters.max_new_tokens},
                quiescent=True,
            )

    def cancel(self):
        self.cancelled = True
        if not self.ignore_cancel:
            self.released.set()

    def is_quiescent(self):
        return not self.busy

    def close(self):
        self.closed = True
        return self.is_quiescent()


@pytest.fixture
async def rig(tmp_path):
    def access(owner, _operation):
        if owner != OWNER:
            raise PermissionError("untrusted_owner")

    store = LabStore(tmp_path / "module", lambda _operation: None, access)
    store.open()
    store.put_document(
        "qualifications",
        SPEC.model_id,
        {
            **asdict(SPEC),
            "qualified": True,
            "receipt_id": "fixture-not-real-qualification",
        },
        owner=OWNER,
    )
    admission = RuntimeAdmission(tmp_path / "admission.sqlite3", enabled=True)
    adapters = []

    def factory(model, lease):
        assert model == SPEC.model_id
        adapter = FakeAdapter(lease)
        adapters.append(adapter)
        return adapter

    runner = LabRunner(store, admission, lambda: [SPEC], factory, cleanup_seconds=0.3)
    yield runner, adapters
    for adapter in adapters:
        adapter.released.set()
    await runner.close()
    # Allow bounded already-owned cleanup tasks to drain before closing storage.
    if runner._tasks:
        import asyncio

        await asyncio.wait(runner._tasks, timeout=1)
    store.close()
