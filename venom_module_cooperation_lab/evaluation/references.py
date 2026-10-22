"""CPU-only independent scorers. Never serialize oracle output as observations."""

from __future__ import annotations

import heapq
import random
from collections import deque
from functools import lru_cache
from typing import Any

from ..errors import LabError
from .games import (
    MOVES,
    Action,
    Environment,
    MemoryEnvironment,
    NimEnvironment,
    SokobanEnvironment,
    TicTacToeEnvironment,
    _won,
    sokoban_transition,
    square_index,
)

REFERENCE_VERSION = "reference-v1"


def nim_sum(heaps: list[int]) -> int:
    total = 0
    for count in heaps:
        total ^= count
    return total


@lru_cache(maxsize=32768)
def _minimax(board: tuple[str, ...], turn: str, perspective: str) -> int:
    if _won(board, perspective):
        return 1
    rival = "O" if perspective == "X" else "X"
    if _won(board, rival):
        return -1
    if all(board):
        return 0
    values = []
    for index, cell in enumerate(board):
        if not cell:
            child = list(board)
            child[index] = turn
            values.append(
                _minimax(tuple(child), "O" if turn == "X" else "X", perspective)
            )
    return max(values) if turn == perspective else min(values)


def _winning_squares(board: tuple[str, ...], mark: str) -> set[int]:
    return {
        index
        for index, cell in enumerate(board)
        if not cell and _won(board[:index] + (mark,) + board[index + 1 :], mark)
    }


def _ttt_assess(
    env: TicTacToeEnvironment, player: str, action: Action
) -> dict[str, Any]:
    board = tuple(env.board)
    mark = env.symbol(player)
    rival = "O" if mark == "X" else "X"
    index = square_index(action["square"])
    child = board[:index] + (mark,) + board[index + 1 :]
    before = _minimax(board, mark, mark)
    after = _minimax(child, rival, mark)
    winning = _winning_squares(board, mark)
    threats = _winning_squares(board, rival)
    win_now = _won(child, mark)
    created_fork = not win_now and len(_winning_squares(child, mark)) >= 2
    fork_available = any(
        len(_winning_squares(board[:i] + (mark,) + board[i + 1 :], mark)) >= 2
        for i, cell in enumerate(board)
        if not cell
    )
    return {
        "value_before": before,
        "value_after": after,
        "optimal": before == after,
        "worse_move": after < before,
        "missed_win": bool(winning) and not win_now,
        "missed_block": bool(threats)
        and not win_now
        and bool(_winning_squares(child, rival)),
        "created_fork": created_fork,
        "missed_fork": fork_available and not created_fork and not win_now,
    }


SokobanState = tuple[tuple[int, int], tuple[int, int]]


@lru_cache(maxsize=2048)
def _solve(
    floor: frozenset[tuple[int, int]],
    start: SokobanState,
    goal: tuple[int, int],
    max_states: int,
) -> tuple[bool, tuple[str, ...], int | None, int]:
    """BFS minimizes steps; a separate Dijkstra search minimizes pushes."""
    queue: deque[SokobanState] = deque([start])
    parents: dict[SokobanState, tuple[SokobanState, str] | None] = {start: None}
    final: SokobanState | None = None
    while queue:
        state = queue.popleft()
        if state[1] == goal:
            final = state
            break
        for move in MOVES:
            target = sokoban_transition(floor, state[0], state[1], move)
            if target is None:
                continue
            child = target[:2]
            if child not in parents:
                if len(parents) >= max_states:
                    raise LabError("environment_solver_limit", 422)
                parents[child] = (state, move)
                queue.append(child)
    if final is None:
        return False, (), None, len(parents)
    path: list[str] = []
    cursor = final
    while parents[cursor] is not None:
        parent = parents[cursor]
        assert parent is not None
        cursor, move = parent
        path.append(move)
    path.reverse()
    # Walking costs zero pushes. Dijkstra still ties by step count, not by RNG.
    heap: list[tuple[int, int, SokobanState]] = [(0, 0, start)]
    best: dict[SokobanState, tuple[int, int]] = {start: (0, 0)}
    while heap:
        pushes, steps, state = heapq.heappop(heap)
        if best[state] != (pushes, steps):
            continue
        if state[1] == goal:
            return True, tuple(path), pushes, len(parents)
        for move in MOVES:
            target = sokoban_transition(floor, state[0], state[1], move)
            if target is None:
                continue
            child = target[:2]
            cost = (pushes + int(target[2]), steps + 1)
            if child not in best or cost < best[child]:
                if child not in best and len(best) >= max_states:
                    raise LabError("environment_solver_limit", 422)
                best[child] = cost
                heapq.heappush(heap, (*cost, child))
    raise LabError("environment_solver_inconsistent", 500)


def solve_sokoban(env: SokobanEnvironment, max_states: int = 20000) -> dict[str, Any]:
    if type(max_states) is not int or not 1 <= max_states <= 20000:
        raise LabError("invalid_solver_limit", 422)
    solved, path, pushes, states = _solve(
        env.floor,
        (env.player_position, env.box_position),
        env.goal,
        max_states,
    )
    return {
        "solvable": solved,
        "path": [{"move": move} for move in path],
        "min_moves": len(path) if solved else None,
        "min_pushes": pushes,
        "states": states,
        "reference_version": REFERENCE_VERSION,
    }


def assess(env: Environment, player: str, action: Action) -> dict[str, Any]:
    """Evaluate before mutation; no solver instruction appears in public_state."""
    # Memory accepts both orders of the same pair; normalize only for comparison.
    candidate = action
    if isinstance(env, MemoryEnvironment) and isinstance(action.get("cards"), list):
        cards = action["cards"]
        if all(type(index) is int for index in cards):
            candidate = {**action, "cards": sorted(cards)}
    legal = candidate in env.legal_actions() and player == env.current_player
    # Python equality treats booleans as integers; the strict engine remains judge.
    if isinstance(env, NimEnvironment):
        legal = legal and all(type(action.get(key)) is int for key in ("heap", "take"))
    if isinstance(env, MemoryEnvironment):
        legal = legal and all(type(index) is int for index in action.get("cards", []))
    if not legal:
        return {"legal": False, "reference_version": REFERENCE_VERSION}
    values: dict[str, Any]
    if isinstance(env, TicTacToeEnvironment):
        values = _ttt_assess(env, player, action)
    elif isinstance(env, NimEnvironment):
        after = list(env.heaps)
        after[action["heap"]] -= action["take"]
        before_sum, after_sum = nim_sum(env.heaps), nim_sum(after)
        values = {
            "winning_position_before": before_sum != 0,
            "winning_position_after": after_sum == 0,
            "lost_winning_position": before_sum != 0 and after_sum != 0,
            "optimal": before_sum == 0 or after_sum == 0,
        }
    elif isinstance(env, MemoryEnvironment):
        pairs = env.known_pairs()
        values = {
            "known_pairs_before": len(pairs),
            "missed_known_pair": bool(pairs) and candidate["cards"] not in pairs,
        }
    elif isinstance(env, SokobanEnvironment):
        before = solve_sokoban(env)
        target = env.transition(action["move"])
        assert target is not None
        solved, path, pushes, _states = _solve(env.floor, target[:2], env.goal, 20000)
        values = {
            "solvable_before": before["solvable"],
            "solvable_after": solved,
            "introduced_deadlock": before["solvable"] and not solved,
            "min_moves_before": before["min_moves"],
            "min_moves_after": len(path) if solved else None,
            "min_pushes_before": before["min_pushes"],
            "min_pushes_after": pushes,
            "optimal_step": solved and before["min_moves"] == len(path) + 1,
        }
    else:
        raise LabError("unsupported_game", 422)
    return {"legal": True, "reference_version": REFERENCE_VERSION, **values}


def reference_action(env: Environment, opponent: str, rng: random.Random) -> Action:
    """Seeded references choose legal actions using only their allowed knowledge."""
    legal = env.legal_actions()
    if not legal:
        raise LabError("reference_no_action", 422)
    if opponent == "random":
        return rng.choice(legal)
    if isinstance(env, TicTacToeEnvironment) and opponent == "optimal":
        scored = [
            (action, assess(env, env.current_player, action)["value_after"])
            for action in legal
        ]
        best = max(score for _action, score in scored)
        return rng.choice([action for action, score in scored if score == best])
    if isinstance(env, NimEnvironment) and opponent == "optimal":
        good = [
            action
            for action in legal
            if assess(env, env.current_player, action)["optimal"]
        ]
        return rng.choice(good)
    if isinstance(env, MemoryEnvironment) and opponent == "remembering":
        pairs = env.known_pairs()
        if pairs:
            return {"cards": rng.choice(pairs)}
        unmatched = [index for index in range(16) if index not in env.matched]
        unknown = [index for index in unmatched if index not in env.revealed_knowledge]
        rng.shuffle(unknown)
        known = [index for index in unmatched if index in env.revealed_knowledge]
        rng.shuffle(known)
        return {"cards": sorted((unknown + known)[:2])}
    if isinstance(env, SokobanEnvironment) and opponent == "optimal":
        path = solve_sokoban(env)["path"]
        if path:
            return path[0]
        raise LabError("reference_unsolvable", 422)
    raise LabError("unsupported_reference", 422)
