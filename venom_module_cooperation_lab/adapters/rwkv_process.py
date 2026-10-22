"""One isolated RWKV worker, shared immutable weights, separate A/B state.

No download, imports of Torch, automatic load, HTTP endpoint or host selection
mutation. The host must hold RuntimeLease.operation across load, inference and
close/join; this component reports quiescence only after worker acknowledgement
with CUDA synchronization, or confirmed process exit.
"""

from __future__ import annotations

import hashlib
import json
import math
import multiprocessing
import os
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .component import verify_overlay
from .rwkv_worker import worker_main

MODEL_SHA256 = "947cb9b8013224e06b112b72204256bec65096cc935a7767ce63d8e3ddef83bb"
TOKENIZER_SHA256 = "8324476023347dec2964625ccb2075c864d250a9c6d9a74f36daba628de8c008"
RUNTIME_SHA256 = "75482aee89a08d2a8c8dbe628110b317fc8d0974ddffbaa52aa19190667305e0"
MODEL_REVISION = "2a17e911155a5be23a4ed2792e978c77038f14e2"
MODEL_FILENAME = "rwkv7-g1d-0.4b-20260210-ctx8192.pth"
MAX_WIRE_BYTES = 65536


class RwkvError(RuntimeError):
    pass


@dataclass(frozen=True)
class RwkvConfig:
    model_path: Path
    runtime_root: Path
    strategy: str = "cuda fp16"
    model_sha256: str | None = None

    def validate(self) -> None:
        if self.strategy not in {"cuda fp16", "cpu fp32"}:
            raise RwkvError("unsupported_precision")
        expected = (
            (self.model_path, self.model_sha256 or MODEL_SHA256),
            (self.runtime_root / "rwkv" / "model.py", RUNTIME_SHA256),
            (self.runtime_root / "rwkv" / "rwkv_vocab_v20230424.txt", TOKENIZER_SHA256),
        )
        for path, digest in expected:
            if not path.is_file():
                raise RwkvError("artifact_missing")
            with path.open("rb") as source:
                if hashlib.file_digest(source, "sha256").hexdigest() != digest:
                    raise RwkvError("artifact_hash_mismatch")
        try:
            verify_overlay(self.runtime_root)
        except (OSError, RuntimeError) as exc:
            raise RwkvError("component_overlay_unverified") from exc


@dataclass(frozen=True)
class RwkvParameters:
    max_new_tokens: int = 128
    temperature: float = 0.8
    top_p: float = 0.5
    seed: int = 0
    max_context_tokens: int = 2048
    profile: str = "chat"
    allowed_outputs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.profile not in {"chat", "structured"}:
            raise RwkvError("invalid_parameters")
        if (
            not isinstance(self.allowed_outputs, tuple)
            or len(self.allowed_outputs) > 9
            or any(
                not isinstance(v, str)
                or len(v) != 2
                or v[0] not in "ABC"
                or v[1] not in "123"
                for v in self.allowed_outputs
            )
            or len(set(self.allowed_outputs)) != len(self.allowed_outputs)
            or (
                self.allowed_outputs
                and (
                    self.profile != "structured"
                    or self.temperature != 0
                    or self.top_p != 0
                )
            )
        ):
            raise RwkvError("invalid_parameters")
        for name, lower, upper in (
            ("max_new_tokens", 1, 256),
            ("seed", 0, 2**31 - 1),
            ("max_context_tokens", 1, 2048),
        ):
            value = getattr(self, name)
            if type(value) is not int or not lower <= value <= upper:
                raise RwkvError("invalid_parameters")
        for name, maximum in (("temperature", 2.0), ("top_p", 1.0)):
            numeric = getattr(self, name)
            if (
                type(numeric) not in (float, int)
                or not math.isfinite(numeric)
                or not 0 <= numeric <= maximum
            ):
                raise RwkvError("invalid_parameters")


class RwkvAdapter:
    def __init__(self, config: RwkvConfig) -> None:
        self.config = config
        self._context = multiprocessing.get_context("spawn")
        self._cancel = self._context.Event()
        self._process: Any = None
        self._connection: Any = None
        self._lock = threading.Lock()
        self._busy = threading.Event()
        self._termination_lock = threading.Lock()
        self._state = "available"
        self._sequence = 0
        self.receipt: dict[str, Any] = {}

    def load(self, timeout_s: float = 120.0) -> dict[str, Any]:
        with self._lock:
            if self._state != "available" or self._cancel.is_set():
                raise RwkvError("invalid_state")
            self.config.validate()
            self._state = "loading"
            parent, child = self._context.Pipe()
            self._connection = parent
            self._process = self._context.Process(
                target=worker_main,
                args=(child, self._cancel, asdict(self.config), os.getpid()),
                daemon=True,
                name="cooperation-rwkv",
            )
            self._busy.set()
            try:
                self._process.start()
                child.close()
                response = self._receive(timeout_s)
                self.receipt = response
                self._state = "ready"
                return response
            except BaseException:
                self._state = "failed"
                self._terminate()
                raise
            finally:
                self._busy.clear()

    def _receive(self, timeout_s: float) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self._connection.poll(min(0.1, max(0.0, deadline - time.monotonic()))):
                try:
                    response = json.loads(self._connection.recv_bytes(MAX_WIRE_BYTES))
                except (EOFError, OSError, ValueError) as exc:
                    raise RwkvError("worker_protocol_error") from exc
                if not isinstance(response, dict):
                    raise RwkvError("worker_protocol_error")
                if response.get("error"):
                    raise RwkvError(str(response["error"]))
                return response
            if not self._process.is_alive():
                raise RwkvError("worker_failed")
        self.cancel()
        self._terminate()
        raise RwkvError("generation_timeout")

    def _request(
        self, command: str, payload: dict[str, Any], timeout_s: float
    ) -> dict[str, Any]:
        if not self._lock.acquire(blocking=False):
            raise RwkvError("runtime_busy")
        try:
            if self._state != "ready" or self._cancel.is_set():
                raise RwkvError("invalid_state")
            self._sequence += 1
            encoded = json.dumps(
                {"command": command, "request_id": self._sequence, **payload},
                allow_nan=False,
            ).encode()
            if len(encoded) > MAX_WIRE_BYTES:
                raise RwkvError("request_too_large")
            self._busy.set()
            self._state = "running"
            self._connection.send_bytes(encoded)
            response = self._receive(timeout_s)
            if response.get("request_id") != self._sequence:
                self._terminate()
                raise RwkvError("worker_protocol_error")
            self._state = "cancelled" if self._cancel.is_set() else "ready"
            return response
        except BaseException:
            if self._process is not None and not self._process.is_alive():
                self._state = "failed"
            elif self._state == "running":
                self._state = "cancelled" if self._cancel.is_set() else "ready"
            raise
        finally:
            self._busy.clear()
            self._lock.release()

    def generate(
        self,
        participant: str,
        prompt: str,
        parameters: RwkvParameters | None = None,
        timeout_s: float = 90.0,
    ) -> dict[str, Any]:
        if (
            participant not in {"A", "B"}
            or not isinstance(prompt, str)
            or not 0 < len(prompt.encode()) <= 16384
        ):
            raise RwkvError("invalid_input")
        if not math.isfinite(timeout_s) or not 0 < timeout_s <= 360:
            raise RwkvError("invalid_deadline")
        return self._request(
            "generate",
            {
                "participant": participant,
                "prompt": prompt,
                "parameters": asdict(parameters or RwkvParameters()),
                "timeout_s": timeout_s,
            },
            timeout_s + 2,
        )

    def reset(self, participant: str | None = None) -> dict[str, Any]:
        if participant not in {None, "A", "B"}:
            raise RwkvError("invalid_input")
        return self._request("reset", {"participant": participant}, 5)

    def state(self) -> dict[str, Any]:
        return self._request("state", {}, 10)

    def cancel(self) -> None:
        self._cancel.set()
        if self._busy.is_set():
            self._state = "cancelling"

    def status(self) -> dict[str, Any]:
        return {
            "state": self._state,
            "busy": self._busy.is_set(),
            "quiescent": not self._busy.is_set() and self._state != "quarantined",
            "cancel_requested": self._cancel.is_set(),
        }

    def _terminate(self) -> None:
        with self._termination_lock:
            if self._process is None or self._process.pid is None:
                return
            if self._process.is_alive():
                self._process.terminate()
                self._process.join(3)
            if self._process.is_alive():
                self._process.kill()
                self._process.join(3)
            if self._process.is_alive():
                self._state = "quarantined"
                raise RwkvError("worker_not_quiescent")

    def close(self) -> bool:
        self.cancel()
        acquired = self._lock.acquire(timeout=2)
        if not acquired:
            self._terminate()
            acquired = self._lock.acquire(timeout=2)
        if not acquired:
            self._state = "quarantined"
            raise RwkvError("worker_not_quiescent")
        try:
            if self._process is not None and self._process.pid is not None:
                if self._process.is_alive():
                    try:
                        self._connection.send_bytes(
                            b'{"command":"close","request_id":0}'
                        )
                    except (OSError, EOFError):
                        pass
                    self._process.join(2)
                self._terminate()
            if self._connection is not None:
                self._connection.close()
            self._state = "closed"
            return True
        finally:
            self._lock.release()
