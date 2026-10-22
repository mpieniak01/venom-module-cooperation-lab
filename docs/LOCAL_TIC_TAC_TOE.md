# Lokalny scenariusz: kółko i krzyżyk

W ustawieniach wybierz „Kółko i krzyżyk”. Panel ustawia dialog i 9 tur;
A gra X i zaczyna, B gra O. Język instrukcji: wybrany polski lub angielski.
Plansza ma wiersze A/B/C i kolumny1/2/3. Model ma zwrócić jedno pole, np. B2.
Opcjonalny envelope JSON nadal działa, jeżeli content zawiera wyłącznie pole.

Przed każdą turą host przekazuje aktualną planszę. Deterministyczny sędzia
sprawdza kolejność, zakres, wolne pole, osiem linii zwycięstwa i remis.
Wynik nie zależy od deklaracji complete modelu. Koniec partii zatrzymuje
następną generację; STOP i istniejący cleanup pozostają dostępne.
Nielegalny ruch kończy próbę jawnym błędem, bez ukrytego retry lub poprawiania
odpowiedzi. Wiadomość błędna pozostaje widoczna, ale nie jest przekazywana dalej.

Plansza i wynik są trwałymi zdarzeniami game, odtwarzanymi w historii/SSE.
Budżet dziewięciu tur dotyczy tylko tej gry; pozostałe scenariusze nadal mają
maks.8. Krótszy limit operatora może zakończyć próbę nierozstrzygniętą.
Gra jest oddzielnym scenariuszem, poza zamrożoną rubryką benchmarku v1.
Zmiana wyłącznie lokalna, bez GH/PR. Testy CPU nie dowodzą umiejętności gry modelu.

## Odbiór lokalny

`make check HOST=/home/ubuntu/venom`: 289 Python PASS (97,37%),
21 frontend PASS (97,12%), Ruff/mypy/TS/lint i kontrakty hosta PASS.
Dwie deprecjacje narzędzi pozostają ostrzeżeniami.
Testy zawierają wszystkie osiem linii wygranej, zwycięstwo obu stron, pełny remis,
błędny ruch i zajęte pole, brak mutacji po odmowie, ignorowanie przedwczesnych
deklaracji complete, zapis planszy i zgodność sekwencji, cleanup oraz 9 tur.

Lokalne API udostępnia cztery scenariusze. Rzeczywisty browser smoke:
Kółko i krzyżyk / Gra naprzemienna / 9 tur / Polski, dziewięć pól planszy,
„Następny ruch: A (X)”, 0 pageerror. Nie klikano START — testy gry używały
jawnych adapterów CPU fixture, nie dowodzą poprawnych ruchów rzeczywistego modelu.
Wdrożono lokalny moduł i kopię UI; odświeżono tylko API przy pustym runtime.


## Warianty celu gry

- Gra naprzemienna (`dialog`): dotychczasowe instrukcje, wybór legalnego pola.
- Gra, aby wygrać (`game_competitive`): jawny cel zwycięstwa, sprawdzanie własnej
  wygranej i blokowania przeciwnika oraz dążenie do remisu, gdy nie można wygrać.

Oba warianty dostają tę samą aktualną planszę i mają identyczne limity oraz
parametry generacji. Host nie podpowiada ruchów ani nie zastępuje decyzji modelu.
Cel zostaje zapisany w niezmiennej konfiguracji próby; stare partie pozostają
wariantem naprzemiennym. Instrukcje nowego wariantu obsługują PL/EN, etykiety UI
PL/EN/DE. Zakres przygotowany do publikacji jako wspólny PR wariantów gry.


### Jawny stan pól — board-context-3

Każda tura obu wariantów otrzymuje planszę oraz listy pól zajętych przez X,
zajętych przez O i dozwolonych wolnych pól. Instrukcja zabrania nadpisywania także
własnego znaku. Listy powstają z tego samego stanu sędziego, bez rankingu ruchów,
automatycznej zamiany odpowiedzi lub ukrytych powtórek. Historyczne próby zachowują
swój numer wersji. Powodem zmiany są cztery próby Gemma4 zakończone błędem zajętego
pola w czwartej turze; sama nowa instrukcja nie dowodzi poprawy jakości modelu.


## Odbiór i ograniczenia

Operator potwierdził 2026-10-22 poprawne działanie Gemma4 po wprowadzeniu jawnych
list pól. To odbiór użytkowy, nie dowód optymalnej strategii ani wynik benchmarku.
RWKV7 0,4B w próbie tego samego dnia zwrócił w drugiej turze opis zamiast jednego
ruchu; sędzia prawidłowo odrzucił odpowiedź jako invalid_game_move. Nie maskujemy
tego ograniczenia skracaniem lub automatycznym poprawianiem odpowiedzi.

Walidacja końcowa: make check HOST=/home/ubuntu/venom — 327 Python PASS,
coverage 97,56%, 28 frontend PASS, Ruff/mypy/TypeScript/lint i kontrakt hosta PASS.
Pełne partie PL/EN obu wariantów sprawdzono przez produkcyjny guard kontekstu
z kontrolowanym transportem bez generacji LLM. Brak nowych zależności i zmian core.
