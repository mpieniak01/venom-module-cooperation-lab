"""Bounded public experience replay; no weight updates or host strategy."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class GameSeries:
    total: int
    remember: bool
    number: int = 1
    moves: list[str] = field(default_factory=list)
    results: list[dict[str, Any]] = field(default_factory=list)

    def begin(self, number: int) -> None:
        self.number = number
        self.moves = []

    def record(self, participant: str, coordinate: str, board: dict[str, Any]) -> None:
        self.moves.append(participant + ":" + coordinate)
        if board["finished"]:
            self.results.append(
                {
                    "number": self.number,
                    "winner": board["winner"],
                    "draw": board["draw"],
                    "moves": list(self.moves),
                }
            )

    def public(self) -> dict[str, Any]:
        return {
            "number": self.number,
            "total": self.total,
            "remember_games": self.remember,
            "results": [dict(row, moves=list(row["moves"])) for row in self.results],
        }

    def memory(self, participant: str, language: str | None) -> str:
        if not self.remember or not self.results:
            return ""
        heading = (
            f"Jesteś {participant}. Poprzednie partie tej sesji (A=X, B=O). "
            "Wykorzystaj doświadczenie do wyboru kolejnego ruchu. "
            "To zakończone partie, nie aktualna plansza."
            if language == "pl"
            else f"You are {participant}. Previous games in this session (A=X, B=O). "
            "Use this experience to choose your next move. "
            "These are finished games, not the current board."
        )
        lines = []
        for row in self.results[-3:]:
            outcome = row["winner"] or ("remis" if language == "pl" else "draw")
            lines.append(
                f"#{row['number']}: " + " ".join(row["moves"]) + f"; result={outcome}"
            )
        return heading + "\n" + "\n".join(lines)

    def outcome_memory(self, participant: str, language: str | None) -> str:
        """Keep results, never coordinates that could be mistaken for this board."""
        if not self.remember or not self.results:
            return ""
        heading = (
            f"Jesteś {participant}. Wyniki poprzednich partii; "
            "nie opisują aktualnej planszy."
            if language == "pl"
            else f"You are {participant}. Previous outcomes; "
            "these are not the current board."
        )
        return (
            heading
            + "\n"
            + "\n".join(
                f"#{row['number']}: result={row['winner'] or 'draw'}"
                for row in self.results[-3:]
            )
        )
