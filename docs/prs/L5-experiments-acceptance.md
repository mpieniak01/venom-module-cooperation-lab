# L5 — samoorganizacja i pełny odbiór MVP

Status: PLAN, nie istniejący numer PR. Repo: venom-module-cooperation-lab. Zależności: L1–L4 i C0.

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
