# Game rules provenance

## TextArena (MIT)

Upstream: https://github.com/TextArena/TextArena

Pinned source commit: `1e3160dea659971f120bf42708fafa8ea3001b81`.
Copyright (c) 2025 Leon Guertler and Bobby Cheng.
Full permission notice: [licenses/TextArena-MIT.txt](licenses/TextArena-MIT.txt).
No TextArena package, SDK, asset, dataset or room generator is installed.

The following rule transitions informed and are adapted in
`venom_module_cooperation_lab/evaluation/games.py`:

| Upstream file | Reviewed SHA256 | Adapted part / local changes |
|---|---|---|
| `textarena/envs/Nim/env.py` | `c7b1e815d0ef290e2a9a798e8c9144d751b4918cdbbb93c529bef6639536e5c6` | Heap-index/positive-removal/bounds checks, heap decrement, last removal wins. Strict dict action, bounded heaps and turns replace regex search and shared State. |
| `textarena/envs/MemoryGame/env.py` | `037967fe2393b4de7ecba5b96adb665b97b317abc9a449aac6df4e51876cf8e8` | Two copies of symbols, seeded shuffle, distinct/unmatched pair checks, reveal and matching. Local RNG, solo 4x4, flattened IDs, hidden deck isolation and revealed-only reference replace two-player scoring and global RNG. |

The pinned Sokoban file
`textarena/envs/Sokoban/env.py` (SHA256
`d5cf4cd9c78f6b1b2c600c6e0e165767f5f6ed2ec5f8aaf85c3cae5f1f7e4677`)
was reviewed for movement/pushing semantics. Its numpy board encoding, room
creation, retries, State API and implementation were not copied. The small
local tuple-based transition, fixtures and exact bounded solvers are original
module code. No gym-sokoban code or generated board assets are distributed.

TTT wraps this module's existing `TicTacToe` referee. Minimax, nim-sum,
Memory's revealed-only reference, BFS and minimum-push Dijkstra are local code.
The small Sokoban fixtures are locally authored and solver-verified.
