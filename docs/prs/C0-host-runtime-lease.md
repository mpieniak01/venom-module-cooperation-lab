# C0 — publiczny kontrakt zasobów LLM

Status: PLAN, nie istniejący numer PR. Repo implementacji: mpieniak01/Venom. Zależność: plan; może powstawać równolegle z L1.

## Problem i wynik

RuntimeExclusiveGuard zabezpiecza benchmarki, ale nie dowiedziono objęcia czatu/Council/daemon/start-stop-switch. Lokalny mutex modułu nie zapewnia wyłączności całego hosta.

## Zakres

Mapowanie wszystkich konsumentów, następnie reużycie istniejącego publicznego admission lub minimalny ogólny lease hosta. Owner/run/engine/model i stan zajętości nie są polami sterowanymi przez model. Generation/load/unload/switch respektują ownership. Konflikt ma czytelny wynik; brak podmiany selekcji chatu i blanket timeoutu. Lease nie znika tylko dlatego, że wygasł HTTP/TTL przy nadal pracującym workerze. Cancel dotyczy własnej pracy; potwierdzony koniec albo quarantine/recovery. Restart oraz single-host/worker topology muszą być zdefiniowane i egzekwowane. Private singleton nie jest publicznym kontraktem.

## Walidacja

Równoczesny chat/benchmark/lab, switch podczas generacji, niewłaściwy owner, cancel/late completion, podwójny release, restart, awaria adaptera i powrót do dostępności. Jedna krótka realna próba końca inferencji, istniejące regression contracts, typing i make pr-fast core. Jeśli obecny mechanizm spełnia WSZYSTKIE kryteria, dokumentować reużycie zamiast tworzyć nowy lock.

Poza zakresem: eksperymenty/GUI/scenariusze w core, trening, zmiany Rider i globalny timeout czatu. Ten PR nie wdraża laboratorium.

## Kryteria zamknięcia

- [ ] Zakres i zależności zgodne z planem; actual SHA hosta/modułu/adaptera zapisane.
- [ ] Testy rzeczywiście wykonane, wyniki i skips jawne. Fixtures nie zastępują wymaganej inferencji.
- [ ] Brak auto-download, zmiany globalnego modelu, kopii sekretów lub pozornego PASS.
- [ ] Review i wymagane bramki, dokumentacja i sprawdzalny rollback.

Kontrakty: [CONTRACTS](../CONTRACTS.md). [Plan](../PLAN.md), [pełny odbiór](../ACCEPTANCE.md).
