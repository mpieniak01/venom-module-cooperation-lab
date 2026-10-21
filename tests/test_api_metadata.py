import json
from pathlib import Path

from venom_module_cooperation_lab.api.routes import catalog_metadata


def test_public_contract_is_serialized_real_backend_metadata():
    metadata = json.loads(json.dumps(catalog_metadata()))
    expected = json.loads(Path("tests/contracts/capabilities.json").read_text())
    assert metadata == expected
    assert all(model["qualified"] is False for model in metadata["models"])
    assert {scenario["scenario_id"] for scenario in metadata["scenarios"]} == {
        "operator_conversation",
        "split_facts",
        "organization",
        "correction",
        "tic_tac_toe",
    }
    assert all(scenario["version"] == "1" for scenario in metadata["scenarios"])
    assert all(
        "expected" not in scenario and "private_a" not in scenario
        for scenario in metadata["scenarios"]
    )
