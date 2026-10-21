# L3 — dwie sesje i runner komunikacji

Status: ZAIMPLEMENTOWANY LOKALNIE, oczekuje integracji zależności i przeglądu. Repo: venom-module-cooperation-lab. Zależności: L1, C0, L2.

## Problem i wynik

Uczestnicy muszą mieć osobne konteksty i faktycznie otrzymywać wiadomości, bez narzuconego podziału ról.

## Zakres

Immutable RunConfig; dwóch uczestników jednego checkpointu; fair/sequential scheduler, max1 aktywny run/request. Wersjonowany envelope, nadawca przypisany przez runner, adresat A/B/all, in_reply_to, turn/seq i journal przed emisją. Propozycje organizacji pochodzą z modelu. Complete nie zastępuje ewaluacji. Budżety tur/tokenów/kontekstu/czasu/kroków/bajtów i efektywne usage.

API start/cancel/snapshot/events/SSE/export/delete z ograniczeniami i host guards. Idempotency key, retry i dwie karty bez drugiej generacji. Persisted state machine i interrupted po restarcie bez auto-resume. Cancel blokuje następny krok i czeka na faktyczne zakończenie zgodnie z C0. Bounded catch-up oraz jawny resync gdy historia niepełna. Bez dowolnego shell/exec i podszywania nadawcy przez treść.

## Walidacja

Rozdzielona informacja A/B, prawdziwy odbiór i odpowiedź, nieprzeciekanie stanu, double start, cancel w każdej fazie i late completion, crash/restart, błędy envelope/odbiorcy/modelu, storage full, seq/duplikaty, limity i cleanup. Jedna krótka realna wymiana nowego zakwalifikowanego modelu. Nie wymagać przewagi jakości, wymagać rzeczywistej komunikacji.

Poza zakresem: GUI, kolejne modele, więcej uczestników i trening.

## Kryteria zamknięcia

- [ ] Zakres i zależności zgodne z planem; exact SHA hosta/modułu/adaptera zapisane.
- [ ] Testy faktycznie wykonane; wyniki, ograniczenia i skips jawne.
- [ ] Brak auto-download, sekretów w Git, pozornej współpracy i manual PASS.
- [ ] Review i wymagane bramki zakończone; dokumentacja i rollback.

Kontrakty: [CONTRACTS](../CONTRACTS.md). [Plan](../PLAN.md), [pełny odbiór](../ACCEPTANCE.md).


## Implementacja

Kod i zamrożony protokół opisuje [RUNNER](../RUNNER.md). Publiczny JSON pochodzi
z rzeczywistego backendu, nie wymyślonej makiety. Scenariusze mają scenario_id i
wersję string "1"; kwalifikacje live pozostają osobną procedurą hosta.

Lokalna pełna regresja L1/L2/L3: 129 pytest PASS, coverage 97.07%; Ruff PASS,
mypy 18 źródeł PASS (po końcowej korekcie typu receipt). Testy używają bounded CPU
fixtures i realnego C0 ledgeru, nie twierdzą, że wykonano inferencję GPU. Pełna
integracja frontu/CI/Sonar i realny odbiór L5 pozostają do wykonania przez
koordynatora po scaleniu C0 oraz L2. Nie uruchamiano urządzenia ani modeli.
