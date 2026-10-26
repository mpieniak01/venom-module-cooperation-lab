"""Transparent per-game task/cost summaries and bounded downloadable reports."""

from __future__ import annotations

import csv
import io
import json
import math
import statistics
import time
from collections import Counter
from typing import Any


def summarize(snapshot: dict[str, Any]) -> dict[str, Any]:
    rows = snapshot["episodes"]
    output = []
    for game in sorted({r["game"] for r in rows}):
        episodes = [r for r in rows if r["game"] == game]
        decisions = [
            d for r in episodes for d in r["decisions"] if d.get("actor") == "model"
        ]
        times = sorted(
            d["seconds"]
            for d in decisions
            if isinstance(d.get("seconds"), (int, float))
        )
        token_fields = {}
        for name in ("input_tokens", "output_tokens"):
            values = [d.get("usage", {}).get(name) for d in decisions]
            token_fields[name] = (
                sum(values)
                if values and all(isinstance(v, int) for v in values)
                else None
            )
        samples: dict[str, list[int | float]] = {}
        boolean_metrics: set[str] = set()
        for d in decisions:
            for name, value in d.get("assessment", {}).items():
                if isinstance(value, (int, float)):
                    samples.setdefault(name, []).append(value)
                    if isinstance(value, bool):
                        boolean_metrics.add(name)
        metrics = {
            name: sum(values) if name in boolean_metrics else statistics.mean(values)
            for name, values in samples.items()
        }
        versus_reference = game in {"tic_tac_toe", "nim"} and (
            snapshot.get("config", {}).get("opponent") != "model"
        )
        finished = [r for r in episodes if r["status"] == "game_completed"]
        vram = [d.get("usage", {}).get("peak_vram_bytes") for d in decisions]
        output.append(
            {
                "game": game,
                "episodes": len(episodes),
                "ttt_variant": snapshot.get("config", {}).get(
                    "ttt_variant", "standard"
                ),
                "result_scope": "assisted"
                if snapshot.get("config", {}).get("ttt_variant") == "assisted"
                else "model",
                "solver_interventions": sum(
                    bool(d.get("assistance", {}).get("applied")) for d in decisions
                ),
                "model_action_samples": sum(
                    d.get("purpose", "action") == "action" and bool(d.get("valid"))
                    for d in decisions
                ),
                "wins": sum(
                    (r.get("result") or {}).get("winner") == r["player"]
                    for r in finished
                )
                if versus_reference
                else None,
                "draws": sum(
                    bool((r.get("result") or {}).get("draw")) for r in finished
                )
                if versus_reference
                else None,
                "losses": sum(
                    (r.get("result") or {}).get("winner") not in {None, r["player"]}
                    for r in finished
                )
                if versus_reference
                else None,
                "successes": sum(
                    bool((r.get("result") or {}).get("success")) for r in episodes
                ),
                "mapped_responses": sum(
                    bool(d.get("response_mapping", {}).get("mapped")) for d in decisions
                ),
                "response_mapper": snapshot.get("config", {})
                .get("request", {})
                .get("response_mode", "strict_json"),
                "model_errors": sum(
                    r["status"]
                    in {
                        "invalid_format",
                        "illegal_action",
                        "decision_timeout",
                        "action_limit",
                        "context_limit",
                    }
                    for r in episodes
                ),
                "infrastructure_errors": sum(
                    r["status"] in {"runtime_error", "environment_error"}
                    for r in episodes
                ),
                "median_decision_s": statistics.median(times) if times else None,
                "p95_decision_s": times[max(0, math.ceil(0.95 * len(times)) - 1)]
                if times
                else None,
                "decision_samples": len(times),
                "p95_method": "nearest_rank",
                "peak_vram_bytes": max(
                    (v for v in vram if isinstance(v, int)), default=None
                ),
                "metrics": metrics,
                "metric_samples": {k: len(v) for k, v in samples.items()},
                "metric_aggregation": {
                    k: "sum" if k in boolean_metrics else "mean" for k in samples
                },
                **token_fields,
            }
        )
    errors = Counter(r["reason_code"] for r in rows if r.get("reason_code"))
    return {
        "by_game": output,
        "errors": dict(errors),
        "repeats": snapshot.get("block_restarts", 0),
        "total_seconds": max(
            0, snapshot.get("ended", time.time()) - snapshot["created"]
        ),
    }


def progress(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "planned": len(rows),
        "started": sum(r.get("started_at") is not None for r in rows),
        "terminal": sum(
            r["status"] not in {"pending", "running", "skipped"} for r in rows
        ),
        "success": sum(bool((r.get("result") or {}).get("success")) for r in rows),
        "skipped": sum(r["status"] == "skipped" for r in rows),
    }


def _export_rows(snapshot: dict[str, Any]) -> list[tuple[bool, dict[str, Any]]]:
    """Preserve prior attempts without mixing them into current result metrics."""
    archived = [
        (True, row) for block in snapshot.get("attempt_history", []) for row in block
    ]
    return [*archived, *((False, row) for row in snapshot["episodes"])]


def export(snapshot: dict[str, Any], format: str) -> tuple[str, str]:
    if format == "json":
        return json.dumps(snapshot, ensure_ascii=False, indent=2), "application/json"
    if format == "jsonl":
        lines = [
            json.dumps(
                {
                    "kind": "configuration",
                    "id": snapshot["id"],
                    "config": snapshot["config"],
                    "archived": False,
                },
                ensure_ascii=False,
            )
        ]
        for archived, row in _export_rows(snapshot):
            identity = {
                "case_id": row["case_id"],
                "episode": row["episode"],
                "block_id": row["block_id"],
                "attempt": row["attempt"],
                "archived": archived,
            }
            for decision in row["decisions"]:
                lines.append(
                    json.dumps(
                        {**decision, **identity, "kind": "decision"},
                        ensure_ascii=False,
                    )
                )
            lines.append(
                json.dumps(
                    {
                        **identity,
                        "kind": "episode",
                        "value": {k: v for k, v in row.items() if k != "decisions"},
                    },
                    ensure_ascii=False,
                )
            )
        return "\n".join(lines) + "\n", "application/x-ndjson"
    if format != "csv":
        raise ValueError("invalid_export_format")
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(
        [
            "archived",
            "case_id",
            "game",
            "episode",
            "block_id",
            "player",
            "attempt",
            "status",
            "reason",
            "success",
            "winner",
            "actions",
            "result",
        ]
    )
    for archived, row in _export_rows(snapshot):
        result = row.get("result") or {}
        writer.writerow(
            [
                str(archived).lower(),
                row["case_id"],
                row["game"],
                row["episode"],
                row["block_id"],
                row["player"],
                row["attempt"],
                row["status"],
                row.get("reason_code"),
                result.get("success"),
                result.get("winner"),
                len(row["decisions"]),
                json.dumps(result, ensure_ascii=False),
            ]
        )
    return stream.getvalue(), "text/csv"
