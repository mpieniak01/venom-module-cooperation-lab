"""Persisted model budgets do not load weights or change experiment snapshots."""

import pytest

from venom_module_cooperation_lab.adapters.base import GenerationParameters
from venom_module_cooperation_lab.adapters.rwkv_process import RwkvError, RwkvParameters
from venom_module_cooperation_lab.errors import LabError
from venom_module_cooperation_lab.evaluation.sessions import capabilities_for


def test_output_limits_are_shared_while_context_contracts_stay_versioned():
    for factory in (GenerationParameters, RwkvParameters):
        p = factory(
            session_protocol="game-eval-v2",
            max_context_tokens=8192,
            max_new_tokens=1024,
        )
        assert p.max_new_tokens == 1024 and p.max_context_tokens == 8192
        assert factory(max_new_tokens=1024).max_new_tokens == 1024
        with pytest.raises((LabError, RwkvError), match="invalid_parameters"):
            factory(max_new_tokens=1025)
        with pytest.raises((LabError, RwkvError), match="invalid_parameters"):
            factory(session_protocol="game-eval-v2", max_new_tokens=1025)


@pytest.mark.parametrize(
    "architecture,context",
    [
        ("rwkv7", 8192),
        ("hrm_text", 4096),
        ("huginn_raven", 4096),
    ],
)
def test_context_caps_follow_supported_checkpoint_family(architecture, context):
    caps = capabilities_for({"architecture": architecture})
    assert caps["max_context_tokens"] == context
    assert caps["max_new_tokens"] == (1024 if architecture == "rwkv7" else 256)


@pytest.mark.parametrize(
    "model,limit",
    [
        ({"architecture": "rwkv7"}, 1024),
        ({"architecture": "hrm_text"}, 256),
        ({"architecture": "huginn_raven"}, 256),
        ({"provider": "ollama", "runtime": "ollama==0.40.6"}, 1024),
        ({"architecture": "unknown"}, 256),
    ],
)
def test_start_uses_model_ceiling_without_increasing_smaller_values(model, limit):
    from venom_module_cooperation_lab.model_limits import applied_output_tokens
    from venom_module_cooperation_lab.run_config import RunConfig, RunRequest

    for requested in (64, limit, 16384):
        config = RunConfig.build(
            RunRequest(
                model_id="fixture", scenario_id="split_facts", max_new_tokens=requested
            ),
            model,
        ).public()
        assert config["budgets"]["max_new_tokens"] == min(requested, limit)
        assert config.get("requested_max_new_tokens") == (
            requested if requested > limit else None
        )
        assert applied_output_tokens(requested, model) == min(requested, limit)
