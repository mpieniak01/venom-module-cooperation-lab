# L7 — decyzja o wykorzystaniu istniejących gier

Data: 2026-10-22. Research zakończony; zaadaptowano ograniczony podzbiór reguł
Nim/Memory. Pochodzenie i MIT są w THIRD_PARTY_NOTICES.md oraz licenses/.
Bez instalacji całego frameworka; odbiór runtime opisujemy osobno.

## Gałąź i cały zaległy zakres

Po `git fetch origin`: aktywna **codex/rwkv7-g1k-2.9b**, czysty checkout,
HEAD `b14b72a`, 9 commitów ponad `origin/main` (`713cf68`). Nie jesteśmy na main,
więc nie ma potrzeby przenoszenia lub cherry-pickowania zmian na kolejną gałąź.
Dalszy L7 realizujemy na tej wspólnej gałęzi; jej historyczna nazwa nie ogranicza
zakresu PR. Nie opublikowano ani nie scalono tych commitów w ramach tego researchu.

| Commit | Zachowany zakres |
|---|---|
| 100813a | Model RWKV-7 2.9B |
| 12469bc | Stan RWKV i formaty odpowiedzi |
| 8b98e20 | Dekodowanie legalnych współrzędnych |
| 41580b5 | Research Huginn/HRM/CTM |
| 1133500 | Przypięte adaptery HRM/Huginn |
| db8fc08 | Adaptacja i rzeczywista kwalifikacja obu modeli |
| e354522 | Usuwanie jednym kliknięciem |
| c7e11cc | Serie gier i ograniczona pamięć tekstowa |
| b14b72a | Plan L7 i backlog |

Zmiany core są lokalnie wygenerowane: rejestracja `cooperation_lab` w dwóch
plikach `optional-*.generated*` oraz dodatkowy import `root-params.d.ts` w
`next-env.d.ts`. To wynik uruchomienia panelu/generatora, nie osobna ręcznie
napisana implementacja funkcji. Zachowane na dysku; nie przenosimy ich ślepo do
repo modułu i nie cofamy działającej rejestracji. Wdrożenie odtwarza oficjalny
`web-next/scripts/prepare-optional-module-node-paths.mjs`.

## Przejrzane rozwiązania

| Projekt | Co już zawiera | Dopasowanie / decyzja |
|---|---|---|
| TextArena | TTT, Nim, MemoryGame, Sokoban; tekstowy interfejs dla LLM; MIT | Główne źródło adaptacji wybranych reguł i testów referencyjnych |
| PettingZoo | TTT, stany graczy, maski legalnych akcji; MIT | Dodatkowy wzorzec/test porównawczy, bez zastępowania stabilnego TTT |
| OpenSpiel | Nim/TTT i algorytmy gier; Apache-2.0 | Referencja merytoryczna; nie instalujemy C++/pyspiel dla tych kilku prostych gier |
| gym-sokoban | Ruch/pchanie i generacja pokojów; MIT | Źródło porównawcze; stary interfejs Gym i zestaw renderowania nie pasują do celu |
| POPGym Concentration | Jednoosobowy test pamięci kart | Referencja widoczności; domyślnie 52 karty, jedna karta na krok, inne zadanie niż nasze 16 kart / para na decyzję |

TextArena sprawdzono po konkretnym SHA:
`1e3160dea659971f120bf42708fafa8ea3001b81`.
Karta projektu deklaruje TextArena 0.7.3 / Python >=3.10. Nie potwierdzono
uruchomieniem zgodności całego pakietu z naszym Pythonem 3.14.8.

## Decyzja: adaptacja małego podzbioru, bez całego frameworka

Nie piszemy wszystkich reguł bez spojrzenia na istniejące produkty. Wykorzystujemy
sprawdzony lokalny TTT i adaptujemy niewielkie części logiki TextArena tam,
gdzie rzeczywiście oszczędzają kod. Własne pozostają kontrakt ewaluacji, parser
akcji, deterministyczny RNG, referencje, polityka pamięci, metryki i raporty.
Nie dodajemy TextArena jako zależności aplikacyjnej całego stosu.

Powody potwierdzone w źródłach:
- Pakiet TextArena ma obowiązkowe zależności openai, rich, nltk, chess,
  python-dotenv, requests i websockets. Importuje także API, agents, wrappers
  oraz katalog środowisk; nie potrzebujemy ich do deterministycznych reguł.
- Nim i pozostałe parsery używają `re.search`, co pozwala znaleźć ruch wewnątrz
  dłuższej wypowiedzi. Nasz v2 wymaga dokładnej pojedynczej akcji bez naprawy.
- TextArena State domyślnie dopuszcza jeden błędny ruch przed przegraną
  (`error_allowance=1`). Nasz kontrakt: jedna odpowiedź, brak drugiej szansy.
- State ustawia globalne `random.seed`; Memory korzysta z globalnego shuffle.
  U nas izolowane `random.Random(seed)` per przypadek/bot i bez wpływu na inne serie.
- MemoryGame jest dwuosobowe, z punktami i pozostawieniem tury po trafieniu.
  Nasza pierwsza wersja jest jednoosobowa i mierzy pominięte znane pary.
- Sokoban generuje planszę, ponawia generację do 50 razy i zmienia seed kolejnymi
  próbami. My używamy stałych wersjonowanych plansz potwierdzonych solverem.

### Co wykorzystać per gra

1. **TTT:** obecny lokalny sędzia. Dodać opakowanie wspólnego Environment,
   pozycje taktyczne, zamianę stron i ocenę minimax. PettingZoo/TextArena mogą
   dostarczyć niezależnych przebiegów porównawczych; nie kopiować ich mapowania
   pól bez jawnej konwersji (różne indeksowanie).
2. **Nim:** adaptować prostą walidację i zmianę stosów TextArena do typowanej
   akcji. Lokalny bot nim-sum i losowy z izolowanym RNG. Bez całego State TextArena.
3. **Memory:** adaptować parowanie/odsłanianie z jawnie oddzielonym ukrytym
   układem. Zmiana do jednego gracza i 16 kart jest obowiązkowa. Wiedza bota i
   metryki wyłącznie z ujawnionych obserwacji. Zachować testy niezależnych ujawnień.
4. **Sokoban:** wykorzystać istniejącą logikę ruchu/pchania jako bazę adaptacji.
   Zastąpić generator stałymi małymi planszami i dodać własny bounded BFS do
   referencji/deadlock. Bez obrazków, GUI, pobierania Boxobana i niejasnych danych.

Jeżeli adaptacja danego fragmentu kosztuje więcej niż mała własna funkcja,
wybrać własną funkcję z testem porównawczym i wskazać to uczciwie w provenance.
Nie oznaczać kodu „reuse”, jeśli tylko przeczytano cudze rozwiązanie.

## Warunki przejęcia kodu w implementacji

- Zamrozić SHA, dokładne ścieżki oraz hashe przejętych plików/fragmentów.
- Zachować pełną licencję MIT i copyright autorów TextArena w dystrybucji,
  dodać `THIRD_PARTY_NOTICES.md` i informację o lokalnych zmianach.
- Dla Sokobana sprawdzić pochodzenie adaptowanego fragmentu; jeśli pochodzi
  z gym-sokoban, zachować także copyright Max-Philipp Schrader i jego MIT.
- Nie kopiować grafik, datasetów, wygenerowanych plansz o nieustalonej licencji
  ani cudzych usług sieciowych. Plansze startowe lokalne, sprawdzone solverem.
- Utrzymywać testy reguł, deterministycznego replay, widoczności i jednorazowej
  odpowiedzi niezależnie od źródła kodu. Skanery obejmują również adaptowany kod.
- Nie instalować nowych wersji bibliotek/venv dla gier; logika CPU bez nowych
  ciężkich zależności. Własny adapter nie może ujawnić solvera lub ukrytego stanu.

## Źródła pierwotne

- [TextArena README środowisk](https://github.com/TextArena/TextArena/blob/main/textarena/envs/README.md)
- [Przypięta licencja TextArena](https://github.com/TextArena/TextArena/blob/1e3160dea659971f120bf42708fafa8ea3001b81/LICENSE)
- [Zależności TextArena](https://github.com/TextArena/TextArena/blob/1e3160dea659971f120bf42708fafa8ea3001b81/pyproject.toml)
- [Nim](https://github.com/TextArena/TextArena/blob/1e3160dea659971f120bf42708fafa8ea3001b81/textarena/envs/Nim/env.py)
- [Memory](https://github.com/TextArena/TextArena/blob/1e3160dea659971f120bf42708fafa8ea3001b81/textarena/envs/MemoryGame/env.py)
- [Sokoban](https://github.com/TextArena/TextArena/blob/1e3160dea659971f120bf42708fafa8ea3001b81/textarena/envs/Sokoban/env.py)
- [State — błędy](https://github.com/TextArena/TextArena/blob/1e3160dea659971f120bf42708fafa8ea3001b81/textarena/state.py)
- [Core — RNG](https://github.com/TextArena/TextArena/blob/1e3160dea659971f120bf42708fafa8ea3001b81/textarena/core.py)
- [PettingZoo TTT](https://pettingzoo.farama.org/environments/classic/tictactoe/)
- [OpenSpiel](https://github.com/google-deepmind/open_spiel)
- [gym-sokoban](https://github.com/mpSchrader/gym-sokoban)
- [POPGym Concentration](https://github.com/proroklab/popgym/blob/master/popgym/envs/concentration.py)
