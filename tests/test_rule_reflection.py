"""Tactical evidence, language profiles, and raw invalid-answer preservation."""

from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest

from venom_module_cooperation_lab.errors import LabError
from venom_module_cooperation_lab.live_game_strategy import LiveGameStrategy
from venom_module_cooperation_lab.rule_reflection import (
    instruction,
    parse_choice,
    rule_text,
    supported_rules,
)
from venom_module_cooperation_lab.run_config import RunConfig, RunRequest
from venom_module_cooperation_lab.runner import OWNER
from venom_module_cooperation_lab.tic_tac_toe import TicTacToe


def feedback(board, player, move):
    game = TicTacToe(board=list(board), moves=sum(bool(x) for x in board))
    coaching = LiveGameStrategy("game_reflection")
    coaching.choose(game, player, move, 0)
    return coaching.feedback(game, player)


def test_win_has_priority_over_block_and_requires_real_error():
    state = ["X", "X", "", "O", "O", "", "", "", ""]
    supported = supported_rules(feedback(state, "A", "B3"))
    assert set(supported) == {"win_now"}
    assert supported["win_now"]["orientations_checked"] == 8
    assert supported["win_now"]["future_model_behavior_verified"] is False
    assert parse_choice('{"rule_id":"block_win"}', supported) == (
        None,
        "unsupported_rule",
    )
    # A good move is not evidence of a mistake, even with a forged annotation.
    good = feedback(state, "A", "A3")
    good["lessons"] = [
        {
            "board": state,
            "model_action": {"square": "A3"},
            "assessment": {"worse_move": True},
        }
    ]
    assert supported_rules(good) == {}


def test_block_requires_no_own_win_and_a_single_threat():
    state = ["X", "X", "", "", "O", "", "", "", ""]
    assert set(supported_rules(feedback(state, "B", "C1"))) == {"block_win"}
    assert supported_rules({"player": "A", "lessons": []}) == {}
    assert supported_rules(feedback([""] * 9, "A", "A1")) == {}
    assert "natychmiast" in rule_text("win_now", "pl")
    assert "Return only JSON" in instruction("en") and "Wybierz" in instruction("pl")


@pytest.mark.parametrize(
    "raw,reason",
    [
        ("", "empty_note"),
        ("x" * 8200, "invalid_note_format"),
        ("<think>unfinished", "unfinished_note"),
        ('{"rule_id":"win_now","rule_id":"block_win"}', "invalid_note_format"),
        ('{"rule":"Never play in an opponent line."}', "invalid_note_format"),
        ('{"rule_id":[]}', "invalid_note_format"),
        ("[]", "invalid_note_format"),
        ('{"rule_id":"invented"}', "unsupported_rule"),
    ],
)
def test_arbitrary_or_ambiguous_rules_never_become_memory(raw, reason):
    assert parse_choice(raw, {"win_now": {}}) == (None, reason)


@pytest.mark.parametrize(
    "raw",
    [
        '{"rule_id":"win_now"}',
        '```json\n{"rule_id":"win_now"}\n```',
        '<think>done</think>{"rule_id":"win_now"}',
    ],
)
def test_finished_rule_choices_are_accepted(raw):
    assert parse_choice(raw, {"win_now": {}}) == ("win_now", "evidence_checked")


@pytest.mark.parametrize("architecture", ["hrm_text", "huginn_raven", "rwkv7"])
def test_new_profiles_are_explicit_and_legacy_prompts_unchanged(architecture):
    model = {"architecture": architecture}
    cfg = RunConfig.build(
        RunRequest(
            model_id="fixture",
            scenario_id="tic_tac_toe",
            mode="game_strategic",
            communication_language="pl",
        ),
        model,
    )
    assert cfg.communication_language == "pl"
    assert cfg.game_language == ("pl" if architecture == "rwkv7" else "en")
    assert cfg.public()["model_language"] == cfg.game_language
    assert ("Examples of" in cfg.prompts[0]) == (architecture == "hrm_text")
    old = RunConfig.build(
        RunRequest(
            model_id="fixture", scenario_id="tic_tac_toe", communication_language="pl"
        ),
        model,
    ).public()
    assert "model_language" not in old and "num_steps" not in old
    assert "Jesteś A" in old["prompts"][0]


def test_huginn_steps_are_allowed_only_for_supported_live_models():
    request = RunRequest(
        model_id="fixture",
        scenario_id="tic_tac_toe",
        mode="game_strategic",
        num_steps=32,
    )
    assert (
        RunConfig.build(request, {"architecture": "huginn_raven"}).public()["num_steps"]
        == 32
    )
    with pytest.raises(LabError, match="unsupported_compute_steps"):
        RunConfig.build(request, {"architecture": "rwkv7"})
    with pytest.raises(LabError, match="unsupported_compute_steps"):
        RunConfig.build(
            request.model_copy(update={"mode": "dialog"}),
            {"architecture": "huginn_raven"},
        )


@pytest.mark.asyncio
async def test_skipped_reflection_has_no_generation_cost_and_keeps_players_private(rig):
    runner, adapters = rig
    factory = runner.adapter_factory

    def configured(model, lease):
        adapter = factory(model, lease)
        adapter.responses = [
            "A1",
            "B2",
            "A2",
            "C3",
            "A3",
            '{"rule_id":"block_win"}',
        ] * 2
        return adapter

    runner.adapter_factory = configured
    row, _ = await runner.start(
        RunRequest(
            model_id="test-0.4b",
            scenario_id="tic_tac_toe",
            mode="game_reflection",
            game_count=2,
        ),
        "skip-notes",
    )
    await asyncio.wait_for(runner.jobs[row["id"]].task, 5)
    assert runner.snapshot(row["id"])["run"]["status"] == "completed", [
        (e["kind"], e["payload"])
        for e in runner.store.events(row["id"], owner=OWNER, limit=100)
        if e["kind"] in {"error", "reflection"}
    ]
    events = runner.store.events(row["id"], owner=OWNER, limit=100)
    notes = [e["payload"] for e in events if e["kind"] == "reflection"]
    assert len(adapters[0].recorded) == 11
    assert [n.get("skipped", False) for n in notes] == [True, False]
    assert all(
        n.get("validation", {}).get("orientations_checked") == 8
        for n in notes
        if n["accepted"]
    )
    final = [e["payload"] for e in events if e["kind"] == "game"][-1]["strategy"]
    assert (
        final["accepted_notes"],
        final["skipped_notes"],
        final["rejected_notes"],
    ) == (1, 1, 0)


@pytest.mark.asyncio
async def test_invalid_move_keeps_original_special_tokens(rig):
    runner, _ = rig
    factory = runner.adapter_factory

    def configured(model, lease):
        adapter = factory(model, lease)
        original = adapter.generate

        def generate(*args):
            return replace(original(*args), text="A1 A2", raw_text="A1 A2<|end_turn|>")

        adapter.generate = generate
        return adapter

    runner.adapter_factory = configured
    row, _ = await runner.start(
        RunRequest(
            model_id="test-0.4b", scenario_id="tic_tac_toe", mode="game_strategic"
        ),
        "raw-invalid",
    )
    await asyncio.wait_for(runner.jobs[row["id"]].task, 5)
    message = next(
        e["payload"]
        for e in runner.store.events(row["id"], owner=OWNER, limit=100)
        if e["kind"] == "message"
    )
    assert message["raw_content"] == "A1 A2<|end_turn|>"


def test_missed_immediate_win_is_a_lesson_even_when_forced_win_is_preserved():
    board = ["X", "X", "", "O", "", "", "O", "", ""]
    own = feedback(board, "A", "B2")
    assert own["lessons"][0]["assessment"]["missed_win"]
    assert own["lessons"][0]["assessment"]["worse_move"] is False
    assert set(supported_rules(own)) == {"win_now"}


@pytest.mark.parametrize("raw", ['"win_now"', "win_now"])
def test_one_explicit_rule_identifier_is_mapped_without_selecting_for_model(raw):
    assert parse_choice(raw, {"win_now": {}}) == ("win_now", "evidence_checked_mapped")
    assert parse_choice(raw, {"block_win": {}}) == (None, "unsupported_rule")
    assert parse_choice("win_now block_win", {"win_now": {}}) == (
        None,
        "invalid_note_format",
    )
