"""Lazy, lease-bound model adapters. Import never downloads or loads a model."""

from .base import (
    ChatMessage,
    GenerationParameters,
    GenerationResult,
    ModelAdapter,
    ModelSpec,
)
from .registry import create_adapter, get_model_spec, list_model_specs, model_specs

__all__ = [
    "ChatMessage",
    "GenerationParameters",
    "GenerationResult",
    "ModelAdapter",
    "ModelSpec",
    "create_adapter",
    "get_model_spec",
    "list_model_specs",
    "model_specs",
]
