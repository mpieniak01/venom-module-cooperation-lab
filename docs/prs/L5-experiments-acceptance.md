# L5 — samoorganizacja i pełny odbiór MVP

Status: IMPLEMENTACJA LOKALNA; realny odbiór i właściwy numer PR pending. Repo: venom-module-cooperation-lab. Zależności: L1–L4 i C0.

## Problem i wynik

Sama rozmowa ani zgodność odpowiedzi nie dowodzi zorganizowanej współpracy. Potrzebne małe, odtwarzalne eksperymenty i pełny realny odbiór miejsca do testów.

## Zakres

Wersjonowane scenariusze: rozdzielona informacja, uzgodnienie podziału pracy, korekta rzeczywistego błędu. Warianty samotnie/samokorekta/no-contact/dialog bez ról/dialog z zachętą. Zamrożone wejścia, kolejność i parametry; porównywalny budżet i rzeczywisty koszt. Osobno zobowiązania zadeklarowane i wykonane, ground truth/rubryka niezależne od konsensusu modeli.

Mały zestaw startowy, nie wielogodzinna macierz. Ujemny wynik hipotezy jest poprawnym wynikiem badania. Runbook instalacji/OFF/rollback/retencji i raport wyników z granicami uogólnienia. Bez zmiany benchmarku po fakcie, aby uzyskać poprawę. Bez nowych modeli, liczby agentów i treningu w tym PR.

## Walidacja

[Pełny odbiór](../ACCEPTANCE.md) na dokładnej zgodnej parze core/module/adapter: realna sesja kontroli i nowego modelu, pomiary, cancel/quiescence, cold restart i wyłączenie, retencja, brak regresji dotychczasowego chatu/runtime/ekranów. Wszystkie skonfigurowane CI/review/skany właściwego SHA. Blocker/limit skanera jawny i blokuje release bez osobnego rozstrzygnięcia; nie manual PASS. Rzeczywisty eksperyment nie steruje robotem. Wynik nie musi być lepszy od jednego modelu, aby laboratorium było sprawne.

Poza zakresem: trening wag, kolejne modele/uczestnicy, płatne zasoby, automatyczna publikacja danych i sterowanie urządzeniami.

## Kryteria zamknięcia

- [ ] Zakres i zależności zgodne z planem; exact SHA hosta/modułu/adaptera zapisane.
- [ ] Testy faktycznie wykonane; wyniki, ograniczenia i skips jawne.
- [ ] Brak auto-download, sekretów w Git, pozornej współpracy i manual PASS.
- [ ] Review i wymagane bramki zakończone; dokumentacja i rollback.

Kontrakty: [CONTRACTS](../CONTRACTS.md). [Plan](../PLAN.md), [pełny odbiór](../ACCEPTANCE.md).


## Implementacja i granice dowodów

Gotowe: wersjonowana niezależna rubryka, mały plan 2 prób / opcjonalna macierz30,
pięć trybów, publiczne syntetyczne metadata, ocena exportu z seq/hash/quiescence,
metryki actual/charged/load/TTFT/device i deklaracje oddzielone od dowodów.
CLI domyślnie tylko planuje, wykonuje pracę przez istniejące lokalne API dopiero
po `--execute` i qualified preflight; stały endpoint, bez proxy/redirectów,
idempotentne retry, bounded cancel, prywatne raporty i jawne Delete.

Testy deterministyczne badają kontrakt i błędy; nie przedstawiają odpowiedzi
fixture jako inferencji. Formalny wspólny GPU/browser/OFF/recovery odbiór jest
pending i zostanie uzupełniony wyłącznie actual receiptami koordynatora.
[Metodologia](../EXPERIMENTS.md), [procedura i rollback](../RUNBOOK.md).

Lokalna walidacja L5 (2026-10-21): Ruff/mypy PASS; pełna regresja Python
179 testów PASS / 96,98% coverage, w tym awaria zapisu receipt.
Smoke default plan
nie wykonał HTTP ani inferencji. Lokalne linki Markdown PASS. Realny odbiór
GPU/browser/wyłączenia i skany pozostają oddzielnymi pending warunkami.

Dodatkowy przegląd P2: zgodność recipient/delivered_to i turn→usage→message,
whitelist per-turn effective_parameters, stop_reason i truncation_count.
Pełna lokalna regresja po poprawkach: 189 testów PASS, 96,98% coverage;
Ruff/format/mypy (z CLI) PASS. Bez nowych prób GPU.


Obsługa actual late cleanup: failed end pozostaje failed/unscorable; osobny
zgodny trwały cleanup_late marker może potwierdzić wyłącznie zwolnienie zasobu.
CLI odczytuje tylko ten sam run/export przez max20s/max20 odczytów, bez nowej
generacji. Trwała quarantine blokuje batch/Delete. Regresja CPU oraz mypy/Ruff
potwierdzone lokalnie, bez dalszej inferencji.
