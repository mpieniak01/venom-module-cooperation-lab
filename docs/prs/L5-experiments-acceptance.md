# L5 — samoorganizacja i pełny odbiór MVP

Status: KOD I LOKALNY ODBIÓR TECHNICZNY GOTOWE; publikacja, recenzja, kontrole i scalenie L5 pozostają do wykonania. Rzeczywiste GPU/matrix/browser/SSE/STOP/OFF mają dowody w RELEASE_ACCEPTANCE. Repo: venom-module-cooperation-lab. Zależności: L1–L4 i C0.

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

Gotowe: wersjonowana niezależna rubryka, mały plan 2 prób / opcjonalna macierz 30,
pięć trybów, publiczne syntetyczne metadata, ocena exportu z seq/hash/quiescence,
metryki actual/charged/load/TTFT/device i deklaracje oddzielone od dowodów.
CLI domyślnie tylko planuje, wykonuje pracę przez istniejące lokalne API dopiero
po `--execute` i qualified preflight; stały endpoint, bez proxy/redirectów,
idempotentne retry, bounded cancel, prywatne raporty i jawne Delete.

Testy deterministyczne badają kontrakt i błędy; nie przedstawiają odpowiedzi
fixture jako inferencji. Formalny GPU oraz rzeczywiste matrix/browser/SSE/STOP/OFF
mają receipty koordynatora w RELEASE_ACCEPTANCE. Zwykłego chatu po laboratorium
nie uruchamiano; crash/retencja/quotas to dowody fixture.
[Metodologia](../EXPERIMENTS.md), [procedura i rollback](../RUNBOOK.md).

Lokalna walidacja L5 (2026-10-21): Ruff/mypy PASS; pełna regresja Python
179 testów PASS / 96,98% coverage, w tym awaria zapisu receipt.
Smoke default plan
nie wykonał HTTP ani inferencji. Lokalne linki Markdown PASS. Realny odbiór
GPU/browser/wyłączenia odnotowano później w RELEASE_ACCEPTANCE; skany i końcowe
scalenie L5 pozostają warunkami wydania.

Dodatkowy przegląd P2: zgodność recipient/delivered_to i turn→usage→message,
whitelist per-turn effective_parameters, stop_reason i truncation_count.
Pełna lokalna regresja po poprawkach: 189 testów PASS, 96,98% coverage;
Ruff/format/mypy (z CLI) PASS. Bez nowych prób GPU.


Obsługa actual late cleanup: failed end pozostaje failed/unscorable; osobny
zgodny trwały cleanup_late marker może potwierdzić wyłącznie zwolnienie zasobu.
CLI odczytuje tylko ten sam run/export przez max20s/max20 odczytów, bez nowej
generacji. Trwała quarantine blokuje batch/Delete. Regresja CPU oraz mypy/Ruff
potwierdzone lokalnie, bez dalszej inferencji.


Aktualny odbiór i granice dowodów: [RELEASE_ACCEPTANCE](../RELEASE_ACCEPTANCE.md).


## Końcowy lokalny odbiór 2026-10-21

Macierz 30: 30/30 completed, 12/12 dialogowych prób z komunikacją i 30/30 strict-v1
unscorable (nie 0% accuracy). Realny browser: START RWKV/A/B, ta sama próba po
reload i wiadomości 1→4; SSE proxy HTTP 200/text/event-stream replay 2→17;
STOP cancelled/quiescent, lease available/0 operacji i Ollama ps[]. Stałe
kontrolki, desktop/mobile bez overflow, PL/EN/DE sprawdzone. 0 console errors;
ostrzeżenia wykresów hosta pozostają jawne.

Pełna regresja integracji: 252 Python PASS / ok. 97%, 13 React PASS / 95.28%,
mypy/TS/lint i host contracts PASS. Szczegóły, rewizje i ograniczenia:
[RELEASE_ACCEPTANCE](../RELEASE_ACCEPTANCE.md). Publikacja/review/merge L5,
końcowe skany i exact release SHA nadal pending. V1 pozostaje zamrożone;
final-answer contract v2 jest oddzielnym researchem.
