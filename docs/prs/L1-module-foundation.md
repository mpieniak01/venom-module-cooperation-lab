# L1 — opcjonalny moduł, dane i bramki

Status: SCALONY przez PR #9, merge `d4797d7`. Fundament i jego bramki wydano; końcowy odbiór całej integracji opisuje RELEASE_ACCEPTANCE. Repo: venom-module-cooperation-lab. Zależność: plan.

## Problem i wynik

Niezależny moduł musi mieć poprawną instalację i lifecycle, a brak/OFF/błąd nie może blokować core. Ekran na tym etapie pokazuje prawdziwe not_ready, nie fikcyjne eksperymenty.

## Zakres

Installable Python package, manifest cooperation_lab z data_policy, async bounded startup/shutdown, flagi OFF, router, dynamiczna trasa/menu i własne tłumaczenia PL/EN/DE. Health/capabilities bez ładowania modeli. Namespacowana SQLite z migracjami, fixed state_files (także WAL/SHM), guard tworzenia/mutacji i polityka dostępu. Zamrozić limity/retencję z CONTRACTS. Brak trwałych modeli lub danych research w Git.

Powtarzalne make check, backend Ruff/mypy/pytest z coverage >=90%, frontend TS/lint/unit oraz host module contract. Przypiąć obsługiwany host SHA/ABI i build/test contract frontu; nie instalować drugiego Next do core. Skonfigurować właściwe projekty i organizację Snyk/Sonar/GitGuardian, CI i review bez kopiowania tokenów/.env. Przy ograniczeniu planu stan jawny, nie ręczne PASS.

## Walidacja

Czysta instalacja, import bez GPU/sieci, brak repo/manifestu/flag/OFF, ABI mismatch quarantine, lifecycle z błędem/timeoutem, host policy odmowy, migracja i pełny dysk/retencja. Bez modelu, inferencji i rejestracji w działającej instancji operatora. Testy integracji w izolowanym profilu hosta, nie kopia całego środowiska.

Poza zakresem: generacja, model adapter, pokazywanie mocka jako działającej współpracy i instalacja ciężkich zależności.

## Kryteria zamknięcia

- [x] Zakres i zależności zgodne z planem; actual SHA hosta/modułu/adaptera zapisane.
- [x] Testy rzeczywiście wykonane, wyniki i skips jawne. Fixtures nie zastępują wymaganej inferencji.
- [x] Brak auto-download, zmiany globalnego modelu, kopii sekretów lub pozornego PASS.
- [x] Review i wymagane bramki, dokumentacja i sprawdzalny rollback.

Kontrakty: [CONTRACTS](../CONTRACTS.md). [Plan](../PLAN.md), [pełny odbiór](../ACCEPTANCE.md).


## Wynik implementacji L1 (2026-10-21)

Pakiet, manifest, namespace SQLite i własny szkielet UI są dostępne. Moduł nadal
OFF, bez rejestracji w żywej instancji i bez modeli. Szczegóły oraz rollback:
[FOUNDATION](../FOUNDATION.md). Zamrożone limity i poprawne rozróżnienie ABI 1.0.0
od runtime 1.6.0 znajdują się w CONTRACTS.

Wykonane lokalnie: 32 pytest PASS, pokrycie backendu 100%; 4 testy frontendowe
PASS, LCOV 100% dla wykonywanego UI; Ruff/mypy/TS/ESLint/host module contract
PASS. Zbudowany wheel 9.4KB przeszedł import w czystym katalogu bez zapisów i bez
importu Torch/Transformers/RWKV. Artefakt tymczasowy usunięto. Realny Snyk CLI:
10 zależności, zero vulnerable paths w właściwej organizacji mpieniak01.

Sonar/Snyk CI i niezależna recenzja pozostają do wykonania po publikacji PR;
nie są oznaczone PASS. Dwie ostrzegawcze deprecacje pochodzą z istniejącego
TestClient hosta, bez błędów testów. Rzeczywisty dialog, kwalifikacja GPU i testy
SSE/operatora należą do L2–L5.


Aktualny odbiór i granice dowodów: [RELEASE_ACCEPTANCE](../RELEASE_ACCEPTANCE.md).
