"""Deterministic game rules, isolated from model prompts and offline oracles.

Nim/Memory transitions adapt TextArena's MIT rules; see THIRD_PARTY_NOTICES.md.
Sokoban movement and bounded fixtures are local, without a generator dependency.
"""

from __future__ import annotations

import copy
import hashlib
import json
import random
from collections.abc import Callable
from typing import Any, NoReturn, Protocol

from ..errors import LabError
from ..tic_tac_toe import TicTacToe

Action = dict[str, Any]
MOVES = {"up": (-1, 0), "down": (1, 0), "left": (0, -1), "right": (0, 1)}
LINES = (
    (0, 1, 2),
    (3, 4, 5),
    (6, 7, 8),
    (0, 3, 6),
    (1, 4, 7),
    (2, 5, 8),
    (0, 4, 8),
    (2, 4, 6),
)


class Environment(Protocol):
    game: str
    current_player: str

    @property
    def finished(self) -> bool: ...
    def observation(self, player: str, listed: bool = True) -> dict[str, Any]: ...
    def legal_actions(self) -> list[Action]: ...
    def step(self, player: str, action: Action) -> dict[str, Any]: ...
    def result(self) -> dict[str, Any]: ...
    def public_state(self) -> dict[str, Any]: ...


def other(player: str) -> str:
    return "B" if player == "A" else "A"


def _reject() -> NoReturn:
    raise LabError("illegal_action", 422)


def _turn(env: Environment, player: str) -> None:
    if env.finished or player not in {"A", "B"} or player != env.current_player:
        _reject()


def _keys(action: Action, keys: set[str]) -> None:
    if not isinstance(action, dict) or set(action) != keys:
        _reject()


def _config_keys(config: dict[str, Any], keys: set[str]) -> None:
    if not isinstance(config, dict) or set(config) - keys:
        raise LabError("invalid_game_config", 422)


def _observe(env: Environment, player: str, listed: bool) -> dict[str, Any]:
    if player not in {"A", "B"}:
        raise LabError("invalid_game_player", 422)
    result = env.public_state()
    result["you"] = player
    if listed:
        result["legal_actions"] = env.legal_actions()
    return result


class TicTacToeEnvironment:
    game = "tic_tac_toe"

    def __init__(self, config: dict[str, Any]) -> None:
        _config_keys(config, {"board", "starting_player", "current_player"})
        self.starting_player = config.get("starting_player", "A")
        board = config.get("board", [""] * 9)
        if (
            type(self.starting_player) is not str
            or self.starting_player not in {"A", "B"}
            or not isinstance(board, list)
            or len(board) != 9
            or any(
                type(cell) is not str or cell not in {"", "X", "O"} for cell in board
            )
        ):
            raise LabError("invalid_game_config", 422)
        nx, no = board.count("X"), board.count("O")
        wins = {mark for mark in ("X", "O") if _won(tuple(board), mark)}
        if (
            nx not in {no, no + 1}
            or len(wins) > 1
            or ("X" in wins and nx != no + 1)
            or ("O" in wins and nx != no)
        ):
            raise LabError("invalid_game_config", 422)
        internal_winner = "A" if "X" in wins else "B" if "O" in wins else None
        self.referee = TicTacToe(list(board), nx + no, internal_winner)
        self.initial_moves = nx + no
        self.current_player = (
            self.starting_player if nx == no else other(self.starting_player)
        )
        if config.get("current_player", self.current_player) != self.current_player:
            raise LabError("invalid_game_config", 422)

    @property
    def finished(self) -> bool:
        return self.referee.finished

    @property
    def board(self) -> list[str]:
        return self.referee.board

    def symbol(self, player: str) -> str:
        return "X" if player == self.starting_player else "O"

    def legal_actions(self) -> list[Action]:
        if self.finished:
            return []
        return [
            {"square": square(i)} for i, value in enumerate(self.board) if not value
        ]

    def step(self, player: str, action: Action) -> dict[str, Any]:
        _turn(self, player)
        _keys(action, {"square"})
        if type(action["square"]) is not str or action not in self.legal_actions():
            _reject()
        internal = "A" if player == self.starting_player else "B"
        self.referee.play(internal, action["square"])
        self.current_player = other(player)
        return self.public_state()

    def result(self) -> dict[str, Any]:
        winner = self.referee.winner
        if winner is not None:
            winner = (
                self.starting_player if winner == "A" else other(self.starting_player)
            )
        return {
            "success": self.finished,
            "winner": winner,
            "draw": self.finished and winner is None,
            "actions": self.referee.moves - self.initial_moves,
            "board_moves": self.referee.moves,
        }

    def public_state(self) -> dict[str, Any]:
        return {
            "game": self.game,
            "board": list(self.board),
            "current_player": None if self.finished else self.current_player,
            "symbols": {self.starting_player: "X", other(self.starting_player): "O"},
            "finished": self.finished,
            "result": self.result(),
            "rules": (
                "Rows A-C, columns 1-3. X starts. Place on one empty square; "
                "three in a line wins."
            ),
            "action_schema": {"square": "B2"},
        }

    def observation(self, player: str, listed: bool = True) -> dict[str, Any]:
        result = _observe(self, player, listed)
        result["your_symbol"] = self.symbol(player)
        return result


def square(index: int) -> str:
    return "ABC"[index // 3] + str(index % 3 + 1)


def square_index(value: str) -> int:
    return (ord(value[0]) - ord("A")) * 3 + int(value[1]) - 1


def _won(board: tuple[str, ...], mark: str) -> bool:
    return any(all(board[i] == mark for i in line) for line in LINES)


class NimEnvironment:
    game = "nim"

    def __init__(self, config: dict[str, Any]) -> None:
        _config_keys(config, {"heaps", "starting_player"})
        heaps = config.get("heaps", [3, 4, 5])
        self.current_player = config.get("starting_player", "A")
        if (
            not isinstance(heaps, list)
            or not 1 <= len(heaps) <= 8
            or any(type(value) is not int or not 0 <= value <= 32 for value in heaps)
            or not 1 <= sum(heaps) <= 128
            or type(self.current_player) is not str
            or self.current_player not in {"A", "B"}
        ):
            raise LabError("invalid_game_config", 422)
        self.heaps = list(heaps)
        self.winner: str | None = None
        self.actions = 0

    @property
    def finished(self) -> bool:
        return self.winner is not None

    def legal_actions(self) -> list[Action]:
        if self.finished:
            return []
        return [
            {"heap": i, "take": n}
            for i, size in enumerate(self.heaps)
            for n in range(1, size + 1)
        ]

    def step(self, player: str, action: Action) -> dict[str, Any]:
        _turn(self, player)
        _keys(action, {"heap", "take"})
        # bool is deliberately not an integer action, despite Python's subclassing.
        if (
            any(type(action[k]) is not int for k in ("heap", "take"))
            or action not in self.legal_actions()
        ):
            _reject()
        self.heaps[action["heap"]] -= action["take"]
        self.actions += 1
        if not any(self.heaps):
            self.winner = player
        self.current_player = other(player)
        return self.public_state()

    def result(self) -> dict[str, Any]:
        return {
            "success": self.finished,
            "winner": self.winner,
            "draw": False,
            "actions": self.actions,
        }

    def public_state(self) -> dict[str, Any]:
        return {
            "game": self.game,
            "heaps": list(self.heaps),
            "current_player": None if self.finished else self.current_player,
            "finished": self.finished,
            "result": self.result(),
            "rules": (
                "Remove a positive number of stones from exactly one heap. "
                "Heap indices start at 0. Taking the last stone wins."
            ),
            "action_schema": {"heap": 0, "take": 1},
        }

    def observation(self, player: str, listed: bool = True) -> dict[str, Any]:
        return _observe(self, player, listed)


class MemoryEnvironment:
    game = "memory"
    current_player = "A"

    def __init__(self, config: dict[str, Any], seed: int) -> None:
        _config_keys(config, {"size"})
        if type(config.get("size", 4)) is not int or config.get("size", 4) != 4:
            raise LabError("invalid_game_config", 422)
        self._cards = [chr(65 + i) for i in range(8)] * 2
        # Seeded public fixture shuffle; never used for security-sensitive randomness.
        random.Random(seed).shuffle(self._cards)  # NOSONAR
        self.matched: set[int] = set()
        self.revealed_knowledge: dict[int, str] = {}
        self.last_reveal: list[dict[str, Any]] = []
        self.attempts = 0
        self.known_pairs_missed = 0
        self.deck_id = hashlib.sha256(f"memory4-v1:{seed}".encode()).hexdigest()[:16]

    @property
    def finished(self) -> bool:
        return len(self.matched) == 16

    def legal_actions(self) -> list[Action]:
        remaining = [i for i in range(16) if i not in self.matched]
        return [
            {"cards": [left, right]}
            for pos, left in enumerate(remaining)
            for right in remaining[pos + 1 :]
        ]

    def known_pairs(self) -> list[list[int]]:
        """Only evidence previously revealed to the player, never the hidden deck."""
        groups: dict[str, list[int]] = {}
        for index, value in self.revealed_knowledge.items():
            if index not in self.matched:
                groups.setdefault(value, []).append(index)
        return [sorted(indices) for indices in groups.values() if len(indices) == 2]

    def step(self, player: str, action: Action) -> dict[str, Any]:
        _turn(self, player)
        _keys(action, {"cards"})
        cards = action["cards"]
        if (
            not isinstance(cards, list)
            or len(cards) != 2
            or any(type(index) is not int or not 0 <= index < 16 for index in cards)
            or cards[0] == cards[1]
            or any(index in self.matched for index in cards)
        ):
            _reject()
        if self.known_pairs() and sorted(cards) not in self.known_pairs():
            self.known_pairs_missed += 1
        self.attempts += 1
        self.last_reveal = [{"card": i, "value": self._cards[i]} for i in cards]
        self.revealed_knowledge.update({i: self._cards[i] for i in cards})
        if self._cards[cards[0]] == self._cards[cards[1]]:
            self.matched.update(cards)
        return self.public_state()

    def result(self) -> dict[str, Any]:
        return {
            "success": self.finished,
            "winner": "A" if self.finished else None,
            "draw": False,
            "actions": self.attempts,
            "attempts": self.attempts,
            "reveals": 2 * self.attempts,
            "pairs_found": len(self.matched) // 2,
            "known_pairs_missed": self.known_pairs_missed,
        }

    def public_state(self) -> dict[str, Any]:
        return {
            "game": self.game,
            "size": 4,
            "deck_id": self.deck_id,
            "board": [self._cards[i] if i in self.matched else None for i in range(16)],
            "matched": sorted(self.matched),
            "last_reveal": copy.deepcopy(self.last_reveal),
            "current_player": None if self.finished else "A",
            "finished": self.finished,
            "result": {
                key: value
                for key, value in self.result().items()
                if key != "known_pairs_missed"
            },
            "rules": (
                "Solo 4x4 matching pairs. Cards 0-15, row-major. Choose two "
                "different unmatched cards together. A mismatch is hidden again; "
                "remember earlier reveals. Match all eight pairs."
            ),
            "action_schema": {"cards": [0, 5]},
        }

    def observation(self, player: str, listed: bool = True) -> dict[str, Any]:
        if player != "A":
            raise LabError("invalid_game_player", 422)
        return _observe(self, player, listed)


class SokobanEnvironment:
    game = "sokoban"
    current_player = "A"

    def __init__(self, config: dict[str, Any]) -> None:
        _config_keys(config, {"board"})
        rows = config.get("board", ["#####", "#@$.#", "#####"])
        if (
            not isinstance(rows, list)
            or not 3 <= len(rows) <= 8
            or any(type(row) is not str for row in rows)
            or not 3 <= len(rows[0]) <= 8
            or any(len(row) != len(rows[0]) for row in rows)
            or any(char not in "# .$@*+" for row in rows for char in row)
        ):
            raise LabError("invalid_game_config", 422)
        self.height, self.width = len(rows), len(rows[0])
        self.floor = frozenset(
            (r, c)
            for r, row in enumerate(rows)
            for c, char in enumerate(row)
            if char != "#"
        )
        players = [
            (r, c)
            for r, row in enumerate(rows)
            for c, char in enumerate(row)
            if char in "@+"
        ]
        boxes = [
            (r, c)
            for r, row in enumerate(rows)
            for c, char in enumerate(row)
            if char in "$*"
        ]
        goals = [
            (r, c)
            for r, row in enumerate(rows)
            for c, char in enumerate(row)
            if char in ".*+"
        ]
        if len(players) != 1 or len(boxes) != 1 or len(goals) != 1:
            raise LabError("invalid_game_config", 422)
        self.player_position, self.box_position, self.goal = (
            players[0],
            boxes[0],
            goals[0],
        )
        self.actions, self.pushes = 0, 0
        self.deadlock = False

    @property
    def finished(self) -> bool:
        return self.box_position == self.goal or self.deadlock

    def transition(
        self, move: str
    ) -> tuple[tuple[int, int], tuple[int, int], bool] | None:
        return sokoban_transition(
            self.floor, self.player_position, self.box_position, move
        )

    def legal_actions(self) -> list[Action]:
        if self.finished:
            return []
        return [{"move": move} for move in MOVES if self.transition(move) is not None]

    def step(self, player: str, action: Action) -> dict[str, Any]:
        _turn(self, player)
        _keys(action, {"move"})
        if type(action["move"]) is not str or action["move"] not in MOVES:
            _reject()
        target = self.transition(action["move"])
        if target is None:
            _reject()
        self.player_position, self.box_position, pushed = target
        self.actions += 1
        self.pushes += int(pushed)
        if pushed and self.box_position != self.goal:
            # Reachability is exact for this bounded one-box environment.
            from .references import solve_sokoban

            self.deadlock = not solve_sokoban(self)["solvable"]
        return self.public_state()

    def result(self) -> dict[str, Any]:
        success = self.box_position == self.goal
        return {
            "success": success,
            "winner": "A" if success else None,
            "draw": False,
            "actions": self.actions,
            "moves": self.actions,
            "pushes": self.pushes,
            "deadlock": self.deadlock,
        }

    def public_state(self) -> dict[str, Any]:
        board = [
            [" " if (r, c) in self.floor else "#" for c in range(self.width)]
            for r in range(self.height)
        ]
        board[self.goal[0]][self.goal[1]] = "."
        board[self.box_position[0]][self.box_position[1]] = (
            "*" if self.box_position == self.goal else "$"
        )
        board[self.player_position[0]][self.player_position[1]] = (
            "+" if self.player_position == self.goal else "@"
        )
        return {
            "game": self.game,
            "board": ["".join(row) for row in board],
            "current_player": None if self.finished else "A",
            "finished": self.finished,
            "result": self.result(),
            "rules": (
                "Solo Sokoban. # wall, @ player, $ box, . target, "
                "* box on target, + player on target. Move up/down/left/right, "
                "push one box into free floor; no pulling. "
                "Place the box on the target."
            ),
            "action_schema": {"move": "up"},
        }

    def observation(self, player: str, listed: bool = True) -> dict[str, Any]:
        if player != "A":
            raise LabError("invalid_game_player", 422)
        return _observe(self, player, listed)


def sokoban_transition(
    floor: frozenset[tuple[int, int]],
    player: tuple[int, int],
    box: tuple[int, int],
    move: str,
) -> tuple[tuple[int, int], tuple[int, int], bool] | None:
    if move not in MOVES:
        return None
    dr, dc = MOVES[move]
    target = (player[0] + dr, player[1] + dc)
    if target not in floor:
        return None
    if target != box:
        return target, box, False
    box_target = (box[0] + dr, box[1] + dc)
    if box_target not in floor:
        return None
    return target, box_target, True


def make_environment(game: str, config: dict[str, Any], seed: int) -> Environment:
    if type(seed) is not int or not 0 <= seed <= 2**32 - 1:
        raise LabError("invalid_game_config", 422)
    factories: dict[str, Callable[[], Environment]] = {
        "tic_tac_toe": lambda: TicTacToeEnvironment(config),
        "nim": lambda: NimEnvironment(config),
        "memory": lambda: MemoryEnvironment(config, seed),
        "sokoban": lambda: SokobanEnvironment(config),
    }
    if game not in factories:
        raise LabError("unsupported_game", 422)
    return factories[game]()


def state_digest(env: Environment) -> str:
    """Hash only public state, useful for deterministic journal replay checks."""
    encoded = json.dumps(env.public_state(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()
