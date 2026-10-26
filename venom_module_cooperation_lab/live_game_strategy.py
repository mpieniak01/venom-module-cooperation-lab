"""Live-board coaching for the conversation runner, sharing the CPU scorer."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from typing import Any

from .errors import LabError
from .evaluation.actions import parse_action
from .evaluation.games import TicTacToeEnvironment
from .evaluation.references import _winning_squares, assess
from .evaluation.strategies import strategy_action
from .tic_tac_toe import TicTacToe


@dataclass
class LiveGameStrategy:
    mode: str
    decisions: list[dict[str, Any]] = field(default_factory=list)
    notes: dict[str, str] = field(default_factory=dict)
    note_ids: dict[str, str] = field(default_factory=dict)
    rule_opportunities: int = 0
    rule_followed: int = 0
    rule_ignored: int = 0
    interventions: int = 0
    model_moves: int = 0
    worse_moves: int = 0
    missed_wins: int = 0
    accepted_notes: int = 0
    rejected_notes: int = 0
    skipped_notes: int = 0

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
        rule_id = self.note_ids.get(player)
        if rule_id:
            from .rule_reflection import policy_actions

            actions = policy_actions(env, player, rule_id)
            applicable = bool(actions)
            followed = action in actions if applicable else None
            record["rule_application"] = {
                "rule_id": rule_id,
                "applicable": applicable,
                "followed": followed,
                "scope": "legal_model_proposal",
            }
            self.rule_opportunities += applicable
            self.rule_followed += followed is True
            self.rule_ignored += followed is False
        variant = {
            "game_strategic": "standard",
            "game_reflection": "reflection",
            "game_assisted": "assisted",
        }[self.mode]
        record["action"] = strategy_action(
            env, player, action, score, record, variant, seed
        )
        # Missing an immediate win can preserve minimax value while still being
        # a useful tactical lesson. Keep this live-v3 policy out of frozen batch v1.
        if (
            self.mode == "game_reflection"
            and "lesson" not in record
            and (score.get("missed_win") or score.get("missed_block"))
        ):
            mark = env.symbol(player)
            wins = _winning_squares(tuple(env.board), mark)
            threats = _winning_squares(tuple(env.board), "O" if mark == "X" else "X")
            targets = wins or threats
            if targets:
                index = min(targets)
                better = {"square": "ABC"[index // 3] + str(index % 3 + 1)}
                if assess(env, player, better).get("optimal"):
                    record["lesson"] = {
                        "board": list(game.board),
                        "model_action": copy.deepcopy(action),
                        "better_action": better,
                        "assessment": copy.deepcopy(score),
                    }
        self.decisions.append(record)
        self.model_moves += 1
        self.worse_moves += bool(score["worse_move"])
        self.missed_wins += bool(score["missed_win"])
        self.interventions += bool(record.get("assistance", {}).get("applied"))
        return copy.deepcopy(record)

    def public(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "rule_opportunities": self.rule_opportunities,
            "rule_followed": self.rule_followed,
            "rule_ignored": self.rule_ignored,
            "accepted_notes": self.accepted_notes,
            "rejected_notes": self.rejected_notes,
            "skipped_notes": self.skipped_notes,
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
                    "\nTwoja reguła taktyczna potwierdzona przykładem "
                    "z poprzedniej partii:\n"
                    if language == "pl"
                    else "\nYour private tactical rule supported by "
                    "a previous mistake:\n"
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
