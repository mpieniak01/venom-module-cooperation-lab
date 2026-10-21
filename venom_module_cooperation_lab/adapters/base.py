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

    def __post_init__(self) -> None:
        for name, lower, upper in (
            ("max_new_tokens", 1, 256),
            ("seed", 0, 2**31 - 1),
            ("max_context_tokens", 1, 2048),
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


def validate_messages(participant_id: str, messages: Sequence[ChatMessage]) -> None:
    if participant_id not in {"A", "B"} or not messages or len(messages) > 24:
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
