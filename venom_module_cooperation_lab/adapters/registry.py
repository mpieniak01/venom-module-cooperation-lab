"""Immutable model identities; paths and endpoint belong to trusted host config."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from ..errors import LabError
from .base import Lease, ModelAdapter, ModelSpec
from .component import OVERLAY_RUNTIME
from .rwkv_process import MODEL_FILENAME, MODEL_REVISION, MODEL_SHA256, TOKENIZER_SHA256

RWKV_TEMPLATE = "System: {system}\n\nUser: {user}\n\nAssistant:"
RWKV_SPEC = ModelSpec(
    model_id="rwkv7-g1d-0.4b",
    architecture="rwkv7",
    provider="local_component",
    artifact=MODEL_FILENAME,
    revision=MODEL_REVISION,
    digest=MODEL_SHA256,
    tokenizer_hash=TOKENIZER_SHA256,
    template_hash=hashlib.sha256(RWKV_TEMPLATE.encode()).hexdigest(),
    runtime=f"rwkv==0.8.32;torch==2.13.0;cuda13.0;{OVERLAY_RUNTIME};rwkv-chat-v2",
    quantization="float16",
)
RWKV_29_SPEC = ModelSpec(
    model_id="rwkv7-g1k-2.9b",
    architecture="rwkv7",
    provider="local_component",
    artifact="rwkv7-g1k-2.9b-20260930-ctx25600.pth",
    revision=MODEL_REVISION,
    digest="d8f8ecd4af8d706f867ac8a74284f35c0e3b9f863e7b09bb4d4031480c8b28b2",
    tokenizer_hash=TOKENIZER_SHA256,
    template_hash=hashlib.sha256(RWKV_TEMPLATE.encode()).hexdigest(),
    runtime=RWKV_SPEC.runtime,
    quantization="float16",
)
RWKV_SPECS = (RWKV_SPEC, RWKV_29_SPEC)

OLLAMA_SPEC = ModelSpec(
    model_id="qwen3-4b-control",
    architecture="qwen3",
    provider="ollama",
    artifact="qwen3:4b",
    revision="359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7",
    digest="359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7",
    tokenizer_hash="bundled-in-gguf-covered-by-model-digest",
    template_hash="2d54db2b9bb29ce7db54fea63a891f5859603813c555b1f88b5e0994652897f9",
    runtime="ollama==0.40.6",
    quantization="Q4_K_M",
)


def model_specs() -> tuple[ModelSpec, ...]:
    return (*RWKV_SPECS, OLLAMA_SPEC)


def list_model_specs() -> list[ModelSpec]:
    return list(model_specs())


def get_model_spec(model_id: str) -> ModelSpec:
    for spec in model_specs():
        if spec.model_id == model_id:
            return spec
    raise LabError("model_not_allowed", 422)


def create_adapter(model_id: str, lease: Lease) -> ModelAdapter:
    if lease is None or not callable(getattr(lease, "operation", None)):
        raise LabError("runtime_lease_required")
    if model_id in {s.model_id for s in RWKV_SPECS}:
        spec = get_model_spec(model_id)
        from .rwkv import RecurrentAdapter

        root = Path(
            os.environ.get(
                "COOPERATION_LAB_RWKV_MODEL_ROOT",
                "/home/ubuntu/venom/models/research/rwkv7-g1",
            )
        )
        runtime = Path(
            os.environ.get(
                "COOPERATION_LAB_RWKV_RUNTIME_ROOT",
                "/home/ubuntu/.local/share/venom/components/cooperation-rwkv-0.8.32",
            )
        )
        if not root.is_absolute() or not runtime.is_absolute():
            raise LabError("invalid_model_configuration")
        return RecurrentAdapter(
            spec, lease, root / spec.revision / spec.artifact, runtime
        )
    if model_id == OLLAMA_SPEC.model_id:
        from .ollama import OllamaAdapter

        return OllamaAdapter(OLLAMA_SPEC, lease)
    raise LabError("model_not_allowed", 422)
