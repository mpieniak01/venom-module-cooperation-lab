"""Existing local Ollama control; cancel drains to actual terminal completion."""

from __future__ import annotations

import hashlib
import json
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Sequence
from dataclasses import asdict
from typing import Any

from ..errors import LabError
from .base import (
    ChatMessage,
    GenerationParameters,
    GenerationResult,
    Lease,
    ModelAdapter,
    ModelSpec,
    remaining,
    validate_messages,
)

MAX_RESPONSE_BYTES = 262144


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        raise LabError("runtime_redirect_rejected")


class OllamaAdapter(ModelAdapter):
    def __init__(self, spec: ModelSpec, lease: Lease) -> None:
        self.spec, self._lease = spec, lease
        # A trusted local endpoint, never a request/model-controlled URL.
        self._endpoint = "http://127.0.0.1:11434"
        self._opener = urllib.request.build_opener(NoRedirect())
        self._cancel = threading.Event()
        self._busy = False
        self._uncertain = False
        self._request_sent = False
        self._state = "available"
        self._histories: dict[str, tuple[ChatMessage, ...]] = {"A": (), "B": ()}

    def _open(self, path: str, payload: dict[str, Any] | None, timeout_s: float) -> Any:
        body = (
            None if payload is None else json.dumps(payload, allow_nan=False).encode()
        )
        request = urllib.request.Request(
            self._endpoint + path,
            data=body,
            headers={"Content-Type": "application/json"},
        )
        return self._opener.open(request, timeout=timeout_s)

    def _json(self, path: str, payload: dict[str, Any] | None, timeout_s: float) -> Any:
        with self._open(path, payload, timeout_s) as response:
            data = response.read(MAX_RESPONSE_BYTES + 1)
        if len(data) > MAX_RESPONSE_BYTES:
            raise LabError("runtime_response_too_large")
        return json.loads(data)

    def load(self, deadline_s: float) -> dict[str, Any]:
        with self._lease.operation(kind="generation"):
            try:
                version = self._json("/api/version", None, remaining(deadline_s, 5))
                tags = self._json("/api/tags", None, remaining(deadline_s, 5))
                match = next(
                    (
                        item
                        for item in tags.get("models", [])
                        if item.get("name") == self.spec.artifact
                    ),
                    None,
                )
                if match is None:
                    raise LabError("artifact_missing")
                if (
                    match.get("digest") != self.spec.digest
                    or "ollama==" + str(version.get("version")) != self.spec.runtime
                ):
                    raise LabError("model_identity_changed")
                show = self._json(
                    "/api/show", {"model": self.spec.artifact}, remaining(deadline_s, 5)
                )
                if (
                    hashlib.sha256(show.get("template", "").encode()).hexdigest()
                    != self.spec.template_hash
                ):
                    raise LabError("model_template_changed")
                self._state = "ready"
                return {
                    "state": "ready",
                    "weights_loaded": False,
                    "metadata_verified": True,
                    "runtime": "ollama",
                    "runtime_version": version["version"],
                    "model_digest": match["digest"],
                    "quantization": match.get("details", {}).get("quantization_level"),
                    "think": False,
                }
            except (
                urllib.error.URLError,
                OSError,
                ValueError,
                TypeError,
                AttributeError,
            ) as exc:
                self._state = "failed"
                raise LabError("runtime_unavailable") from exc

    def generate(
        self,
        participant_id: str,
        messages: Sequence[ChatMessage],
        parameters: GenerationParameters,
        deadline_s: float,
    ) -> GenerationResult:
        validate_messages(
            participant_id, messages, protocol=parameters.session_protocol
        )
        if self._cancel.is_set() or self._state != "ready":
            raise LabError("invalid_state")
        # UTF-8 bytes are a conservative upper bound, rather than claiming an
        # unavailable tokenizer or silently accepting runtime truncation.
        byte_bound = 256 + sum(
            len(message.content.encode()) + 16 for message in messages
        )
        if byte_bound + parameters.max_new_tokens > parameters.max_context_tokens:
            raise LabError("context_budget_exceeded", 422)
        with self._lease.operation(kind="generation"):
            self._busy = True
            self._request_sent = True
            started = time.monotonic()
            self._state = "running"
            payload = {
                "model": self.spec.artifact,
                "messages": [asdict(message) for message in messages],
                "stream": True,
                "think": False,
                "keep_alive": 0,
                "options": {
                    "num_predict": parameters.max_new_tokens,
                    "num_ctx": parameters.max_context_tokens,
                    "temperature": parameters.temperature,
                    "top_p": parameters.top_p,
                    "seed": parameters.seed,
                },
            }
            terminal = None
            try:
                text, ttft, terminal = self._consume_generation(
                    payload, deadline_s, started
                )
                if terminal is None:
                    self._uncertain = True
                    raise LabError("runtime_not_quiescent")
                for name in ("prompt_eval_count", "eval_count"):
                    value = terminal.get(name)
                    if value is not None and (type(value) is not int or value < 0):
                        raise LabError("malformed_model_usage")
                cancelled = self._cancel.is_set()
                if not cancelled:
                    self._histories[participant_id] = (
                        *messages,
                        ChatMessage("assistant", text),
                    )
                self._state = "cancelled" if cancelled else "ready"
                return GenerationResult(
                    text=text,
                    input_tokens=terminal.get("prompt_eval_count"),
                    output_tokens=terminal.get("eval_count"),
                    ttft_s=ttft,
                    generation_s=time.monotonic() - started,
                    stop_reason="cancelled"
                    if cancelled
                    else str(terminal.get("done_reason", "stop")),
                    effective_parameters={
                        **asdict(parameters),
                        "num_steps_requested": parameters.num_steps,
                        "num_steps_applied": None,
                        "num_steps": None,
                        "think": False,
                        "keep_alive": 0,
                        "input_bound_method": "utf8_bytes_plus_role_overhead",
                    },
                    quiescent=True,
                )
            except (
                urllib.error.URLError,
                OSError,
                ValueError,
                TypeError,
                AttributeError,
            ) as exc:
                self._uncertain = True
                self._state = "failed"
                raise LabError("runtime_transport_failed") from exc
            except LabError:
                self._uncertain = terminal is None
                self._state = "quarantined" if self._uncertain else "failed"
                raise
            finally:
                self._busy = False

    @staticmethod
    def _generation_chunk(item: Any) -> str:
        if not isinstance(item, dict) or item.get("error"):
            raise LabError("generation_failed")
        chunk = item.get("message", {}).get("content", "")
        if not isinstance(chunk, str):
            raise LabError("malformed_model_output")
        return chunk

    def _consume_generation(
        self, payload: dict[str, Any], deadline_s: float, started: float
    ) -> tuple[str, float | None, dict[str, Any] | None]:
        text, ttft, consumed = "", None, 0
        with self._open("/api/chat", payload, remaining(deadline_s, 360)) as response:
            while time.monotonic() < deadline_s:
                line = response.readline(MAX_RESPONSE_BYTES + 1)
                if not line:
                    break
                consumed += len(line)
                if consumed > MAX_RESPONSE_BYTES:
                    raise LabError("runtime_response_too_large")
                item = json.loads(line)
                chunk = self._generation_chunk(item)
                if chunk and ttft is None:
                    ttft = time.monotonic() - started
                text += chunk
                if len(text.encode()) > 16384:
                    raise LabError("runtime_response_too_large")
                if item.get("done") is True:
                    return text, ttft, item
        return text, ttft, None

    def cancel(self) -> None:
        self._lease.cancel()
        self._cancel.set()
        if self._busy:
            self._state = "cancelling"
        # Deliberately keep reading until done. Socket closure is not GPU STOP.

    def reset(self, participant_id: str | None = None) -> dict[str, Any]:
        if participant_id not in {None, "A", "B"}:
            raise LabError("invalid_participant", 422)
        if self._busy:
            raise LabError("runtime_busy")
        for participant in (participant_id,) if participant_id else ("A", "B"):
            self._histories[participant] = ()
        return {"state": "reset"}

    def state(self) -> dict[str, Any]:
        return {
            "state": self._state,
            "busy": self._busy,
            "quiescent": self.is_quiescent(),
            "history_messages": {
                participant: len(history)
                for participant, history in self._histories.items()
            },
        }

    def is_quiescent(self) -> bool:
        return not self._busy and not self._uncertain

    def close(self) -> bool:
        self._cancel.set()
        with self._lease.cleanup(confirm_quiescent=self.is_quiescent):
            if not self.is_quiescent():
                raise LabError("runtime_not_quiescent")
            if self._request_sent:
                deadline = time.monotonic() + 2
                while True:
                    try:
                        running = self._json(
                            "/api/ps", None, max(0.1, deadline - time.monotonic())
                        )
                        present = any(
                            item.get("name") == self.spec.artifact
                            for item in running.get("models", [])
                        )
                    except (OSError, ValueError, TypeError, AttributeError) as exc:
                        self._uncertain = True
                        raise LabError("runtime_not_quiescent") from exc
                    if not present:
                        break
                    if time.monotonic() >= deadline:
                        self._uncertain = True
                        raise LabError("runtime_not_quiescent")
                    time.sleep(0.05)
            self._histories = {"A": (), "B": ()}
            self._state = "closed"
            return True
