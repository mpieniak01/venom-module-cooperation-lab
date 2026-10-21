"""Small immutable tasks; ground truth is evaluated separately from consensus."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .errors import LabError


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    version: str
    title: str
    goal: str
    private_a: str
    private_b: str
    expected: str

    def public(self) -> dict[str, str]:
        return {
            key: value
            for key, value in asdict(self).items()
            if key not in {"private_a", "private_b", "expected"}
        }


SCENARIOS = (
    Scenario(
        "split_facts",
        "1",
        "Split facts",
        "Find the two-letter code.",
        "The first letter is R.",
        "The second letter is K.",
        "RK",
    ),
    Scenario(
        "organization",
        "1",
        "Shared calculation",
        "Find the sum of the two private numbers.",
        "Your private number is 17.",
        "Your private number is 25.",
        "42",
    ),
    Scenario(
        "correction",
        "1",
        "Correct a proposal",
        "A proposed sum is 41. Verify or correct it using both private numbers.",
        "Your private number is 17.",
        "Your private number is 25.",
        "42",
    ),
)


def get_scenario(scenario_id: str) -> Scenario:
    for scenario in SCENARIOS:
        if scenario.scenario_id == scenario_id:
            return scenario
    raise LabError("scenario_not_allowed", 422)
