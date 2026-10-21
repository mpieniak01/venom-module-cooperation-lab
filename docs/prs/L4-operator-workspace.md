# L4 — ekran obserwacji i kontroli współpracy

Status: kod lokalny L4, odbiór hosta i CI przed wydaniem. Repo: venom-module-cooperation-lab. Zależność: L3; projektowanie po zamrożeniu API może zacząć się wcześniej.

## Problem i wynik

Operator ma widzieć prawdziwy dialog, organizację i wynik, przy stabilnym układzie oraz dostępnych kontrolkach.

## Zakres

/cooperation-lab: cel, zakwalifikowany model, neutralni A/B, scenariusz/encouragement i budżet, START/STOP. Stałe pola uczestników/dialogu i propozycji/podziału pracy; koszty i parametry w detalach. Jawne współdzielenie wag i rzeczywisty runtime. Bez auto-startu po wejściu na ekran.

SSE po rzeczywistym smoke same-origin proxy bez buforowania; jeden kanał, reconnect Last-Event-ID/catch-up/dedup i snapshot przy luce. Dwie karty nie ponawiają startu. Lost connection nie oznacza końca inferencji. Cancelling do potwierdzonego końca. Historia i bounded export. A11y, i18n PL/EN/DE, responsive, długie treści bez skoków sterowania. Bez zmian ekranów Council/Inspector/Rider.

## Walidacja

Browser flow rzeczywistego hosta/modelu: start, wiadomość A/B z powiązaniem, STOP i cleanup, reconnect, history/result. Fixtures dla błędów/długich treści/wielu kart; typowanie/lint/unit, proxy streaming, brak dublowania subskrypcji, widoczne sterowanie. Jeśli proxy wymaga generycznej poprawki, oddzielny host hunk w C0 przed wydaniem.

Poza zakresem: dekoracyjny graf zastępujący dialog, nowy framework UI, automatyczne wyświetlanie rzekomych ukrytych myśli i trening.

## Kryteria zamknięcia

- [ ] Zakres i zależności zgodne z planem; exact SHA hosta/modułu/adaptera zapisane.
- [ ] Testy faktycznie wykonane; wyniki, ograniczenia i skips jawne.
- [ ] Brak auto-download, sekretów w Git, pozornej współpracy i manual PASS.
- [ ] Review i wymagane bramki zakończone; dokumentacja i rollback.

Kontrakty: [CONTRACTS](../CONTRACTS.md). [Plan](../PLAN.md), [pełny odbiór](../ACCEPTANCE.md).

Implementacja i użycie: [WORKSPACE](../WORKSPACE.md). Niezależny review poprawił wybranie archiwum podczas pracy, spóźnione odpowiedzi STOP, powiązanie potwierdzenia DELETE z ID, pending START/STOP i zgodność z rzeczywistym kontraktem L3.
