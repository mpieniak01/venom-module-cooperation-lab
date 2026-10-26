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


def parse_move(content: str) -> tuple[str, str]:
    """Accept explicit single-move formats, never search arbitrary prose/boards."""
    text = content.strip()
    patterns = (
        ("coordinate", r"([ABC][123])"),
        ("inline_code", r"`([ABC][123])`"),
        ("code_block", r"```(?:text)?\s*([ABC][123])\s*```"),
        ("label", r"(?:move|ruch):\s*([ABC][123])[.]?"),
        (
            "message_echo",
            r"(?:Message|Wiadomość) [a-f0-9]{32} (?:from|od) [AB]:\s*([ABC][123])",
        ),
    )
    for name, pattern in patterns:
        match = re.fullmatch(pattern, text, flags=re.IGNORECASE)
        if match:
            return match[1].upper(), name
    raise LabError("invalid_game_move", 422)


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
        square, _format = parse_move(content)
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

    def recurrent_prompt(self, participant: str, language: str | None) -> str:
        """Append a small authoritative observation; retain private RNN memory."""
        board = "\n".join(
            row + " " + " ".join(self.board[i] or "." for i in range(start, start + 3))
            for row, start in (("A", 0), ("B", 3), ("C", 6))
        )
        allowed = ", ".join(
            "ABC"[i // 3] + str(i % 3 + 1)
            for i, value in enumerate(self.board)
            if not value
        )
        symbol = "X" if participant == "A" else "O"
        instruction = (
            f"Grasz {symbol}. Aktualna plansza (kolumny 1 2 3):"
            if language == "pl"
            else f"You play {symbol}. Current board (columns 1 2 3):"
        )
        choice = (
            f"Wolne pola: {allowed}. Zwróć tylko jedną współrzędną."
            if language == "pl"
            else f"Empty squares: {allowed}. Return one coordinate only."
        )
        return instruction + "\n" + board + "\n" + choice

    def prompt(self, participant: str, language: str | None) -> str:
        rows = ["  1 2 3"] + [
            name
            + " "
            + " ".join(value or "." for value in self.board[start : start + 3])
            for name, start in (("A", 0), ("B", 3), ("C", 6))
        ]
        symbol = "X" if participant == "A" else "O"
        fields = {
            mark: ", ".join(
                "ABC"[i // 3] + str(i % 3 + 1)
                for i, value in enumerate(self.board)
                if value == mark
            )
            for mark in ("X", "O", "")
        }
        empty = "brak" if language == "pl" else "none"
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
        if language == "pl":
            constraints = (
                f"Pola zajęte przez X: {fields['X'] or empty}.\n"
                f"Pola zajęte przez O: {fields['O'] or empty}.\n"
                f"Dozwolone wolne pola: {fields[''] or empty}.\n"
                "Wybierz wyłącznie pole z listy dozwolonych. Nie wolno "
                "nadpisywać żadnego zajętego pola, także własnego znaku."
            )
        else:
            constraints = (
                f"Squares occupied by X: {fields['X'] or empty}.\n"
                f"Squares occupied by O: {fields['O'] or empty}.\n"
                f"Allowed empty squares: {fields[''] or empty}.\n"
                "Choose only from the allowed squares. Never overwrite any "
                "occupied square, including your own mark."
            )
        return instructions + "\n" + "\n".join(rows) + "\n" + constraints

    def compact_prompt(
        self, participant: str, language: str | None, reminder: str = ""
    ) -> str:
        """Live v4: one explicit state, no diagram or stale peer transcript."""
        labels = ["ABC"[i // 3] + str(i % 3 + 1) for i in range(9)]
        cells = ", ".join(
            label + "=" + (mark or "empty")
            for label, mark in zip(labels, self.board, strict=True)
        )
        allowed = ", ".join(
            label for label, mark in zip(labels, self.board, strict=True) if not mark
        )
        mark = "X" if participant == "A" else "O"
        lines = [
            f"Aktualny stan. Twój znak: {mark}."
            if language == "pl"
            else f"Current state. Your mark: {mark}.",
            "Cells: " + cells,
        ]
        if reminder:
            lines.append(
                ("Twoja reguła: " if language == "pl" else "Your rule: ") + reminder
            )
        lines.append(
            (
                "Wybierz jedno wolne pole: "
                if language == "pl"
                else "Choose ONE empty cell: "
            )
            + allowed
        )
        lines.append(
            "Odpowiedz tylko współrzędną:"
            if language == "pl"
            else "Answer with its coordinate only:"
        )
        return "\n".join(lines)
