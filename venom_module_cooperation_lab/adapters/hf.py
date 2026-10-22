"""Pinned local HF models behind the existing lease and isolated process IPC."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ..errors import LabError
from .base import (
    ChatMessage,
    GenerationParameters,
    GenerationResult,
    Lease,
    ModelSpec,
    remaining,
    validate_messages,
)
from .rwkv import RecurrentAdapter
from .rwkv_process import RwkvAdapter, RwkvError, RwkvParameters

PINS = json.loads(Path(__file__).with_name("hf_artifacts.json").read_text())
TEMPLATES = {
    "hrm-text-1b": (
        "prefixlm-v2:fewshot2;direct=object_ref_start;"
        "synth,cot=quad_end,object_ref_end;token_type_ids=1;replay"
    ),
    "huginn-0125": (
        "huginn-native-template-v2:tied-map-v5;bf16;num_steps=8;cache=false;replay"
    ),
}


def pinned_specs() -> tuple[ModelSpec, ...]:
    return tuple(
        ModelSpec(
            model_id=mid,
            architecture="hrm_text" if mid == "hrm-text-1b" else "huginn_raven",
            provider="local_component",
            artifact=pin["repository"],
            revision=pin["revision"],
            digest=hashlib.sha256(json.dumps(pin, sort_keys=True).encode()).hexdigest(),
            tokenizer_hash=hashlib.sha256(
                json.dumps(
                    {n: v for n, v in pin["files"].items() if "token" in n},
                    sort_keys=True,
                ).encode()
            ).hexdigest(),
            template_hash=hashlib.sha256(TEMPLATES[mid].encode()).hexdigest(),
            runtime="torch==2.13.0;transformers==5.17.0;hf-lab-worker-v1",
            quantization="bfloat16",
        )
        for mid, pin in PINS.items()
    )


@dataclass(frozen=True)
class HfConfig:
    model_id: str
    root: Path

    def payload(self) -> dict[str, Any]:
        return {"model_id": self.model_id, "root": str(self.root)}

    def validate(self) -> None:
        if self.model_id not in PINS or not self.root.is_absolute():
            raise RwkvError("invalid_model_configuration")
        for name, expected in PINS[self.model_id]["files"].items():
            path = self.root / name
            if path.is_symlink() or not path.is_file():
                raise RwkvError("artifact_missing")
            if path.stat().st_size != expected["bytes"]:
                raise RwkvError("artifact_hash_mismatch")
            with path.open("rb") as source:
                if "sha256" in expected:
                    actual = hashlib.file_digest(source, "sha256").hexdigest()
                    digest = expected["sha256"]
                else:
                    body = source.read()
                    actual = hashlib.sha1(
                        b"blob " + str(len(body)).encode() + b"\0" + body,
                        usedforsecurity=False,
                    ).hexdigest()
                    digest = expected["git_sha1"]
            if actual != digest:
                raise RwkvError("artifact_hash_mismatch")


class HfAdapter(RecurrentAdapter):
    def __init__(self, spec: ModelSpec, lease: Lease) -> None:
        from .hf_worker import worker_main

        pin = PINS[spec.model_id]
        base = Path(
            os.environ.get(
                "COOPERATION_LAB_HF_MODEL_ROOT", "/home/ubuntu/venom/models/research"
            )
        )
        self.spec, self._lease = spec, lease
        self._process = RwkvAdapter(
            HfConfig(spec.model_id, base / pin["directory"] / pin["revision"]),
            worker_target=worker_main,
        )
        self._histories = {"A": [], "B": []}
        self._round_ended = {"A": False, "B": False}

    def generate(
        self,
        participant_id: str,
        messages: Sequence[ChatMessage],
        parameters: GenerationParameters,
        deadline_s: float,
    ) -> GenerationResult:
        validate_messages(participant_id, messages)
        with self._lease.operation(kind="generation"):
            try:
                result = self._process.generate(
                    participant_id,
                    json.dumps([asdict(m) for m in messages], ensure_ascii=False),
                    RwkvParameters(**asdict(parameters)),
                    remaining(deadline_s, 360),
                )
            except RwkvError as exc:
                raise LabError(str(exc)) from exc
            if result["stop_reason"] not in {"cancelled", "deadline"}:
                self._histories[participant_id] = [
                    *messages,
                    ChatMessage("assistant", result["text"]),
                ]
            return GenerationResult(
                text=result["text"],
                raw_text=result.get("raw_text"),
                input_tokens=result["input_tokens"],
                output_tokens=result["output_tokens"],
                ttft_s=result.get("ttft_s"),
                generation_s=result["generation_s"],
                stop_reason=result["stop_reason"],
                effective_parameters=result["effective_parameters"],
                quiescent=result["quiescent"],
            )
