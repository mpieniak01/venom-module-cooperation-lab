"""Bounded deterministic referee; model claims never decide the game result."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .errors import LabError

_LINES = (
    (0, 1, 2),
    (3, 4, 5),
    (6, 7, 8),
    (0, 3, 6),
    (1, 4, 7),
    (2, 5, 8),
    (0, 4, 8),
    (2, 4, 6),
)


@dataclass
class TicTacToe:
    board: list[str] = field(default_factory=lambda: [""] * 9)
    moves: int = 0
    winner: str | None = None
    last_move: str | None = None

    @property
    def finished(self) -> bool:
        return self.winner is not None or self.moves == 9

    def public(self) -> dict[str, Any]:
        return {
            "board": list(self.board),
            "moves": self.moves,
            "winner": self.winner,
            "draw": self.moves == 9 and self.winner is None,
            "finished": self.finished,
            "last_move": self.last_move,
            "next_player": None
            if self.finished
            else ("A" if self.moves % 2 == 0 else "B"),
        }

    def play(self, participant: str, content: str) -> dict[str, Any]:
        square = content.strip().upper()
        expected = "A" if self.moves % 2 == 0 else "B"
        if (
            self.finished
            or participant != expected
            or not re.fullmatch(r"[ABC][123]", square)
        ):
            raise LabError("invalid_game_move", 422)
        index = (ord(square[0]) - ord("A")) * 3 + int(square[1]) - 1
        if self.board[index]:
            raise LabError("occupied_game_square", 422)
        symbol = "X" if participant == "A" else "O"
        self.board[index] = symbol
        self.moves += 1
        self.last_move = square
        if any(all(self.board[i] == symbol for i in line) for line in _LINES):
            self.winner = participant
        return self.public()

    def prompt(self, participant: str, language: str | None) -> str:
        rows = ["  1 2 3"] + [
            name
            + " "
            + " ".join(value or "." for value in self.board[start : start + 3])
            for name, start in (("A", 0), ("B", 3), ("C", 6))
        ]
        symbol = "X" if participant == "A" else "O"
        if language == "pl":
            instructions = (
                f"Aktualna plansza. Twoja tura, grasz {symbol}. "
                "Kropka oznacza wolne pole. Wybierz jedno wolne pole. "
                "Zwróć wyłącznie jego współrzędne, np. B2, bez komentarza."
            )
        else:
            instructions = (
                f"Current board. Your turn, playing {symbol}. "
                "A dot means an empty square. Choose one empty square. "
                "Return only its coordinate, e.g. B2, without commentary."
            )
        return instructions + "\n" + "\n".join(rows)
