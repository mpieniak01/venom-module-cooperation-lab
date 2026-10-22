"""Frozen generation contract shared by recurrent and stateless model adapters."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Protocol

from ..errors import LabError


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str

    def __post_init__(self) -> None:
        if (
            self.role not in {"system", "user", "assistant"}
            or not isinstance(self.content, str)
            or len(self.content.encode()) > 16384
        ):
            raise LabError("invalid_message", 422)


@dataclass(frozen=True)
class GenerationParameters:
    max_new_tokens: int = 128
    max_context_tokens: int = 2048
    temperature: float = 0.8
    top_p: float = 0.5
    seed: int = 0
    profile: str = "chat"
    allowed_outputs: tuple[str, ...] = ()
    num_steps: int = 8
    session_protocol: str = "v1"

    def __post_init__(self) -> None:
        if (
            self.profile not in {"chat", "structured"}
            or self.session_protocol not in {"v1", "game-eval-v2"}
            or type(self.num_steps) is not int
            or self.num_steps not in {8, 16, 32, 64}
        ):
            raise LabError("invalid_parameters", 422)
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
            raise LabError("invalid_parameters", 422)
        for name, lower, upper in (
            (
                "max_new_tokens",
                1,
                1024 if self.session_protocol == "game-eval-v2" else 256,
            ),
            ("seed", 0, 2**31 - 1),
            (
                "max_context_tokens",
                1,
                8192 if self.session_protocol == "game-eval-v2" else 2048,
            ),
        ):
            value = getattr(self, name)
            if type(value) is not int or not lower <= value <= upper:
                raise LabError("invalid_parameters", 422)
        for name, maximum in (("temperature", 2.0), ("top_p", 1.0)):
            numeric = getattr(self, name)
            if (
                type(numeric) not in (float, int)
                or not math.isfinite(numeric)
                or not 0 <= numeric <= maximum
            ):
                raise LabError("invalid_parameters", 422)


@dataclass(frozen=True)
class ModelSpec:
    model_id: str
    architecture: str
    provider: str
    artifact: str
    revision: str
    digest: str
    tokenizer_hash: str
    template_hash: str
    runtime: str
    quantization: str
    qualification: str = "host_acceptance_pending"
    qualified: bool = False
    availability_reason: str = "host_acceptance_pending"
    capabilities: tuple[str, ...] = ("text", "two_private_contexts", "cancel", "reset")


@dataclass(frozen=True)
class GenerationResult:
    text: str
    input_tokens: int | None
    output_tokens: int | None
    ttft_s: float | None
    generation_s: float
    stop_reason: str
    effective_parameters: Mapping[str, Any]
    quiescent: bool
    raw_text: str | None = None
    peak_vram_bytes: int | None = None


class Lease(Protocol):
    def operation(
        self, *, kind: str = "generation"
    ) -> AbstractContextManager[None]: ...
    def cancel(self) -> None: ...
    def cleanup(
        self, *, confirm_quiescent: Callable[[], bool]
    ) -> AbstractContextManager[None]: ...


class ModelAdapter(Protocol):
    spec: ModelSpec

    def load(self, deadline_s: float) -> dict[str, Any]: ...
    def generate(
        self,
        participant_id: str,
        messages: Sequence[ChatMessage],
        parameters: GenerationParameters,
        deadline_s: float,
    ) -> GenerationResult: ...
    def cancel(self) -> None: ...
    def reset(self, participant_id: str | None = None) -> dict[str, Any]: ...
    def state(self) -> dict[str, Any]: ...
    def close(self) -> bool: ...
    def is_quiescent(self) -> bool: ...


def validate_messages(
    participant_id: str,
    messages: Sequence[ChatMessage],
    *,
    protocol: str = "v1",
) -> None:
    # V2 preserves exact event history; the backend still enforces real tokens.
    limit = 512 if protocol == "game-eval-v2" else 24
    if participant_id not in {"A", "B"} or not messages or len(messages) > limit:
        raise LabError("invalid_messages", 422)
    if (
        messages[-1].role != "user"
        or sum(len(message.content.encode()) for message in messages) > 16384
    ):
        raise LabError("context_budget_exceeded", 422)


def remaining(deadline_s: float, maximum: float = 120) -> float:
    import time

    value = deadline_s - time.monotonic()
    if not math.isfinite(value) or value <= 0:
        raise LabError("generation_timeout", 408)
    return min(value, maximum)
