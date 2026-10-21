# L1 — opcjonalny moduł, dane i bramki

Status: PLAN, nie istniejący numer PR. Repo: venom-module-cooperation-lab. Zależność: plan.

## Problem i wynik

Niezależny moduł musi mieć poprawną instalację i lifecycle, a brak/OFF/błąd nie może blokować core. Ekran na tym etapie pokazuje prawdziwe not_ready, nie fikcyjne eksperymenty.

## Zakres

Installable Python package, manifest cooperation_lab z data_policy, async bounded startup/shutdown, flagi OFF, router, dynamiczna trasa/menu i własne tłumaczenia PL/EN/DE. Health/capabilities bez ładowania modeli. Namespacowana SQLite z migracjami, fixed state_files (także WAL/SHM), guard tworzenia/mutacji i polityka dostępu. Zamrozić limity/retencję z CONTRACTS. Brak trwałych modeli lub danych research w Git.

Powtarzalne make check, backend Ruff/mypy/pytest z coverage >=90%, frontend TS/lint/unit oraz host module contract. Przypiąć obsługiwany host SHA/ABI i build/test contract frontu; nie instalować drugiego Next do core. Skonfigurować właściwe projekty i organizację Snyk/Sonar/GitGuardian, CI i review bez kopiowania tokenów/.env. Przy ograniczeniu planu stan jawny, nie ręczne PASS.

## Walidacja

Czysta instalacja, import bez GPU/sieci, brak repo/manifestu/flag/OFF, ABI mismatch quarantine, lifecycle z błędem/timeoutem, host policy odmowy, migracja i pełny dysk/retencja. Bez modelu, inferencji i rejestracji w działającej instancji operatora. Testy integracji w izolowanym profilu hosta, nie kopia całego środowiska.

Poza zakresem: generacja, model adapter, pokazywanie mocka jako działającej współpracy i instalacja ciężkich zależności.

## Kryteria zamknięcia

- [ ] Zakres i zależności zgodne z planem; actual SHA hosta/modułu/adaptera zapisane.
- [ ] Testy rzeczywiście wykonane, wyniki i skips jawne. Fixtures nie zastępują wymaganej inferencji.
- [ ] Brak auto-download, zmiany globalnego modelu, kopii sekretów lub pozornego PASS.
- [ ] Review i wymagane bramki, dokumentacja i sprawdzalny rollback.

Kontrakty: [CONTRACTS](../CONTRACTS.md). [Plan](../PLAN.md), [pełny odbiór](../ACCEPTANCE.md).
