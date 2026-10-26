"""Live-board coaching for the conversation runner, sharing the CPU scorer."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from typing import Any

from .errors import LabError
from .evaluation.actions import parse_action
from .evaluation.games import TicTacToeEnvironment
from .evaluation.references import assess
from .evaluation.strategies import strategy_action
from .tic_tac_toe import TicTacToe


@dataclass
class LiveGameStrategy:
    mode: str
    decisions: list[dict[str, Any]] = field(default_factory=list)
    notes: dict[str, str] = field(default_factory=dict)
    interventions: int = 0
    model_moves: int = 0
    worse_moves: int = 0
    missed_wins: int = 0
    accepted_notes: int = 0
    rejected_notes: int = 0

    def choose(
        self, game: TicTacToe, player: str, text: str, seed: int
    ) -> dict[str, Any]:
        action, mapping = parse_action(text, "tic_tac_toe", "mapped")
        env = TicTacToeEnvironment({"board": list(game.board)})
        score = assess(env, player, action)
        if not score["legal"]:
            raise LabError("occupied_game_square", 422)
        record: dict[str, Any] = {
            "actor": "model",
            "player": player,
            "assessment": score,
            "model_action": copy.deepcopy(action),
            "response_mapping": mapping,
        }
        variant = {
            "game_strategic": "standard",
            "game_reflection": "reflection",
            "game_assisted": "assisted",
        }[self.mode]
        record["action"] = strategy_action(
            env, player, action, score, record, variant, seed
        )
        self.decisions.append(record)
        self.model_moves += 1
        self.worse_moves += bool(score["worse_move"])
        self.missed_wins += bool(score["missed_win"])
        self.interventions += bool(record.get("assistance", {}).get("applied"))
        return copy.deepcopy(record)

    def public(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "accepted_notes": self.accepted_notes,
            "rejected_notes": self.rejected_notes,
            "model_moves": self.model_moves,
            "worse_moves": self.worse_moves,
            "missed_wins": self.missed_wins,
            "solver_interventions": self.interventions,
            "result_scope": "assisted" if self.mode == "game_assisted" else "model",
        }

    def feedback(self, game: TicTacToe, player: str) -> dict[str, Any]:
        return {
            "player": player,
            "final_state": game.public(),
            "lessons": [
                copy.deepcopy(d["lesson"])
                for d in self.decisions
                if d["player"] == player and "lesson" in d
            ][-3:],
        }

    def memory(self, player: str, language: str | None = None) -> str:
        note = self.notes.get(player)
        return (
            (
                (
                    "\nTwoja sprawdzona notatka z poprzedniej partii:\n"
                    if language == "pl"
                    else "\nYour validated private rule from a previous game:\n"
                )
                + note
            )
            if note
            else ""
        )

    def begin(self) -> None:
        self.decisions.clear()

    @staticmethod
    def encode_feedback(feedback: dict[str, Any]) -> str:
        lessons = feedback["lessons"]
        selected = next(
            (lesson for lesson in lessons if lesson["assessment"].get("missed_win")),
            lessons[0] if lessons else None,
        )
        compact = {
            "player": feedback["player"],
            "winner": feedback["final_state"]["winner"],
            "mistake": selected,
        }
        return json.dumps(compact, ensure_ascii=False, separators=(",", ":"))
