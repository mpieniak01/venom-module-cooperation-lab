from __future__ import annotations

import csv
import io
import json

import pytest

from venom_module_cooperation_lab.evaluation.reports import export, progress, summarize


def decision(seconds=1.0, *, actor="model", usage=None, assessment=None):
    return {
        "player": "A",
        "actor": actor,
        "observation": {"visible": [0, 1]},
        "response": '{"cards":[0,1]}',
        "action": {"cards": [0, 1]},
        "valid": True,
        "seconds": seconds,
        "usage": {"input_tokens": 10, "output_tokens": 2, "peak_vram_bytes": 100}
        if usage is None
        else usage,
        "assessment": {"missed_win": False} if assessment is None else assessment,
    }


def episode(status="game_completed", *, game="nim", decisions=None, success=True):
    return {
        "case_id": game + "-case",
        "game": game,
        "episode": 1,
        "player": "A",
        "block_id": "block-A",
        "attempt": 1,
        "status": status,
        "reason_code": None if status == "game_completed" else status,
        "result": {"success": success, "winner": "A" if success else "B"},
        "started_at": 1,
        "decisions": [decision()] if decisions is None else decisions,
    }


def snapshot(rows):
    return {
        "id": "series1",
        "config": {"protocol": "game-eval-v2", "episode_memory": "fresh"},
        "created": 10.0,
        "ended": 20.0,
        "block_restarts": 2,
        "episodes": rows,
    }


def test_game_reports_keep_model_errors_in_denominator_and_infrastructure_separate():
    rows = [
        episode(),
        episode("invalid_format", success=False),
        episode("illegal_action", success=False),
        episode("decision_timeout", success=False),
        episode("action_limit", success=False),
        episode("context_limit", success=False),
        episode("runtime_error", success=False),
        episode("environment_error", success=False),
        {**episode("skipped", success=False), "started_at": None},
        {**episode("pending", success=False), "started_at": None},
    ]
    report = summarize(snapshot(rows))
    nim = report["by_game"][0]
    assert nim["episodes"] == 10
    assert nim["successes"] == 1
    assert nim["model_errors"] == 5
    assert nim["infrastructure_errors"] == 2
    assert report["errors"]["illegal_action"] == 1
    assert report["repeats"] == 2
    assert report["total_seconds"] == 10.0
    assert progress(rows) == {
        "planned": 10,
        "started": 8,
        "terminal": 8,
        "success": 1,
        "skipped": 1,
    }


def test_game_reports_unknown_cost_is_null_and_zero_is_a_measurement():
    unknown = episode(
        game="memory", decisions=[decision(None, usage={"input_tokens": None})]
    )
    known_zero = episode(
        game="sokoban",
        decisions=[
            decision(
                0.0, usage={"input_tokens": 0, "output_tokens": 0, "peak_vram_bytes": 0}
            )
        ],
    )
    none = episode(game="tic_tac_toe", decisions=[])
    rows = {
        row["game"]: row
        for row in summarize(snapshot([unknown, known_zero, none]))["by_game"]
    }
    for key in (
        "input_tokens",
        "output_tokens",
        "median_decision_s",
        "p95_decision_s",
        "peak_vram_bytes",
    ):
        assert rows["memory"][key] is None
        assert rows["tic_tac_toe"][key] is None
        assert rows["sokoban"][key] == 0
    assert rows["tic_tac_toe"]["decision_samples"] == 0


def test_game_reports_percentiles_peak_vram_and_bots_do_not_pollute_model_cost():
    decisions = [decision(float(number)) for number in range(1, 21)]
    decisions += [
        decision(
            999.0,
            actor="reference",
            usage={"input_tokens": 999, "output_tokens": 999, "peak_vram_bytes": 999},
        )
    ]
    decisions[1]["usage"]["peak_vram_bytes"] = 200
    row = summarize(snapshot([episode(decisions=decisions)]))["by_game"][0]
    assert row["decision_samples"] == 20
    assert row["p95_method"] == "nearest_rank"
    assert row["median_decision_s"] == 10.5
    assert row["p95_decision_s"] == 19.0
    assert row["input_tokens"] == 200
    assert row["output_tokens"] == 40
    assert row["peak_vram_bytes"] == 200
    missing = [decision(), decision(usage={"input_tokens": None, "output_tokens": 0})]
    partial = summarize(snapshot([episode(decisions=missing)]))["by_game"][0]
    assert partial["input_tokens"] is None
    assert partial["output_tokens"] == 2


def test_game_reports_quality_boolean_counters_numeric_means_and_samples():
    rows = [
        episode(
            decisions=[
                decision(
                    assessment={
                        "missed_win": True,
                        "value_before": 1,
                        "worse_move": True,
                    }
                ),
                decision(
                    assessment={
                        "missed_win": False,
                        "value_before": -1,
                        "worse_move": True,
                    }
                ),
            ]
        ),
        episode(
            decisions=[
                decision(
                    assessment={
                        "missed_win": True,
                        "value_before": None,
                        "worse_move": False,
                    }
                )
            ]
        ),
    ]
    row = summarize(snapshot(rows))["by_game"][0]
    assert row["metrics"]["missed_win"] == 2
    assert row["metrics"]["worse_move"] == 2
    assert row["metrics"]["value_before"] == 0
    assert row["metric_samples"]["value_before"] == 2
    assert row["metric_samples"]["missed_win"] == 3
    assert row["metric_aggregation"]["missed_win"] == "sum"
    assert row["metric_aggregation"]["value_before"] == "mean"


def test_game_report_exports_preserve_unicode_decisions_and_result_without_new_calls():
    row = episode()
    row["decisions"][0]["response"] = "Żółta karta, <script>literal</script>"
    data = snapshot([row])
    content, mime = export(data, "json")
    assert mime == "application/json"
    assert json.loads(content) == data
    content, mime = export(data, "jsonl")
    assert mime == "application/x-ndjson"
    lines = [json.loads(line) for line in content.splitlines()]
    assert [line["kind"] for line in lines] == ["configuration", "decision", "episode"]
    assert lines[1]["response"] == "Żółta karta, <script>literal</script>"
    assert lines[2]["value"]["result"] == row["result"]
    assert "decisions" not in lines[2]["value"]
    content, mime = export(data, "csv")
    assert mime == "text/csv"
    records = list(csv.DictReader(io.StringIO(content)))
    assert records[0]["case_id"] == row["case_id"]
    assert records[0]["actions"] == "1"
    assert json.loads(records[0]["result"]) == row["result"]
    with pytest.raises(ValueError, match="invalid_export_format"):
        export(data, "html")


def test_game_reports_wins_draws_losses_are_model_relative_and_solo_unknown():
    win = episode()
    loss = episode(success=False)
    draw = episode(success=False)
    draw["result"].update(winner=None, draw=True)
    as_b = episode()
    as_b["player"] = "B"
    as_b["result"].update(winner="B", success=True)
    incomplete = episode("decision_timeout", success=False)
    data = snapshot([win, loss, draw, as_b, incomplete])
    data["config"]["opponent"] = "optimal"
    row = summarize(data)["by_game"][0]
    assert row["wins"] == 2
    assert row["draws"] == 1
    assert row["losses"] == 1
    assert row["episodes"] == 5
    assert row["model_errors"] == 1
    data["config"]["opponent"] = "model"
    head_to_head = summarize(data)["by_game"][0]
    assert all(head_to_head[key] is None for key in ("wins", "draws", "losses"))
    solo = summarize(snapshot([episode(game="memory")]))["by_game"][0]
    assert solo["wins"] is solo["draws"] is solo["losses"] is None
    assert solo["successes"] == 1


def test_game_report_exports_keep_archived_attempts_distinct_from_current_metrics():
    old = {**episode("cancelled", success=False), "attempt": 1}
    current = {**episode(), "attempt": 2}
    old["decisions"][0]["response"] = "old attempt"
    current["decisions"][0]["response"] = "current attempt"
    data = {**snapshot([current]), "attempt_history": [[old]]}
    metrics = summarize(data)
    assert metrics["by_game"][0]["episodes"] == 1
    assert metrics["by_game"][0]["input_tokens"] == 10
    assert "cancelled" not in metrics["errors"]
    content, _ = export(data, "json")
    assert json.loads(content)["attempt_history"] == [[old]]
    content, _ = export(data, "jsonl")
    lines = [json.loads(line) for line in content.splitlines()]
    decisions = [line for line in lines if line["kind"] == "decision"]
    assert [line["archived"] for line in decisions] == [True, False]
    assert [line["attempt"] for line in decisions] == [1, 2]
    assert [line["response"] for line in decisions] == [
        "old attempt",
        "current attempt",
    ]
    for line in lines[1:]:
        assert line["case_id"] == "nim-case"
        assert line["episode"] == 1
        assert line["block_id"] == "block-A"
        assert type(line["archived"]) is bool
    content, _ = export(data, "csv")
    records = list(csv.DictReader(io.StringIO(content)))
    assert [row["archived"] for row in records] == ["true", "false"]
    assert [row["attempt"] for row in records] == ["1", "2"]
    assert all(row["block_id"] == "block-A" for row in records)
