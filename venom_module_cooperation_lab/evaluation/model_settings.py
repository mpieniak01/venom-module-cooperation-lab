"""Persisted operator budgets bound to the exact model identity."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..errors import LabError
from ..runner import MODEL_IDENTITY_FIELDS, OWNER
from .config import digest
from .sessions import capabilities_for


class ModelBudgets(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    max_context_tokens: int = Field(ge=128, le=8192)
    max_new_tokens: int = Field(ge=8, le=1024)
    decision_timeout_s: int = Field(ge=1, le=300)


def validate_budgets(budgets: ModelBudgets, model: dict[str, Any]) -> None:
    caps = capabilities_for(model)
    if not caps["observation_modes"]:
        raise LabError("unsupported_model_adapter", 422)
    if budgets.max_context_tokens > caps["max_context_tokens"]:
        raise LabError("unsupported_context_budget", 422)
    if budgets.max_new_tokens > caps["max_new_tokens"]:
        raise LabError("unsupported_output_budget", 422)


def _key(model: dict[str, Any]) -> str:
    return "eval-budget-" + digest(model["model_id"])[:32]


def _identity(model: dict[str, Any]) -> str:
    return digest({key: model.get(key) for key in MODEL_IDENTITY_FIELDS})


def read_budgets(store: Any, model: dict[str, Any]) -> dict[str, Any]:
    defaults = ModelBudgets(
        max_context_tokens=8192
        if model.get("provider") == "ollama" and model.get("architecture") == "gemma4"
        else 2048,
        max_new_tokens=64,
        decision_timeout_s=30,
    )
    doc = store.get_document("settings", _key(model), owner=OWNER)
    saved = False
    stale = doc is not None
    if doc and doc.get("identity") == _identity(model):
        try:
            values = ModelBudgets.model_validate(doc["budgets"])
            validate_budgets(values, model)
        except (KeyError, ValidationError, LabError):
            pass
        else:
            defaults, saved, stale = values, True, False
    return {"budgets": defaults.model_dump(), "saved": saved, "stale": stale}


def save_budgets(
    store: Any, model: dict[str, Any], budgets: ModelBudgets
) -> dict[str, Any]:
    validate_budgets(budgets, model)
    store.put_document(
        "settings",
        _key(model),
        {"identity": _identity(model), "budgets": budgets.model_dump()},
        owner=OWNER,
    )
    return read_budgets(store, model)
