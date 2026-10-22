"""Answer mapping does not solve games or guess incomplete model decisions."""

import pytest

from venom_module_cooperation_lab.errors import LabError
from venom_module_cooperation_lab.evaluation.actions import parse_action
from venom_module_cooperation_lab.evaluation.games import make_environment


@pytest.mark.parametrize(
    "game,text,action",
    [
        ("sokoban", "move right", {"move": "right"}),
        ("sokoban", '{"action":"move","move":"right"}', {"move": "right"}),
        ("sokoban", '{"action":"move","value":"right"}', {"move": "right"}),
        ("nim", "take 1 stone from heap 0", {"heap": 0, "take": 1}),
        ("memory", "reveal 1 and 2", {"cards": [1, 2]}),
        ("memory", "cards: 0, 5", {"cards": [0, 5]}),
        ("tic_tac_toe", "Move b2.", {"square": "B2"}),
        ("sokoban", 'Answer: ```json\n{"move":"right"}\n```', {"move": "right"}),
        (
            "sokoban",
            '<think>left or right?</think>\n{"move":"right"}',
            {"move": "right"},
        ),
    ],
)
def test_explicit_answer_maps_without_changing_selected_move(game, text, action):
    actual, receipt = parse_action(text, game, "mapped")
    assert actual == action
    assert receipt["version"] == "action-map-v1" and receipt["mapped"]
    if text.startswith("{"):
        # Strict JSON deliberately leaves envelopes unmodified.
        original, strict = parse_action(text, game, "strict_json")
        assert original != action and not strict["mapped"]
    else:
        with pytest.raises(LabError, match="invalid_format"):
            parse_action(text, game, "strict_json")


@pytest.mark.parametrize(
    "text",
    [
        "right or left",
        "I might move right.",
        "match",
        "<think>I should move right",
        '{"move":"left","move":"right"}',
        '{"move":"right"} {"move":"left"}',
        '["right"]',
        '{"move":NaN}',
        'Here is an observation: {"move":"right"}',
        '<think>{"move":"right"}</think>',
    ],
)
def test_ambiguous_truncated_echoed_or_duplicate_answers_are_rejected(text):
    with pytest.raises(LabError, match="invalid_format"):
        parse_action(text, "sokoban", "mapped")


def test_canonical_json_is_unchanged_and_illegal_moves_are_not_repaired():
    action, receipt = parse_action('{"move":"right"}', "sokoban", "mapped")
    assert action == {"move": "right"} and not receipt["mapped"]
    env = make_environment("sokoban", {"board": ["#####", "#@$.#", "#####"]}, 17)
    action, _ = parse_action("move left", "sokoban", "mapped")
    with pytest.raises(LabError, match="illegal_action"):
        env.step("A", action)
    assert env.result()["actions"] == 0
    with pytest.raises(LabError, match="invalid_format"):
        parse_action("right", "sokoban", "unknown")
    for text in ('{"move":"right","extra":1}', '{"action":"stop","value":"right"}'):
        action, _ = parse_action(text, "sokoban", "mapped")
        with pytest.raises(LabError, match="illegal_action"):
            env.step("A", action)
