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
    assert caps["max_context_tokens"] == context and caps["max_new_tokens"] == 1024
