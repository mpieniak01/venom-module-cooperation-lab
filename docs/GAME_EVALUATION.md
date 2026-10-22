# Ewaluacja gier L7 — lokalny operator

Stan: implementacja i wdrożenie lokalne na `codex/rwkv7-g1k-2.9b`.
Nie utworzono ani nie opublikowano PR L7. Dotychczasowa zakładka rozmów/serii
pozostaje dostępna. Nowy protokół `game-eval-v2` nie zmienia starych wyników.

## Uruchomienie

1. Otwórz `/cooperation-lab` i wybierz **Ewaluacja gier**.
2. Wybierz model oraz przypadki TTT, Nim, Memory lub Sokoban.
3. Ustaw powtórzenia, pamięć, generację i limity. **Sprawdź konfigurację**
   pokazuje plan i przyczynę ewentualnej blokady. Każda zmiana wymaga nowego sprawdzenia.
4. **Rozpocznij serię** uruchamia jeden model przez wspólną blokadę zasobów Venoma.
   **Zatrzymaj serię** przerywa własne obliczenia; zwolnienie zasobu czeka na unload.
5. Wyniki, surowe odpowiedzi i decyzje są w historii. Eksport JSON/JSONL/CSV
   zapisuje również stare podejścia bloków. **Usuń serię** usuwa zakończony zapis
   jednym kliknięciem. Aktywnej serii ani zajętego runtime nie można usunąć.

Przy błędzie infrastruktury **Wznów serię** zachowuje identyfikator i konfigurację.
Nie powtarza zatwierdzonych epizodów fresh; carry restartuje cały uszkodzony blok.
Poprzednie podejście zostaje w `attempt_history`. Niedozwolony ruch lub zły format
nie uruchamiają automatycznie drugiej szansy. Wznowienie po zmianie modelu,
checkpointu lub reguł jest blokowane; należy utworzyć nową serię.

## Format odpowiedzi

Nowe próby w formularzu domyślnie używają **Mapowania odpowiedzi**.
**Ścisły JSON** pozostaje do porównania; API bez response_mode i historyczne
konfiguracje zachowują tryb ścisły. Tryb jest częścią zapisanej konfiguracji.

Mapowanie action-map-v1 zamienia wyłącznie jednoznaczną odpowiedź na akcję:
np. move right → obiekt move, take 1 stone from heap 0 → heap/take.
Obsługuje również uzgodnione koperty JSON move/value, pojedynczy blok json
i końcową odpowiedź po zamkniętym think. Nie wybiera ruchu za model, nie zgaduje
indeksów i nie naprawia ruchów niedozwolonych. Niejednoznaczność lub brak końcowej
akcji nadal kończą próbę. Surowy tekst i response_mapping zostają w dzienniku.
Wyników ścisłego JSON i mapowania nie należy mieszać bez oznaczenia trybu.

[Odbiór i ograniczenia mapowania](ACTION_MAPPING_20261022.md).

## Pamięć i interpretacja

- `history_replay`: przed decyzją reset i pełna dozwolona historia własnej sesji.
- `native_incremental`: rzeczywisty stan RWKV, izolowany dla A/B; backend dostaje
  tylko nowy przyrost. HRM/Huginn nie deklarują tego trybu.
- `fresh`: nowa historia i stan przed każdym epizodem.
- `carry`: zachowanie zadeklarowanej pamięci w obrębie gry/strony. Końcowy stan
  publiczny i wynik poprzedniej partii trafiają raz do sesji. Opcjonalna notatka
  jest odpowiedzią modelu na własne doświadczenia, bez podawania rozwiązań solvera.

Wagi pozostają zamrożone. Zmienność ruchów ani poprawa w kilku partiach nie jest
sama w sobie dowodem trwałego uczenia. Deterministyczne dekodowanie może powtarzać
ruchy; sampling oraz seed są jawne i porównywalne między modelami.

Reguły i schemat akcji podawane są raz na gracza/blok; kolejne obserwacje zawierają
aktualny stan. W Memory lista wszystkich 120 par jest zapisana równoważnie jako
wybór dwóch różnych indeksów spośród niesparowanych kart. Nie ujawnia to ich
wartości. Historia nie jest potajemnie skracana. Przekroczenie kontekstu daje
`context_limit`. Długi blok carry może celowo wyczerpać ograniczenie 2048 tokenów.

## Modele i budżety

RWKV-7, HRM-Text i Huginn korzystają z istniejących, zakwalifikowanych adapterów.
Modele istniejącego adaptera Ollama (w tym Gemma4) obsługują history_replay
oraz fresh/carry przez historię tekstową; nie deklarują natywnego stanu ani iteracji.
Adapter zachowuje weryfikację checkpointu/runtime/template, izolację graczy
i konserwatywny limit kontekstu. Sam wpis w katalogu nie kwalifikuje modelu.
Lista pokazuje również inne modele katalogu, ale brak adaptera protokołu v2
blokuje START z przyczyną. Nie następuje niewidoczna zamiana modelu.
Huginn stosuje rzeczywiste `num_steps` 8/16/32/64; pozostałe modele raportują
zastosowane iteracje jako brak danych. Każda decyzja ma jeden limit odpowiedzi
(8–256 tokenów) i czasu (1–90 s), bez ponawiania decyzji ani zmiany wybranego ruchu przez parser.

**Ograniczenie obecnego odbioru:** modele mogą odpowiedzieć rozumowaniem lub
niepoprawnym JSON. Ruch jest wtedy `invalid_format`, a nie poprawną grą.
Próby RWKV/HRM z budżetami 64/256 tokenów nie potwierdziły obsługi ścisłego JSON
w wybranych scenariuszach; Huginn miał także timeouty i niedozwolony ruch.
Nie deklarujemy zaliczonej jakości strategii ani poprawy dzięki carry.
Surowych wyników nie należy zestawiać bezpośrednio z dawnymi współrzędnymi TTT,
gdzie maskowanie wymuszało legalną odpowiedź. Wyniki odbioru są oddzielone od
zaliczenia technicznej poprawności środowiska.

## Reguły i odniesienia

Manifest `suite-v1` zawiera 13 przypadków. TTT używa lokalnego sędziego/minimax;
Nim — nim-sum i legalnego bota losowego; Memory — jednoosobowe pary 4×4 i bota
pamiętającego tylko ujawnienia; Sokoban — trzy stałe plansze z jedną skrzynią,
każda potwierdzona dokładnym solverem. Nie pobieramy generatorów ani datasetów.
Adaptacje Nim/Memory: TextArena MIT, opis i licencja w `THIRD_PARTY_NOTICES.md`.

Model–bot zamienia badaną stronę. Model–model naprawdę zamienia rozpoczynającego
A/B. Memory i Sokoban mają tylko jednego gracza. Boty/solvery nie podpowiadają
modelowi ruchów. Oceny `assessment` służą wyłącznie raportowi.

`wins/draws/losses` w grach przeciw botowi odnoszą się do badanej strony.
Pominięte i błędne próby pozostają w licznikach. Błędy modelu i infrastruktury
mają osobne kategorie. Koszty obejmują decyzje modeli, bez ruchów bota.
Brak tokenów/VRAM jest `null`, nie zerem. p95 to nearest-rank, z liczbą próbek.
Booleanowe metryki strategii są licznikami; pozostałe wartości mają średnią,
liczbę próbek i jawne `metric_aggregation` w eksporcie.

## Zapis, odtworzenie i granice

Ten sam kontrolowany namespace/SQLite hosta; bez plików modeli lub logów w Git.
Limity: wspólne 100 zapisów prób/serii, retencja 14 dni, 2 MiB na snapshot
i wspólne 512 MiB storage. Przy nowym START najstarsze zakończone zapisy są
rotowane automatycznie, razem z ich zdarzeniami. Aktywne próby i cleanup_pending
pozostają chronione; jeśli nie ma rekordu do zwolnienia, START zostaje odrzucony.
Rotacja i nowy zapis są jedną transakcją — nieudany zapis nie usuwa starej próby.
Plan: do 128 epizodów / 384 akcji / 1800 s; frontend pokazuje plan i zajętość.
Osiem zakończonych snapshotów może zostać w cache, ale usunięcie/retencja SQLite
nadal blokuje ich odczyt. API odczytu nie tworzy tabel ani nie ładuje modelu.
Eksport jest generowany w pamięci; operator odpowiada za swoje pobrane kopie.

Eksport JSON zawiera definicje przypadków i seed. Można odtworzyć legalne akcje
bez runtime przez `evaluation.replay.replay_episode(snapshot, episode)`.
Funkcja sprawdza zgodność końcowego wyniku i odrzuca zmieniony zapis.
Przy carry bez trwałego snapshotu tensorów wznawiamy cały blok, jawnie jako nowe
podejście; nie udajemy kontynuacji utraconego stanu natywnego.

Nowa gra wymaga implementacji Environment w `evaluation/games.py`, referencji,
wersjonowanego przypadku w `manifest.py`, testów legalności/widoczności/replay
oraz tłumaczeń panelu. Metadane testów aktualizujemy celami `test-catalog-sync`
i `test-groups-sync`; pełna bramka to `make pr-fast HOST=/home/ubuntu/venom`.
