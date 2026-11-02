"""Versioned live-only measurements; frozen batch scores are never rewritten."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from .evaluation.games import TicTacToeEnvironment
from .evaluation.references import _winning_squares
from .rule_reflection import _transform, policy_actions

VERSION = "live-tactical-measurement-v1"
COUNTERS = (
    "proposals",
    "legal_moves",
    "invalid_format",
    "illegal_moves",
    "optimal_moves",
    "worse_moves",
    "win_opportunities",
    "wins_taken",
    "block_opportunities",
    "blocks_taken",
    "unavoidable_threats",
    "first_empty_choices",
    "rule_opportunities",
    "rule_followed",
    "repeated_tactical_errors",
    "solver_interventions",
)


def counters() -> dict[str, int]:
    """Initialize identical measured fields for one game and the whole series."""
    return dict.fromkeys(COUNTERS, 0)


def canonical_board(board: list[str], player: str) -> tuple[str, ...]:
    """Identify the same decision under D4 symmetry and symbol exchange."""
    own, rival = ("X", "O") if player == "A" else ("O", "X")
    normalized = [
        "X" if cell == own else "O" if cell == rival else "" for cell in board
    ]
    return min(
        tuple(_transform(normalized, "A1", rotation, mirror)[0])
        for mirror in (False, True)
        for rotation in range(4)
    )


@dataclass
class LiveGameMeasurement:
    """Bounded live-series evidence, isolated from frozen historical scoring."""

    totals: dict[str, int] = field(default_factory=counters)
    games: list[dict[str, Any]] = field(default_factory=list)
    rules: dict[str, dict[str, dict[str, dict[str, int]]]] = field(default_factory=dict)
    mistakes: set[tuple[str, str, tuple[str, ...]]] = field(default_factory=set)
    transfer: dict[str, dict[str, dict[str, int]]] = field(default_factory=dict)
    run_status: str = "running"
    failure_category: str | None = None

    def begin(self) -> None:
        """Open a measured game without resetting series evidence."""
        self.games.append(
            {"number": len(self.games) + 1, "status": "in_progress", **counters()}
        )

    def add(self, key: str, value: int = 1) -> None:
        """Increment the current game and series consistently."""
        if not self.games:
            self.begin()
        self.totals[key] += value
        self.games[-1][key] += value

    def invalid(self, code: str) -> None:
        """Count only a returned model proposal, never an infrastructure error."""
        self.add("proposals")
        self.add(
            "illegal_moves" if code == "occupied_game_square" else "invalid_format"
        )

    def observe(
        self,
        env: TicTacToeEnvironment,
        player: str,
        action: dict[str, Any],
        score: dict[str, Any],
        rule_id: str | None,
        intervention: bool,
        evidence: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Assess actual legal proposals; no oracle answer enters the model prompt."""
        self.add("proposals")
        self.add("legal_moves")
        self.add("optimal_moves", int(score["optimal"]))
        self.add("worse_moves", int(score["worse_move"]))
        self.add("first_empty_choices", int(action == env.legal_actions()[0]))
        self.add("solver_interventions", int(intervention))
        mark = env.symbol(player)
        threats = _winning_squares(tuple(env.board), "O" if mark == "X" else "X")
        wins = policy_actions(env, player, "win_now")
        self.add("unavoidable_threats", int(not wins and len(threats) > 1))
        checks: dict[str, Any] = {}
        for rule, opportunity_key, success_key in (
            ("win_now", "win_opportunities", "wins_taken"),
            ("block_win", "block_opportunities", "blocks_taken"),
        ):
            actions = policy_actions(env, player, rule)
            if not actions:
                continue
            followed = action in actions
            self.add(opportunity_key)
            self.add(success_key, int(followed))
            checks[rule] = self._record_rule(
                env, player, rule, followed, rule == rule_id, evidence
            )
        return checks

    def _record_rule(
        self,
        env: TicTacToeEnvironment,
        player: str,
        rule: str,
        followed: bool,
        reminder_present: bool,
        evidence: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Keep observed rule use separate from selection and host validation."""
        phase = "with_reminder" if reminder_present else "without_reminder"
        groups = self.rules.setdefault(player, {}).setdefault(
            rule,
            {
                "with_reminder": {"opportunities": 0, "followed": 0},
                "without_reminder": {"opportunities": 0, "followed": 0},
            },
        )
        groups[phase]["opportunities"] += 1
        groups[phase]["followed"] += int(followed)
        key = (player, rule, canonical_board(env.board, player))
        repeated = not followed and key in self.mistakes
        if not followed:
            self.mistakes.add(key)
        self.add("repeated_tactical_errors", int(repeated))
        if reminder_present:
            self.add("rule_opportunities")
            self.add("rule_followed", int(followed))
            if evidence:
                self._record_transfer(env, player, followed, evidence)
        return {
            "followed": followed,
            "reminder_present": reminder_present,
            "repeated_error": repeated,
        }

    def _record_transfer(
        self,
        env: TicTacToeEnvironment,
        player: str,
        followed: bool,
        evidence: dict[str, Any],
    ) -> None:
        """Count actual model applications relative to its private example."""
        equivalent = canonical_board(env.board, player) == canonical_board(
            evidence["board"], player
        )
        kind = "source_equivalent" if equivalent else "new_position"
        counts = self.transfer.setdefault(player, {}).setdefault(
            kind, {"opportunities": 0, "followed": 0}
        )
        counts["opportunities"] += 1
        counts["followed"] += int(followed)

    def complete(self, board: dict[str, Any]) -> None:
        """Record only referee-confirmed completed boards."""
        if self.games and board["finished"]:
            self.games[-1].update(
                status="completed", winner=board["winner"], draw=board["draw"]
            )

    def stop(self, status: str, reason: str | None) -> None:
        """Technical completion does not turn an unfinished board into a result."""
        self.run_status = status
        self.failure_category = self._failure_category(status, reason)
        if self.games and self.games[-1]["status"] == "in_progress":
            self.games[-1].update(
                status="incomplete" if status == "completed" else status,
                reason_code=reason,
            )

    @staticmethod
    def _failure_category(status: str, reason: str | None) -> str | None:
        """Classify termination without counting runtime errors as proposals."""
        if status == "cancelled":
            return "cancelled"
        if not reason:
            return None
        categories = {
            "invalid_format": "format",
            "invalid_game_move": "format",
            "empty_model_output": "format",
            "occupied_game_square": "illegal_move",
        }
        return categories.get(reason, "infrastructure")

    def public(self) -> dict[str, Any]:
        """Return a detached snapshot for journaling and UI consumption."""
        return copy.deepcopy(
            {
                "version": VERSION,
                "scope": "legal_model_proposals",
                "totals": self.totals,
                "games": self.games,
                "rules": self.rules,
                "transfer": self.transfer,
                "run_status": self.run_status,
                "failure_category": self.failure_category,
            }
        )
