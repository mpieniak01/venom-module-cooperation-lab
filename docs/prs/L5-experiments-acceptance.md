# L5 — samoorganizacja i pełny odbiór MVP

Status: [PR #13 do main](https://github.com/mpieniak01/venom-module-cooperation-lab/pull/13) OTWARTY; końcowa recenzja, kontrole i scalenie L5 pozostają do wykonania. L1–L4 i C0 scalone; L4 PR #12 ma CI/contracts/Sonar/Snyk/GitGuardian i niezależny review PASS. Rzeczywiste GPU/matrix/browser/SSE/STOP/OFF mają dowody w RELEASE_ACCEPTANCE. Próba zwykłego chatu po laboratorium zwróciła HTTP 400 przed pierwszą treścią; ponowny odbiór po poprawce cleanup transportu jest nierozwiązanym blockerem. Repo: venom-module-cooperation-lab. Zależności: L1–L4 i C0.

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
mają receipty koordynatora w RELEASE_ACCEPTANCE. Późniejszy rzeczywisty probe
zwykłego chatu zakończył się HTTP 400 przed pierwszą treścią; nie jest to PASS.
Crash/retencja/quotas pozostają dowodami fixture.
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
kontrolki, desktop/mobile bez overflow, PL/EN/DE sprawdzone. Podstawowy smoke:
0 console errors, z jawnymi ostrzeżeniami wykresów hosta. Dodatkowo realna historia
Qwen→RWKV odtworzyła model/2 tury/32 tokeny; eksport własnej anulowanej próby
pobrano, a usunięcie potwierdzono HTTP 404 (1 oczekiwany błąd konsoli). PL przywrócono.

Pełna regresja integracji: 252 Python PASS / 97% (1993 statements / 55 miss),
mypy 20 źródeł, 15 testów frontendowych PASS / 96,02%, TS/lint i host contracts
PASS. L4 scalony jako `1021bb3`, kod `6fb7613` z CI/contracts, Sonar, Snyk,
GitGuardian i niezależnym review PASS. Szczegóły, rewizje i ograniczenia:
[RELEASE_ACCEPTANCE](../RELEASE_ACCEPTANCE.md). PR #13 ma bazę main; jego
review/końcowe kontrole/scalenie, exact release SHA i deployment nadal pending.

Ponowny browser smoke finalnego refaktoru L4 (`382dd65`) potwierdził PL/EN/DE,
stały desktop/mobile i widoczne START/STOP, bez overflow i z 0 błędów konsoli
w tym przebiegu. Eksport/Delete odebrano wcześniej na `b3dcc43`; probe 404
pozostaje oddzielnym wynikiem.

Zwykły chat po laboratorium: jeden rzeczywisty probe FAILED — HTTP 400 przed
pierwszą treścią. Wybór operatora `gemma2:2b` (legacy completion-only) niezmieniony.
Body błędu utracono, więc przyczyny nie potwierdzamy. Po probe zaobserwowano
quarantine=1; poprawka core cleanup typowanego błędu transportu i ponowny odbiór
pozostają blockerem końcowego odbioru. V1 pozostaje zamrożone; final-answer
contract v2 jest oddzielnym researchem.
