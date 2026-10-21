"""Small immutable tasks; ground truth is evaluated separately from consensus."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Literal

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
        "operator_conversation",
        "1",
        "Operator conversation",
        "Follow the operator conversation. The operator supplies the topic. "
        "Do not invent an operator message.",
        "",
        "",
        "",
    ),
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
    Scenario(
        "tic_tac_toe",
        "1",
        "Tic-tac-toe",
        "Play tic-tac-toe on a 3x3 board. A is X and starts; B is O. "
        "Rows are A, B, C and columns are 1, 2, 3. "
        "Take turns placing one mark on an empty square. "
        "Three marks in a row, column or diagonal win; a full board is a draw. "
        "Return only the coordinate of your move, e.g. B2. "
        "The host validates moves and decides when the game ends.",
        "You play X. Try to win, or prevent losing.",
        "You play O. Try to win, or prevent losing.",
        "",
    ),
)


def get_scenario(scenario_id: str) -> Scenario:
    for scenario in SCENARIOS:
        if scenario.scenario_id == scenario_id:
            return scenario
    raise LabError("scenario_not_allowed", 422)


DialogueLanguage = Literal["pl", "en"]

# Localized dialogue profiles are separate from the frozen benchmark v1.
_POLISH_SCENARIOS = {
    "operator_conversation": (
        "Rozmowa operatora",
        "Prowadź rozmowę według wpisów operatora. "
        "Operator podaje temat. Nie wymyślaj wiadomości operatora.",
        "",
        "",
    ),
    "tic_tac_toe": (
        "Kółko i krzyżyk",
        "Zagraj w kółko i krzyżyk na planszy 3x3. A gra X i zaczyna; B gra O. "
        "Wiersze to A, B, C, a kolumny 1, 2, 3. "
        "Wykonujcie na zmianę po jednym ruchu na wolnym polu. "
        "Trzy znaki w wierszu, kolumnie lub przekątnej oznaczają wygraną; "
        "pełna plansza oznacza remis. "
        "Zwróć wyłącznie współrzędne ruchu, np. B2. "
        "Host sprawdza ruchy i rozstrzyga zakończenie partii.",
        "Grasz X. Spróbuj wygrać lub zapobiec przegranej.",
        "Grasz O. Spróbuj wygrać lub zapobiec przegranej.",
    ),
    "split_facts": (
        "Rozdzielone informacje",
        "Ustal dwuliterowy kod.",
        "Pierwsza litera to R.",
        "Druga litera to K.",
    ),
    "organization": (
        "Wspólne obliczenie",
        "Oblicz sumę dwóch prywatnych liczb.",
        "Twoja prywatna liczba to 17.",
        "Twoja prywatna liczba to 25.",
    ),
    "correction": (
        "Sprawdzenie i poprawa propozycji",
        "Zaproponowana suma to 41. Sprawdź ją lub popraw, "
        "korzystając z obu prywatnych liczb.",
        "Twoja prywatna liczba to 17.",
        "Twoja prywatna liczba to 25.",
    ),
}


def get_dialogue_scenario(scenario_id: str, language: DialogueLanguage) -> Scenario:
    scenario = get_scenario(scenario_id)
    if language == "pl":
        title, goal, private_a, private_b = _POLISH_SCENARIOS[scenario_id]
        scenario = replace(
            scenario, title=title, goal=goal, private_a=private_a, private_b=private_b
        )
    return replace(scenario, version=f"{scenario.version}-dialogue-{language}-1")
