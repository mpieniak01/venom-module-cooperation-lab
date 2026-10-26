"""Live v4 observation, rule-use metrics and final-note elimination."""

from __future__ import annotations

import pytest

from venom_module_cooperation_lab.live_game_strategy import LiveGameStrategy
from venom_module_cooperation_lab.run_config import RunConfig, RunRequest
from venom_module_cooperation_lab.tic_tac_toe import TicTacToe


@pytest.mark.parametrize("language", ["pl", "en"])
def test_compact_state_is_complete_and_rule_is_near_the_decision(language):
    game = TicTacToe(board=["X", "", "O", "", "X", "", "", "", "O"], moves=4)
    prompt = game.compact_prompt("A", language, "PRIVATE RULE")
    assert "A1=X" in prompt and "A3=O" in prompt and "B2=X" in prompt
    assert "A2=empty" in prompt and "C2=empty" in prompt
    choice = prompt.splitlines()[-2]
    assert (
        "A2" in choice and "B1" in choice and "A1" not in choice and "C3" not in choice
    )
    assert prompt.index("PRIVATE RULE") > prompt.index("Cells:")
    assert "B PRIVATE" not in prompt
    assert len(prompt) < len(game.prompt("A", language)) + len("PRIVATE RULE")
    assert "PRIVATE RULE" not in game.compact_prompt("B", language)


def test_metrics_measure_proposals_and_never_replace_them():
    strategy = LiveGameStrategy("game_reflection")
    strategy.note_ids["A"] = "win_now"
    board = ["X", "X", "", "O", "O", "", "", "", ""]
    game = TicTacToe(board=board, moves=4)
    ignored = strategy.choose(game, "A", "C1", 0)
    followed = strategy.choose(game, "A", "A3", 0)
    assert ignored["action"] == {"square": "C1"}
    assert ignored["rule_application"]["followed"] is False
    assert followed["rule_application"]["followed"] is True
    assert strategy.public()["rule_opportunities"] == 2
    assert strategy.public()["rule_followed"] == strategy.public()["rule_ignored"] == 1
    quiet = strategy.choose(TicTacToe(), "A", "A1", 0)
    assert quiet["rule_application"]["applicable"] is False
    assert quiet["rule_application"]["followed"] is None
    strategy.begin()
    assert strategy.note_ids["A"] == "win_now" and strategy.rule_opportunities == 2


@pytest.mark.parametrize("games", [2, 3, 10])
def test_budgets_only_reserve_notes_between_games(games):
    cfg = RunConfig.build(
        RunRequest(
            model_id="fixture",
            scenario_id="tic_tac_toe",
            mode="game_reflection",
            game_count=games,
            max_new_tokens=8,
            reflection_max_new_tokens=32,
        ),
        {},
    )
    notes = 2 * (games - 1)
    assert cfg.budgets.total_input_tokens == (9 * games + notes) * 2048
    assert cfg.budgets.total_output_tokens == 9 * games * 8 + notes * 32
    assert (
        cfg.budgets.processing_steps
        == cfg.budgets.total_input_tokens + cfg.budgets.total_output_tokens
    )
    assert cfg.public()["reflection_schedule"] == "between-games-only"
    assert cfg.public()["observation_profile"] == "explicit-cells-v1"


@pytest.mark.parametrize("architecture", ["hrm_text", "huginn_raven", "rwkv7"])
def test_model_specific_context_keeps_own_rule_close_without_leaking_peer_memory(
    rig, architecture
):
    from types import SimpleNamespace

    from venom_module_cooperation_lab.adapters.base import ChatMessage

    runner, _ = rig
    config = RunConfig.build(
        RunRequest(
            model_id="fixture",
            scenario_id="tic_tac_toe",
            mode="game_reflection",
            communication_language="pl",
        ),
        {"architecture": architecture},
    )
    coaching = LiveGameStrategy("game_reflection")
    coaching.notes = {"A": "PRIVATE_A", "B": "PRIVATE_B"}
    job = SimpleNamespace(
        config=config,
        coaching=coaching,
        game=TicTacToe(),
        histories={
            "A": [ChatMessage("system", "system"), ChatMessage("user", "peer-id A1")]
        },
        last_delivered={"A": "peer-id"},
    )
    context = runner._turn_context(job, "A")
    assert "PRIVATE_A" in context[-1].content and "PRIVATE_B" not in context[-1].content
    assert ("Cells:" in context[-1].content) == (architecture != "hrm_text")
    if architecture == "hrm_text":
        assert context[1].content == "peer-id A1"
        assert (
            config.public()["observation_profile"] == "board-and-peer-with-reminder-v1"
        )
    elif architecture == "huginn_raven":
        assert len(context) == 2 and "peer-id" not in context[-1].content
