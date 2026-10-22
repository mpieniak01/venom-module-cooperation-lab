"""Lease-bound recurrent adapter with per-participant append-only contexts."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
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
from .rwkv_process import RwkvAdapter, RwkvConfig, RwkvError, RwkvParameters
from .rwkv_tokenizer import clean_message


class RecurrentAdapter(ModelAdapter):
    def __init__(
        self, spec: ModelSpec, lease: Lease, model_path: Path, runtime_root: Path
    ) -> None:
        self.spec, self._lease = spec, lease
        self._process = RwkvAdapter(
            RwkvConfig(model_path, runtime_root, model_sha256=spec.digest)
        )
        self._histories: dict[str, list[ChatMessage]] = {"A": [], "B": []}
        self._round_ended = {"A": False, "B": False}

    def load(self, deadline_s: float) -> dict[str, Any]:
        with self._lease.operation(kind="generation"):
            try:
                return self._process.load(remaining(deadline_s))
            except RwkvError as exc:
                raise LabError(str(exc)) from exc

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
        if parameters.num_steps != 8:
            raise LabError("unsupported_compute_steps", 422)
        with self._lease.operation(kind="generation"):
            previous = self._histories[participant_id]
            appending = (
                bool(previous)
                and list(messages[: len(previous)]) == previous
                and len(messages) > len(previous)
            )
            selected = messages[len(previous) :] if appending else messages
            if previous and not appending:
                self._process.reset(participant_id)
            prompt = (
                "\n\n".join(
                    f"{message.role.title()}: {clean_message(message.content)}"
                    for message in selected
                )
                + "\n\nAssistant:"
            )
            if appending and not self._round_ended[participant_id]:
                prompt = "\n\n" + prompt
            try:
                response = self._process.generate(
                    participant_id,
                    prompt,
                    RwkvParameters(**asdict(parameters)),
                    remaining(deadline_s, 360),
                )
            except RwkvError as exc:
                raise LabError(str(exc)) from exc
            if response["stop_reason"] not in {"cancelled", "deadline"}:
                self._round_ended[participant_id] = (
                    response["stop_reason"] == "stop_sequence"
                )
                self._histories[participant_id] = [
                    *messages,
                    ChatMessage("assistant", response["text"]),
                ]
            return GenerationResult(
                text=response["text"],
                raw_text=response.get("raw_text", response["text"]),
                input_tokens=response["input_tokens"],
                output_tokens=response["output_tokens"],
                ttft_s=response.get("ttft_s"),
                generation_s=response.get("generation_s", 0),
                stop_reason=response["stop_reason"],
                effective_parameters={
                    **response.get("effective_parameters", {}),
                    "context_mode": "append" if appending else "replay",
                },
                quiescent=response.get("quiescent", False),
            )

    def cancel(self) -> None:
        self._lease.cancel()
        self._process.cancel()

    def reset(self, participant_id: str | None = None) -> dict[str, Any]:
        if participant_id not in {None, "A", "B"}:
            raise LabError("invalid_participant", 422)
        with self._lease.operation(kind="generation"):
            result = self._process.reset(participant_id)
            for participant in (participant_id,) if participant_id else ("A", "B"):
                self._histories[participant] = []
                self._round_ended[participant] = False
            return result

    def state(self) -> dict[str, Any]:
        snapshot = self._process.status()
        return {
            **snapshot,
            "generation_quiescent": snapshot["quiescent"],
            "quiescent": self.is_quiescent(),
            "model_id": self.spec.model_id,
            "history_messages": {
                name: len(history) for name, history in self._histories.items()
            },
        }

    def close(self) -> bool:
        # Cleanup must remain possible after lease.cancel(), which blocks new ops.
        with self._lease.cleanup(confirm_quiescent=self.is_quiescent):
            result = self._process.close()
            self._histories = {"A": [], "B": []}
            self._round_ended = {"A": False, "B": False}
            return result

    def is_quiescent(self) -> bool:
        process = self._process._process
        return process is None or process.pid is None or not process.is_alive()
