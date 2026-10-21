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


## Poprawka po rzeczywistym browser smoke

Style krytyczne należą do modułu jako statyczny scoped CSS; zewnętrzna ścieżka
modułu nie musi być skanowana przez Tailwind JIT hosta. Własna wysokość uwzględnia
rzeczywisty top elementu w viewport, stałe kontrolki i notice są nad wewnętrznym
scroll body. Desktop od1024px: settings6kolumn i main+aside; START zielony,
STOP czerwony. Nie zmieniono globalnych stylów/layoutu core.

Wybrana próba synchronizuje formularz przed kolejnym paint z immutable config
(nested model.model_id i budgets), wyłącznie poprawne wartości. Test historii
Qwen 4tury/32tokeny/seed17/no_contact/correction zabezpiecza regres domyślnego
RWKV 8/128 w nieaktywnych polach. Node/JSDOM potwierdza kolory i overflow bez
Tailwind; rzeczywiste bounding boxes i media queries odbiera koordynator.

Node24 generuje rzeczywisty LCOV z tej samej sesji testów do
`test-results/lcov.info`, wskazanego przez sonar.javascript.lcov.reportPaths.
Bez wyłączeń pokrycia i zmiany progów. TS/lint oraz12testów PASS,95,28% line
coverage. Wynik Sonara/i18n CPD należy ocenić po actual skanie.
