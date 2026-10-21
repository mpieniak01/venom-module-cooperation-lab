"""Immutable, versioned experiment config and effective hard budgets."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .scenarios import DialogueLanguage, get_dialogue_scenario, get_scenario

Mode = Literal["single", "self_correction", "no_contact", "dialog", "dialog_encouraged"]
MODES = ("single", "self_correction", "no_contact", "dialog", "dialog_encouraged")


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    model_id: str = Field(
        min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$"
    )
    scenario_id: str = Field(min_length=1, max_length=128)
    communication_language: DialogueLanguage | None = None
    mode: Mode = "dialog_encouraged"
    seed: int = Field(default=0, ge=0, le=2**31 - 1)
    max_turns: int = Field(default=8, ge=1, le=9)
    max_new_tokens: int = Field(default=128, ge=1, le=256)
    temperature: float = Field(default=0.8, ge=0, le=2, allow_inf_nan=False)
    top_p: float = Field(default=0.5, ge=0, le=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_scenario_limits(self) -> RunRequest:
        if self.scenario_id == "tic_tac_toe":
            if "mode" not in self.model_fields_set:
                self.mode = "dialog"
            if "max_turns" not in self.model_fields_set:
                self.max_turns = 9
            if self.mode != "dialog":
                raise ValueError("tic_tac_toe_requires_dialog")
        elif self.max_turns > 8:
            raise ValueError("scenario_turn_limit_exceeded")
        return self


@dataclass(frozen=True)
class Budgets:
    max_turns: int = 8
    max_new_tokens: int = 128
    max_context_tokens: int = 2048
    total_input_tokens: int = 16384
    total_output_tokens: int = 2048
    processing_steps: int = 18432
    wall_seconds: int = 360


@dataclass(frozen=True)
class RunConfig:
    model_json: str
    scenario_id: str
    scenario_version: str
    scenario_goal: str
    mode: str
    prompts: tuple[str, str]
    budgets: Budgets
    seed: int
    temperature: float
    top_p: float
    schema_version: int = 1
    participant_count: int = 2
    scheduler: str = "alternating-v1"
    communication_language: DialogueLanguage | None = None

    @classmethod
    def build(cls, request: RunRequest, model: dict[str, Any]) -> RunConfig:
        language = request.communication_language
        scenario = (
            get_scenario(request.scenario_id)
            if language is None
            else get_dialogue_scenario(request.scenario_id, language)
        )
        instructions = (
            "You are participant {participant}. Work on the common goal. "
            "Only your own private information is given. "
            "Return a concise answer or a message for the other participant. "
            "Optional JSON: kind(message/proposal/accept/ask/evidence/complete), "
            "recipient(A/B/all), content(string), in_reply_to(message id or null). "
            "Never include sender identity or tools."
        )
        if language == "pl":
            instructions = (
                "Jesteś uczestnikiem {participant}. Pracuj nad wspólnym celem. "
                "Otrzymujesz wyłącznie własne prywatne informacje. "
                "Porozumiewaj się po polsku, również w kolejnych odpowiedziach. "
                "Zwróć zwięzłą odpowiedź lub wiadomość do drugiego uczestnika. "
                "Opcjonalny JSON: kind(message/proposal/accept/ask/evidence/complete), "
                "recipient(A/B/all), content(tekst po polsku), "
                "in_reply_to(identyfikator wiadomości albo null). "
                "Zachowaj angielskie klucze i wartości protokołu JSON. "
                "Nigdy nie dodawaj tożsamości nadawcy ani narzędzi."
            )
        elif language == "en":
            instructions += (
                " Communicate in English, including all subsequent replies. "
                "Keep JSON protocol keys and enum values unchanged."
            )
        encouragement = (
            " You may organize your work together: ask for missing information, "
            "propose a division of work, agree or revise your plan. "
            "No role is assigned."
            if request.mode == "dialog_encouraged"
            else ""
        )
        if language == "pl" and encouragement:
            encouragement = (
                " Możecie wspólnie organizować pracę: pytać o brakujące informacje, "
                "proponować podział pracy, uzgadniać lub poprawiać plan. "
                "Nie przypisano wam ról."
            )
        goal_label = "\nCel: " if language == "pl" else "\nGoal: "
        private_label = (
            "\nPrywatne informacje: " if language == "pl" else "\nPrivate information: "
        )
        prompts = []
        for participant, private in (
            ("A", scenario.private_a),
            ("B", scenario.private_b),
        ):
            if request.mode in {"single", "self_correction"}:
                private = scenario.private_a + " " + scenario.private_b
            prompts.append(
                instructions.format(participant=participant)
                + encouragement
                + goal_label
                + scenario.goal
                + private_label
                + private
            )
        return cls(
            model_json=json.dumps(model, sort_keys=True, ensure_ascii=False),
            scenario_id=scenario.scenario_id,
            scenario_version=scenario.version,
            scenario_goal=scenario.goal,
            mode=request.mode,
            prompts=(prompts[0], prompts[1]),
            budgets=(
                Budgets(
                    max_turns=request.max_turns,
                    max_new_tokens=request.max_new_tokens,
                    total_input_tokens=9 * 2048,
                    total_output_tokens=9 * request.max_new_tokens,
                    processing_steps=9 * (2048 + request.max_new_tokens),
                )
                if request.scenario_id == "tic_tac_toe"
                else Budgets(
                    max_turns=request.max_turns, max_new_tokens=request.max_new_tokens
                )
            ),
            seed=request.seed,
            temperature=request.temperature,
            top_p=request.top_p,
            communication_language=language,
            schema_version=1 if language is None else 2,
        )

    def public(self) -> dict[str, Any]:
        result = asdict(self)
        if self.communication_language is None:
            # Preserve exact legacy v1 serialization and hashes.
            result.pop("communication_language")
        result["model"] = json.loads(result.pop("model_json"))
        result["prompts"] = list(self.prompts)
        canonical = json.dumps(result, sort_keys=True, ensure_ascii=False)
        result["config_hash"] = hashlib.sha256(canonical.encode()).hexdigest()
        return result
