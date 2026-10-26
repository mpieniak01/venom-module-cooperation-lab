"""Immutable, versioned experiment config and effective hard budgets."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .errors import LabError
from .model_limits import MAX_REQUESTED_TOKENS, applied_output_tokens
from .scenarios import DialogueLanguage, get_dialogue_scenario, get_scenario

Mode = Literal[
    "single",
    "self_correction",
    "no_contact",
    "dialog",
    "dialog_encouraged",
    "operator_chat",
    "operator_relay",
    "operator_review",
    "game_competitive",
    "game_strategic",
    "game_reflection",
    "game_assisted",
]
MODES = (
    "single",
    "self_correction",
    "no_contact",
    "dialog",
    "dialog_encouraged",
    "operator_chat",
    "operator_relay",
    "operator_review",
    "game_competitive",
    "game_strategic",
    "game_reflection",
    "game_assisted",
)


STRATEGIC_MODES = {"game_strategic", "game_reflection", "game_assisted"}

OPERATOR_MODES = {"operator_chat", "operator_relay", "operator_review"}


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
    game_count: int = Field(default=1, ge=1, le=10)
    remember_games: bool = True
    max_new_tokens: int = Field(default=128, ge=1, le=MAX_REQUESTED_TOKENS)
    num_steps: Literal[8, 16, 32, 64] = 8
    reflection_max_new_tokens: int = Field(default=128, ge=32, le=256)
    temperature: float = Field(default=0.8, ge=0, le=2, allow_inf_nan=False)
    top_p: float = Field(default=0.5, ge=0, le=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_scenario_limits(self) -> RunRequest:
        if self.mode == "operator_review" and "max_turns" not in self.model_fields_set:
            self.max_turns = 6
        if self.scenario_id == "tic_tac_toe":
            if "mode" not in self.model_fields_set:
                self.mode = "dialog"
            if "max_turns" not in self.model_fields_set:
                self.max_turns = 9
            if self.mode not in {"dialog", "game_competitive"} | STRATEGIC_MODES:
                raise ValueError("tic_tac_toe_requires_dialog")
        elif self.mode in {"game_competitive"} | STRATEGIC_MODES:
            raise ValueError("competitive_mode_requires_game")
        elif self.max_turns > 8:
            raise ValueError("scenario_turn_limit_exceeded")
        if self.mode == "operator_review":
            if self.scenario_id != "peer_review" or self.max_turns not in {3, 6}:
                raise ValueError("peer_review_requires_complete_rounds")
        elif self.scenario_id == "peer_review":
            raise ValueError("peer_review_requires_operator_review")
        else:
            if (self.mode in OPERATOR_MODES) != (
                self.scenario_id == "operator_conversation"
            ):
                raise ValueError("operator_mode_requires_operator_scenario")
            if self.mode in OPERATOR_MODES and (
                self.max_turns < 2 or self.max_turns % 2
            ):
                raise ValueError("operator_chat_requires_pairs")
        if self.scenario_id != "tic_tac_toe" and (
            self.game_count != 1 or not self.remember_games
        ):
            raise ValueError("game_series_requires_game")
        if self.game_count > 1 and self.max_turns != 9:
            raise ValueError("game_series_requires_nine_moves")
        if self.mode in STRATEGIC_MODES and self.max_turns != 9:
            raise ValueError("game_series_requires_nine_moves")
        if self.mode == "game_reflection":
            if "game_count" not in self.model_fields_set:
                self.game_count = 3
            if self.game_count < 2 or not self.remember_games:
                raise ValueError("game_reflection_requires_memory")
        elif self.reflection_max_new_tokens != 128:
            raise ValueError("reflection_tokens_require_reflection_mode")
        if self.game_count == 1:
            self.remember_games = True  # No cross-game memory exists for one game.
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
    game_count: int = 1
    remember_games: bool = True
    requested_max_new_tokens: int | None = None
    reflection_max_new_tokens: int | None = None
    num_steps: int | None = None

    @property
    def game_language(self) -> DialogueLanguage | None:
        architecture = json.loads(self.model_json).get("architecture")
        return (
            "en"
            if self.mode in STRATEGIC_MODES
            and architecture in {"hrm_text", "huginn_raven"}
            else self.communication_language
        )

    @classmethod
    def build(cls, request: RunRequest, model: dict[str, Any]) -> RunConfig:
        requested_tokens = request.max_new_tokens
        request = request.model_copy(
            update={"max_new_tokens": applied_output_tokens(requested_tokens, model)}
        )
        language = request.communication_language
        if request.num_steps != 8 and (
            request.mode not in STRATEGIC_MODES
            or model.get("architecture") != "huginn_raven"
        ):
            raise LabError("unsupported_compute_steps", 422)
        if request.mode in STRATEGIC_MODES and model.get("architecture") in {
            "hrm_text",
            "huginn_raven",
        }:
            language = "en"
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
        if request.mode == "operator_chat":
            instructions += (
                " Operator jest trzecim uczestnikiem. Odpowiadaj na jego nowe "
                "wiadomości, uwzględniając kontekst rozmowy. "
                "Możesz kierować JSON do recipient=operator."
                if language == "pl"
                else " The operator is a third participant. Answer their new messages "
                "using the conversation context. JSON recipient=operator is allowed."
            )
        if request.mode == "operator_review":
            instructions = (
                "Uczestnik {participant}. Pisz po polsku, zwięzłym zwykłym tekstem, "
                "bez JSON i toku myślenia. Wykonuj tylko etap wskazany przez hosta."
                if language == "pl"
                else "Participant {participant}. Write concise plain English, without "
                "JSON or a thinking transcript. Perform only the phase set by the host."
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
            if request.scenario_id == "tic_tac_toe":
                symbol = "X" if participant == "A" else "O"
                prompts.append(
                    f"Jesteś {participant}, grasz {symbol} w kółko i krzyżyk 3x3. "
                    "A/X zaczyna, B/O odpowiada. Trzy znaki w linii wygrywają. "
                    "Używaj aktualnej planszy od hosta. Wybierz wolne pole. "
                    "Odpowiedz tylko współrzędnymi, np. B2, bez JSON i komentarza."
                    if language == "pl"
                    else f"You are {participant}, playing {symbol} in 3x3 tic-tac-toe. "
                    "A/X starts; B/O follows. Three marks in a line win. "
                    "Use the current host board. Choose an empty square. "
                    "Reply only with its coordinate, e.g. B2, no JSON or commentary."
                )
                if request.mode in {"game_competitive"} | STRATEGIC_MODES:
                    prompts[-1] += (
                        " Twoim celem jest wygrać z przeciwnikiem. Sprawdzaj własne "
                        "możliwości natychmiastowej wygranej i zagrożenia przeciwnika. "
                        "Jeśli nie możesz wygrać od razu, blokuj jego wygraną. "
                        "Planuj kolejne ruchy; gdy wygrana jest niemożliwa, "
                        "dąż do remisu."
                        if language == "pl"
                        else " Your goal is to beat your opponent. Check your "
                        "immediate "
                        "winning opportunities and the opponent's threats. "
                        "If you cannot "
                        "win immediately, block their win. Plan ahead; when a win is "
                        "impossible, aim for a draw."
                    )
                if request.mode in STRATEGIC_MODES:
                    prompts[-1] += (
                        " Masz samodzielnie wybrać ruch; nie zakładaj, że host zapewni "
                        "jego legalność. Wykorzystuj własne wnioski z poprzednich gier."
                        if language == "pl"
                        else " Choose the move yourself; do not assume the host "
                        "ensures "
                        "legality. Apply your own lessons from previous games."
                    )
                if (
                    request.mode in STRATEGIC_MODES
                    and model.get("architecture") == "hrm_text"
                ):
                    prompts[-1] += (
                        "\nExamples of the single-coordinate answer format "
                        "(not the current position):"
                        "\nTask: Select one of A1, B2. Answer: A1"
                        "\nTask: Select one of B1, C3. Answer: C3"
                        "\nNow solve only the current host board. Answer:"
                    )
                continue
            if request.mode in {"single", "self_correction"}:
                private = scenario.private_a + " " + scenario.private_b
            if request.mode == "operator_review":
                prompts.append(instructions.format(participant=participant))
                continue
            operator_role = ""
            if request.mode == "operator_relay":
                if language == "pl":
                    operator_role = (
                        " Głuchy telefon: przeczytaj wpis operatora i opowiedz go "
                        "wiernie modelowi B. B nie widzi oryginału."
                        if participant == "A"
                        else " Głuchy telefon: otrzymasz wyłącznie przekaz modelu A, "
                        "nie oryginał operatora. Opowiedz operatorowi to, co "
                        "przekazał A; nie zgaduj brakującego oryginału."
                    )
                else:
                    operator_role = (
                        " Telephone game: faithfully retell the operator message "
                        "to B. B cannot see the original."
                        if participant == "A"
                        else " Telephone game: you receive only A's retelling, never "
                        "the operator original. Retell A's account to the operator; "
                        "do not guess the missing original."
                    )
            prompts.append(
                instructions.format(participant=participant)
                + operator_role
                + encouragement
                + goal_label
                + scenario.goal
                + private_label
                + private
            )
        note_calls = (
            2 * (request.game_count - 1) if request.mode == "game_reflection" else 0
        )
        return cls(
            requested_max_new_tokens=requested_tokens
            if requested_tokens != request.max_new_tokens
            else None,
            num_steps=request.num_steps
            if request.mode in STRATEGIC_MODES
            and model.get("architecture") == "huginn_raven"
            else None,
            reflection_max_new_tokens=request.reflection_max_new_tokens
            if request.mode == "game_reflection"
            else None,
            model_json=json.dumps(model, sort_keys=True, ensure_ascii=False),
            scenario_id=scenario.scenario_id,
            scenario_version=(
                scenario.version + "-board-context-5"
                if request.scenario_id == "tic_tac_toe"
                else scenario.version
            ),
            scenario_goal=scenario.goal,
            mode=request.mode,
            prompts=(prompts[0], prompts[1]),
            budgets=(
                Budgets(
                    max_turns=request.max_turns,
                    max_new_tokens=request.max_new_tokens,
                    total_input_tokens=(9 * request.game_count + note_calls) * 2048,
                    total_output_tokens=9 * request.game_count * request.max_new_tokens
                    + note_calls * request.reflection_max_new_tokens,
                    processing_steps=9
                    * request.game_count
                    * (2048 + request.max_new_tokens)
                    + note_calls * (2048 + request.reflection_max_new_tokens),
                    wall_seconds=min(1800, 360 * request.game_count),
                )
                if request.scenario_id == "tic_tac_toe"
                else Budgets(
                    max_turns=request.max_turns,
                    max_new_tokens=request.max_new_tokens,
                    total_output_tokens=max(
                        2048, request.max_turns * request.max_new_tokens
                    ),
                    processing_steps=max(
                        18432, request.max_turns * (2048 + request.max_new_tokens)
                    ),
                )
            ),
            seed=request.seed,
            temperature=request.temperature,
            top_p=request.top_p,
            communication_language=request.communication_language,
            game_count=request.game_count,
            remember_games=request.remember_games,
            schema_version=3
            if request.mode in OPERATOR_MODES or request.scenario_id == "tic_tac_toe"
            else (1 if language is None else 2),
            participant_count=3 if request.mode in OPERATOR_MODES else 2,
            scheduler="board-state-v4"
            if request.scenario_id == "tic_tac_toe"
            else (
                "author-review-revise-v1"
                if request.mode == "operator_review"
                else "operator-relay-v1"
                if request.mode == "operator_relay"
                else "operator-rounds-v1"
            )
            if request.mode in OPERATOR_MODES
            else "alternating-v1",
        )

    def public(self) -> dict[str, Any]:
        result = asdict(self)
        if self.num_steps is None:
            result.pop("num_steps")
        if self.mode in STRATEGIC_MODES:
            result["model_language"] = self.game_language
            result["model_task_profile"] = "live-task-v4"
            result["observation_profile"] = (
                "board-and-peer-with-reminder-v1"
                if json.loads(self.model_json).get("architecture") == "hrm_text"
                else "explicit-cells-v1"
            )
        if self.reflection_max_new_tokens is None:
            result.pop("reflection_max_new_tokens")
        if self.requested_max_new_tokens is None:
            result.pop("requested_max_new_tokens")
        if self.game_count == 1:
            result.pop("game_count")
            result.pop("remember_games")
        else:
            result["schema_version"] = 4
            result["scheduler"] = "board-series-memory-v1"
            result["scenario_version"] += "-series-1"
        if self.mode in STRATEGIC_MODES:
            result["schema_version"] = 8
            result["scheduler"] = "live-game-strategy-v4"
            result["scenario_version"] += "-live-strategy-4"
            result["strategy_version"] = "ttt-coaching-v4"
            result["memory_policy"] = "outcomes-and-decision-reminder-v4"
            if self.mode == "game_reflection":
                result["reflection_contract"] = "model-selects-host-tactical-catalog-v1"
                result["reflection_mapping"] = "rule-choice-map-v1"
                result["reflection_schedule"] = "between-games-only"
        if self.communication_language is None:
            # Preserve exact legacy v1 serialization and hashes.
            result.pop("communication_language")
        result["model"] = json.loads(result.pop("model_json"))
        result["prompts"] = list(self.prompts)
        canonical = json.dumps(result, sort_keys=True, ensure_ascii=False)
        result["config_hash"] = hashlib.sha256(canonical.encode()).hexdigest()
        return result
