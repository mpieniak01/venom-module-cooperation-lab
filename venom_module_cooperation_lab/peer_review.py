"""Fixed author/reviewer/revision phases, not a semantic quality evaluator."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReviewStep:
    participant: str
    recipient: str
    phase: str
    instruction: str


def review_step(index: int, language: str | None) -> ReviewStep:
    phases = (
        (
            "A",
            "B",
            "draft",
            "Zaproponuj krótką odpowiedź na zadanie operatora dla recenzenta B.",
            "Draft a brief answer to the operator task for reviewer B.",
        ),
        (
            "B",
            "A",
            "critique",
            "Sprawdź propozycję A względem zadania. Wskaż konkretne poprawki "
            "lub brak zastrzeżeń; nie wymyślaj błędów.",
            "Review A's draft against the task. Give specific fixes or say "
            "there are no objections; do not invent errors.",
        ),
        (
            "A",
            "operator",
            "revision",
            "Podaj operatorowi poprawioną odpowiedź po recenzji B. "
            "Uwzględnij słuszne uwagi; krótko wyjaśnij ewentualną niezgodę.",
            "Give the operator a revised answer after B's review. Apply valid "
            "feedback; briefly explain any disagreement.",
        ),
    )
    participant, recipient, phase, pl, en = phases[index % 3]
    return ReviewStep(participant, recipient, phase, pl if language == "pl" else en)
