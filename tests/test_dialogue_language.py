from __future__ import annotations

import asyncio

import pytest
from conftest import SPEC
from pydantic import ValidationError

from venom_module_cooperation_lab.run_config import RunConfig, RunRequest
from venom_module_cooperation_lab.scenarios import get_scenario


def request(**values):
    return RunRequest(
        model_id=SPEC.model_id,
        scenario_id=values.pop("scenario_id", "split_facts"),
        **values,
    )


def test_legacy_config_and_frozen_scenarios_keep_exact_v1_hash():
    config = RunConfig.build(
        request(max_turns=4), {"model_id": SPEC.model_id, "digest": "digest1"}
    )
    assert (
        config.public()["config_hash"]
        == "0a02575d3d57b3c36ba7a50bb0148b941810b596aefdff3f104265b670e4aed7"
    )
    assert "communication_language" not in config.public()
    assert config.public()["schema_version"] == 1
    assert get_scenario("split_facts").version == "1"
    assert get_scenario("split_facts").goal == "Find the two-letter code."
    for language in ["fr", "PL", True, {}, 1]:
        with pytest.raises(ValidationError):
            request(communication_language=language)


@pytest.mark.parametrize("scenario_id", ["split_facts", "organization", "correction"])
@pytest.mark.parametrize("language", ["pl", "en"])
def test_language_is_immutable_hashed_and_separate_from_benchmark(
    scenario_id, language
):
    config = RunConfig.build(
        request(scenario_id=scenario_id, communication_language=language), {}
    )
    public = config.public()
    assert public["communication_language"] == language
    assert public["schema_version"] == 2
    assert public["scenario_version"] == f"1-dialogue-{language}-1"
    assert config.public() == public
    assert get_scenario(scenario_id).version == "1"
    other = RunConfig.build(
        request(
            scenario_id=scenario_id,
            communication_language="en" if language == "pl" else "pl",
        ),
        {},
    )
    assert public["config_hash"] != other.public()["config_hash"]
    expected = (
        "Porozumiewaj się po polsku" if language == "pl" else "Communicate in English"
    )
    assert all(expected in prompt for prompt in config.prompts)
    if language == "pl":
        assert "Cel: " in config.prompts[0] and "Goal: " not in config.prompts[0]
        if scenario_id == "split_facts":
            assert "Pierwsza litera to R." in config.prompts[0]
            assert "Druga litera to K." not in config.prompts[0]
            assert "Druga litera to K." in config.prompts[1]


@pytest.mark.asyncio
@pytest.mark.parametrize("language", ["pl", "en"])
@pytest.mark.parametrize("mode", ["self_correction", "no_contact", "dialog"])
async def test_language_reaches_adapter_followups_and_delivery(rig, language, mode):
    runner, adapters = rig
    row, _ = await runner.start(
        request(communication_language=language, mode=mode, max_turns=4), "language"
    )
    await asyncio.wait_for(runner.jobs[row["id"]].task, timeout=5)
    assert (
        runner.snapshot(row["id"])["run"]["config"]["communication_language"]
        == language
    )
    adapter = adapters[0]
    assert len(adapter.recorded) == 4
    if mode == "dialog":
        label = "Wiadomość " if language == "pl" else "Message "
        assert adapter.recorded[1][1][-1].content.startswith(label)
    else:
        expected = {
            ("pl", "self_correction"): "Sprawdź swoją poprzednią odpowiedź.",
            ("en", "self_correction"): "Verify your previous answer.",
            (
                "pl",
                "no_contact",
            ): "Kontynuuj, korzystając wyłącznie z informacji we własnym kontekście.",
            (
                "en",
                "no_contact",
            ): "Continue using only the information in your own context.",
        }[(language, mode)]
        assert adapter.recorded[-1][1][-1].content == expected
    assert runner.admission.snapshot()["status"] == "available"
