"""Final-rule validation and independent note-budget contracts."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace

import pytest
from pydantic import ValidationError

from venom_module_cooperation_lab.reflection import validate_note
from venom_module_cooperation_lab.run_config import RunConfig, RunRequest
from venom_module_cooperation_lab.runner import OWNER

INSTRUCTION = (
    "Return only JSON with one rule. Do not copy this instruction or write reasoning."
)
RULE = "Take an immediate winning move before defending against an opponent threat."


@pytest.mark.parametrize(
    "text",
    [
        json.dumps({"rule": RULE}),
        "RULE: " + RULE,
        "ZASADA: Najpierw wykorzystaj możliwość natychmiastowej wygranej.",
        "```json\n" + json.dumps({"rule": RULE}) + "\n```",
        "<think>private reasoning not a rule</think>" + json.dumps({"rule": RULE}),
    ],
)
def test_only_finished_bounded_rules_are_accepted(text):
    result = validate_note(text, INSTRUCTION)
    assert result.accepted and result.rule and result.reason == "accepted"
    assert "<think>" not in result.rule


@pytest.mark.parametrize(
    "text,reason",
    [
        ("", "empty_note"),
        ("<think>unfinished", "unfinished_note"),
        (INSTRUCTION, "instruction_echo"),
        (json.dumps({"rule": INSTRUCTION}), "instruction_echo"),
        ('{"rule": 3}', "invalid_note_format"),
        ('{"rule":"win"}', "invalid_note_format"),
        (
            '{"rule":"First play A2 before trying to block the opponent."}',
            "position_specific_note",
        ),
        ('{"rule":"Take a win immediately.","extra":true}', "invalid_note_format"),
        ("RULE: This is an unfinished sentence", "unfinished_note"),
        ("Unstructured prose about a game is not a final rule.", "invalid_note_format"),
        ("x" * 9000, "invalid_note_format"),
        (json.dumps({"rule": "a " * 160}), "invalid_note_format"),
        (
            json.dumps(
                {"rule": "Never save <think>reasoning</think> into the game memory."}
            ),
            "unfinished_note",
        ),
    ],
)
def test_bad_notes_are_rejected_without_salvaging_fragments(text, reason):
    result = validate_note(text, INSTRUCTION)
    assert result.accepted is False and result.rule == "" and result.reason == reason


@pytest.mark.parametrize("tokens", [True, 0, 31, 257])
def test_invalid_note_budgets_are_rejected(tokens):
    with pytest.raises(ValidationError):
        RunRequest(
            model_id="fixture",
            scenario_id="tic_tac_toe",
            mode="game_reflection",
            reflection_max_new_tokens=tokens,
        )


def test_reflection_budget_is_independent_and_does_not_change_legacy_serialization():
    cfg = RunConfig.build(
        RunRequest(
            model_id="fixture",
            scenario_id="tic_tac_toe",
            mode="game_reflection",
            game_count=2,
            max_new_tokens=8,
            reflection_max_new_tokens=128,
        ),
        {},
    )
    assert cfg.budgets.max_new_tokens == 8
    assert cfg.reflection_max_new_tokens == 128
    assert cfg.budgets.total_output_tokens == 2 * 9 * 8 + 2 * 128
    assert (
        cfg.budgets.processing_steps
        == cfg.budgets.total_input_tokens + cfg.budgets.total_output_tokens
    )
    legacy = RunConfig.build(
        RunRequest(model_id="fixture", scenario_id="tic_tac_toe"), {}
    ).public()
    assert "reflection_max_new_tokens" not in legacy and "memory_policy" not in legacy


@pytest.mark.asyncio
async def test_notes_can_exceed_move_budget_without_hiding_cost_or_breaking_idempotency(
    rig,
):
    runner, adapters = rig
    factory = runner.adapter_factory

    def configured(model, lease):
        adapter = factory(model, lease)
        adapter.responses = [
            "A1",
            "A2",
            "A3",
            "B2",
            "B1",
            "B3",
            "C1",
            json.dumps({"rule_id": "block_win"}),
            json.dumps({"rule_id": "win_now"}),
        ] * 2
        original = adapter.generate

        def generate(player, messages, params, deadline):
            value = original(player, messages, params, deadline)
            return (
                replace(value, output_tokens=16)
                if params.max_new_tokens == 128
                else value
            )

        adapter.generate = generate
        return adapter

    runner.adapter_factory = configured
    request = RunRequest(
        model_id="test-0.4b",
        scenario_id="tic_tac_toe",
        mode="game_reflection",
        game_count=2,
        max_new_tokens=8,
        reflection_max_new_tokens=128,
    )
    row, _ = await runner.start(request, "budget-notes")
    await asyncio.wait_for(runner.jobs[row["id"]].task, 5)
    assert runner.snapshot(row["id"])["run"]["status"] == "completed"
    retry, created = await runner.start(request, "budget-notes")
    assert retry["id"] == row["id"] and not created
    assert runner.jobs[row["id"]].output_tokens == 14 * 8 + 2 * 16
    usage = [
        e["payload"]
        for e in runner.store.events(row["id"], owner=OWNER, limit=100)
        if e["kind"] == "usage" and e["payload"].get("purpose") == "reflection"
    ]
    assert len(usage) == 2 and all(u["charged_output_tokens"] == 16 for u in usage)
    assert all(
        c[2].max_new_tokens == 128
        for c in adapters[0].recorded
        if '"supported_rules"' in c[1][-1].content
    )


@pytest.mark.parametrize(
    "scenario,mode",
    [
        ("tic_tac_toe", "dialog"),
        ("tic_tac_toe", "game_strategic"),
        ("tic_tac_toe", "game_assisted"),
        ("split_facts", "no_contact"),
    ],
)
def test_irrelevant_reflection_budget_is_rejected_before_it_can_break_idempotency(
    scenario, mode
):
    from venom_module_cooperation_lab.runner import LabRunner

    with pytest.raises(
        ValidationError, match="reflection_tokens_require_reflection_mode"
    ):
        RunRequest(
            model_id="fixture",
            scenario_id=scenario,
            mode=mode,
            reflection_max_new_tokens=200,
        )
    request = RunRequest(model_id="fixture", scenario_id=scenario, mode=mode)
    config = RunConfig.build(request, {"model_id": "fixture"}).public()
    assert "reflection_max_new_tokens" not in config
    assert LabRunner._same_request(config, request, False)
    note = RunRequest(
        model_id="fixture",
        scenario_id="tic_tac_toe",
        mode="game_reflection",
        reflection_max_new_tokens=200,
    )
    assert note.reflection_max_new_tokens == 200
