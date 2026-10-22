"""Versioned game sessions: exact replay or isolated native RWKV continuity.

Histories contain only observations supplied by the environment and the model's
own answers. Nothing is compressed or silently discarded. Native mode passes an
append-only message sequence to RecurrentAdapter, whose worker receives only its
unseen suffix. Tensor snapshots are deliberately not promised.
"""

from __future__ import annotations

from dataclasses import asdict, replace
from typing import Any

from ..adapters.base import (
    ChatMessage,
    GenerationParameters,
    GenerationResult,
    ModelAdapter,
    validate_messages,
)
from ..errors import LabError

PROTOCOL = "game-eval-v2"
SUPPORTED_ARCHITECTURES = {"rwkv7", "hrm_text", "huginn_raven"}


def capabilities_for(model_spec: dict[str, Any]) -> dict[str, Any]:
    """Capabilities of these adapters, not claims inferred from a model name."""
    architecture = model_spec.get("architecture")
    ollama_replay = model_spec.get("provider") == "ollama" and str(
        model_spec.get("runtime", "")
    ).startswith("ollama==")
    supported = architecture in SUPPORTED_ARCHITECTURES or ollama_replay
    native = architecture == "rwkv7" and "rwkv-chat-v2" in str(
        model_spec.get("runtime", "")
    )
    return {
        "protocol": PROTOCOL,
        "observation_modes": (["history_replay"] if supported else [])
        + (["native_incremental"] if native else []),
        "episode_memories": ["fresh", "carry"] if supported else [],
        "compute_steps": [8, 16, 32, 64] if architecture == "huginn_raven" else [],
        "snapshot_restore": False,
        "max_context_tokens": 8192
        if architecture == "rwkv7" or (ollama_replay and architecture == "gemma4")
        else (4096 if architecture in {"hrm_text", "huginn_raven"} else 2048),
        "max_new_tokens": 1024 if supported else 256,
        "max_decision_timeout_s": 300,
        "max_history_bytes": 16384,
        "max_history_messages": 512,
        "native_reason": None if native else "native_state_not_implemented",
        "reason": None if supported else "unsupported_model_adapter",
    }


class SessionDriver:
    """Own allowed A/B histories without changing model weights or global runtime.

    ``begin_episode`` must be called explicitly. A failed/interrupted generation
    cannot be resumed as though native continuity had survived; create a new
    driver/block instead. Backend token counting is authoritative, while this
    class also enforces bounded message/wire history before invoking it.
    """

    def __init__(
        self,
        adapter: ModelAdapter,
        observation_mode: str,
        episode_memory: str,
        max_context_tokens: int = 2048,
    ) -> None:
        self.adapter = adapter
        self.observation_mode = observation_mode
        self.episode_memory = episode_memory
        self.max_context_tokens = max_context_tokens
        self.capabilities = capabilities_for(asdict(adapter.spec))
        if (
            observation_mode not in self.capabilities["observation_modes"]
            or episode_memory not in self.capabilities["episode_memories"]
        ):
            raise LabError("unsupported_session_configuration", 422)
        if (
            type(max_context_tokens) is not int
            or not 1 <= max_context_tokens <= self.capabilities["max_context_tokens"]
        ):
            raise LabError("invalid_parameters", 422)
        self._histories: dict[str, list[ChatMessage]] = {"A": [], "B": []}
        self._cursors = {"A": 0, "B": 0}
        self._initialized = False
        self._interrupted = False
        self._episode = 0

    def begin_episode(
        self, memory_messages: dict[str, list[ChatMessage]] | None = None
    ) -> None:
        if self._interrupted:
            raise LabError("session_interrupted")
        if memory_messages is not None and (
            not isinstance(memory_messages, dict)
            or any(key not in {"A", "B"} for key in memory_messages)
            or any(
                not isinstance(items, list)
                or any(not isinstance(item, ChatMessage) for item in items)
                for items in memory_messages.values()
            )
        ):
            raise LabError("invalid_messages", 422)
        memories = memory_messages or {}
        if (
            self._initialized
            and self.episode_memory == "carry"
            and self.observation_mode == "native_incremental"
            and any(memories.values())
        ):
            raise LabError("unsupported_memory_injection", 422)
        fresh = not self._initialized or self.episode_memory == "fresh"
        candidate = {
            name: [] if fresh else list(items)
            for name, items in self._histories.items()
        }
        for participant, items in memories.items():
            candidate[participant].extend(items)
        for items in candidate.values():
            self._check_bounds(items)
        if fresh:
            self.adapter.reset()
            self._cursors = {"A": 0, "B": 0}
        self._histories = candidate
        self._initialized = True
        self._episode += 1

    def has_history(self, participant: str) -> bool:
        """Whether this participant already has retained allowed session events."""
        if participant not in {"A", "B"}:
            raise LabError("invalid_participant", 422)
        return bool(self._histories[participant])

    @staticmethod
    def _check_bounds(messages: list[ChatMessage]) -> None:
        if (
            len(messages) > 512
            or sum(len(m.content.encode()) for m in messages) > 16384
        ):
            raise LabError("context_budget_exceeded", 422)

    def generate(
        self,
        participant: str,
        observation: str,
        parameters: GenerationParameters,
        deadline: float,
    ) -> GenerationResult:
        if not self._initialized:
            raise LabError("session_not_started")
        if self._interrupted:
            raise LabError("session_interrupted")
        if participant not in {"A", "B"}:
            raise LabError("invalid_participant", 422)
        if (
            self.adapter.spec.architecture != "huginn_raven"
            and parameters.num_steps != 8
        ):
            raise LabError("unsupported_compute_steps", 422)
        messages = [*self._histories[participant], ChatMessage("user", observation)]
        self._check_bounds(messages)
        validate_messages(participant, messages, protocol=PROTOCOL)
        selected = replace(
            parameters,
            max_context_tokens=min(
                parameters.max_context_tokens, self.max_context_tokens
            ),
            session_protocol=PROTOCOL,
        )
        previous = self._cursors[participant] > 0
        try:
            if self.observation_mode == "history_replay":
                self.adapter.reset(participant)
            result = self.adapter.generate(participant, messages, selected, deadline)
        except Exception:
            self._interrupted = True
            raise
        if self.observation_mode == "native_incremental" and previous:
            if result.effective_parameters.get("context_mode") != "append":
                self._interrupted = True
                raise LabError("native_state_continuity_lost")
        if result.stop_reason in {"cancelled", "deadline"} or not result.quiescent:
            self._interrupted = True
        else:
            self._histories[participant] = [
                *messages,
                ChatMessage("assistant", result.text),
            ]
            self._cursors[participant] += 1
        return replace(
            result,
            effective_parameters={
                **result.effective_parameters,
                "session_protocol": PROTOCOL,
                "observation_mode": self.observation_mode,
                "episode_memory": self.episode_memory,
                "memory_kind": "native_state"
                if self.observation_mode == "native_incremental"
                else "text_history",
                "episode_index": self._episode,
                "event_cursor": self._cursors[participant],
                "snapshot_restore": False,
            },
        )
