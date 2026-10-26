# Ewaluacja gier L7 — lokalny operator

Stan: implementacja i wdrożenie lokalne na `codex/rwkv7-g1k-2.9b`.
Nie utworzono ani nie opublikowano PR L7. Dotychczasowa zakładka rozmów/serii
pozostaje dostępna. Nowy protokół `game-eval-v2` nie zmienia starych wyników.

## Uruchomienie

1. Otwórz `/cooperation-lab` i wybierz **Ewaluacja gier**.
2. Wybierz model oraz przypadki TTT, Nim, Memory lub Sokoban.
3. Wybierz model, grę, wariant i powtórzenia. Pozostałe parametry oraz opcjonalny
   podgląd planu znajdują się w **Ustawieniach zaawansowanych**.
4. **Rozpocznij serię** automatycznie sprawdza aktualne ustawienia i uruchamia jeden
   model przez wspólną blokadę zasobów Venoma. Osobne sprawdzenie nie jest wymagane.
   Błąd pozostawia formularz otwarty i pokazuje przyczynę przy przycisku START.
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

Mapowanie action-map-v2 zamienia wyłącznie jednoznaczną odpowiedź na akcję:
np. move right → obiekt move, take 1 stone from heap 0 → heap/take.
Memory przyjmuje również parę indeksów jako tablicę [I,J]; Nim zapis heap=H take=N.
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
`context_limit`. Budżet wynosi domyślnie 2048; zweryfikowana Gemma4/Ollama w v2 może użyć
do 16384 przez pole Budżet kontekstu. RWKV do 8192; HRM/Huginn do 4096.
Historia nie jest obcinana; konserwatywny limit bajtowy Ollama może zatrzymać
próbę wcześniej niż rzeczywisty limit tokenów. [Wyniki Nim/Memory](NIM_MEMORY_FORMAT_20261022.md).

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
(8–1024 tokenów) i czasu (1–300 s), bez ponawiania decyzji ani zmiany wybranego ruchu przez parser.

**Ograniczenie obecnego odbioru:** modele mogą odpowiedzieć rozumowaniem lub
niepoprawnym JSON. Ruch jest wtedy `invalid_format`, a nie poprawną grą.
Próby RWKV/HRM z budżetami 64/256 tokenów nie potwierdziły obsługi ścisłego JSON
w wybranych scenariuszach; Huginn miał także timeouty i niedozwolony ruch.
Nie deklarujemy zaliczonej jakości strategii ani poprawy dzięki carry.
Surowych wyników nie należy zestawiać bezpośrednio z dawnymi współrzędnymi TTT,
gdzie maskowanie wymuszało legalną odpowiedź. Wyniki odbioru są oddzielone od
zaliczenia technicznej poprawności środowiska.

## Limity pamiętane dla modelu

Wybór modelu automatycznie przywraca jego ostatnio zapisany kontekst, tokeny
odpowiedzi i czas decyzji. **Zapisz limity modelu** utrwala je w Venomie;
niezapisane zmiany nie przechodzą na inne modele. Profile przetrwają odświeżenie
strony. Bez wcześniejszego zapisu model korzysta z wartości domyślnych.
[Analiza, zakres i odbiór profili](MODEL_BUDGET_PROFILES_20261022.md).

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

## Wybór gry w panelu

Otwórz /cooperation-lab → Gry — Nim, Memory, Sokoban → Ustawienia serii.
Pole „Wybierz grę” udostępnia Kółko i krzyżyk, Nim, Memory i Sokoban
z aktualnego manifestu API. Wybór zaznacza wszystkie przypadki tej gry;
można odznaczyć poszczególne przypadki. „Wiele gier / wybór przypadków”
zaznacza cały dostępny zestaw do dalszej ręcznej selekcji.
Wybranie gry zachowuje model i jego budżety, unieważnia wcześniejszy preflight
i niczego automatycznie nie uruchamia. Następnie wybierz model, sprawdź
konfigurację i naciśnij „Rozpocznij serię”.

Odbiór lokalny 2026-10-22: make pr-fast HOST=/home/ubuntu/venom PASS
(663 Python, 46 frontend, coverage 96,93%, zmienione linie 96,11%).
Playwright: rzeczywisty wybór Nim/Memory/Sokoban zaznacza wyłącznie ich
przypadki; 0 błędów konsoli, pozostają ostrzeżenia powłoki hosta.
Oficjalny mirror zsynchronizowany, bez restartu API i bez generacji modeli.


### Odzyskanie po przerwanym żądaniu Ollama

Jeżeli seria pozostała w oczekiwaniu na zwolnienie zasobu, wybierz ją w historii
i użyj **Sprawdź i zwolnij zasób**. Endpoint sprawdza zgodność właściciela i ID
serii, zakończenie lokalnych zadań oraz trzy kolejne puste odczyty Ollama `/api/ps`.
Nie zwalnia aktywnych operacji. Po restarcie API stan jest dostępny do odzyskania
wyłącznie po potwierdzeniu zakończenia procesu poprzedniego właściciela.
Brak dostępu do procesu lub brak odpowiedzi Ollama pozostawia blokadę.

W mapowaniu kółka i krzyżyka Ollama otrzymuje schemat formatu JSON obejmujący
wszystkie dziewięć współrzędnych. Schemat nie usuwa zajętych pól ani nie wybiera
ruchu: zajęte pole nadal kończy próbę jako `illegal_action`. Parametry próbkowania
operatora są zachowane. W raporcie zapisuje się `response_format=tic_tac_toe_json`,
`allowed_outputs=[]` i politykę promptu `mapped-game-v4`; stare przebiegi pozostają
bez zmian i nie są wznawiane z inną polityką promptu.


Zwykłe próby w zakładce **Rozmowa i serie** przyjmują teraz również od 1 do 1024
tokenów na turę we wszystkich adapterach; limity całej próby rosną wraz z wybranym
budżetem. Zmiana 128 → 1024 po zakończeniu poprzedniej próby nie wymaga ponownej
kwalifikacji modelu. Budżet odpowiedzi nadal dzieli kontekst z promptem i historią;
przekroczenie kontekstu jest raportowane oddzielnie. Odrzucony formularz pokazuje
kod `invalid_parameters`; log zawiera tylko nazwy nieprawidłowych pól.


### Zbyt duży budżet odpowiedzi — lokalna poprawka 2026-10-23

Wpisywanie wartości nie zmienia pola. Po kliknięciu START zbyt duża liczba jest
ograniczana do lokalnego limitu wybranego modelu; formularz pokazuje zastosowaną
wartość i próba rozpoczyna się w tym samym działaniu. Dotyczy zwykłych prób oraz
ewaluacji gier. Sprawdzenie konfiguracji pozostaje bez uruchamiania modelu i bez
zmiany wpisu. Szczegóły polityki, zakres i dowód odbioru:
[budżety modeli i start](MODEL_BUDGET_UNIFICATION_PLAN_20261023.md).


Próba, do której nadal odwołuje się dzierżawa runtime, pozostaje chroniona przed
usunięciem także po restarcie API. Najpierw potwierdź zakończenie obliczeń.
Odrzucony START nie tworzy rekordu ani nie uruchamia rotacji historii, więc nie
usuwa próby potrzebnej do odzyskania. Startup recovery-only otwiera magazyn pod
wyłączną ochroną przestrzeni hosta i transakcji ledgeru, również w kwarantannie.

Po restarcie odzyskiwanie ewaluacji używa zapisanej tożsamości wykonawcy
(provider/artifact) oraz zgodnej dzierżawy. Nie wymaga ponownego wykrycia ani
instalacji usuniętego tagu Ollama. Brak poprawnej zapisanej tożsamości pozostawia
kwarantannę; nadal wymagane są trzy puste odpowiedzi `/api/ps`.


## Warianty kółka i krzyżyka — 2026-10-26

W zakładce ewaluacji wybierz **Kółko i krzyżyk**, a następnie pole
**Wariant kółka i krzyżyka**. Sam wybór nie uruchamia modelu.

- **Samodzielna** (`standard`, również domyślny wariant starszych zapisów):
  model sam wybiera ruchy; dotychczasowe ustawienia pozostają dostępne.
- **Z refleksją po partii** (`reflection`): formularz ustawia carry, notatkę
  po partii i co najmniej trzy powtórzenia. API wymaga co najmniej dwóch.
  Po zakończeniu partii model dostaje maksymalnie trzy własne ruchy obniżające
  ocenę minimaksu: planszę, propozycję, ocenę i lepszy ruch. Następnie zapisuje
  prywatną notatkę do historii swojego bloku. Podpowiedzi nie trafiają do decyzji
  przed zakończeniem partii. Wagi pozostają zamrożone; to coaching w kontekście,
  bez treningu ze wzmocnieniem i bez gwarancji poprawy.
- **Ze wsparciem solvera** (`assisted`): minimaks zastępuje tylko legalny ruch
  obniżający wartość pozycji. Ruch optymalny pozostaje bez zmian; zły format lub
  nielegalna akcja nadal kończą epizod błędem. Nie ma ponownej generacji LLM.
  Model otrzymuje informację o swojej poprzedniej interwencji w kolejnej turze.

W dzienniku `model_action` oznacza propozycję, `action` ruch wykonany,
`assessment` ocenę pierwotnej propozycji, a `execution_assessment` ocenę ruchu
po wsparciu. `assistance.applied` i podsumowanie `solver_interventions`
wskazują interwencje. Wynik partii wspomaganej ma `result_scope=assisted`;
metryki błędów nadal dotyczą modelu. Nie porównuj takiego wyniku bezpośrednio
z samodzielną grą. JSON/JSONL zachowują pełny ślad, a replay używa wykonanych
ruchów. Wersja strategii jest zapisana i sprawdzana przy wznowieniu serii.

Nowe warianty dotyczą wyłącznie przypadków TTT. Ustawienia dekodowania,
kontekstu, tokenów i kroków Huginn są jawne i nie są zmieniane przez wybór
wariantu. Korzystają ze ścieżki ewaluacji v2, bez historycznego wymuszania
legalnych współrzędnych ze zwykłych serii v1. Nie uruchamiają treningu wag.


## Podgląd na żywo w „Rozmowa i serie” — 2026-10-26

Dla pojedynczej gry lub krótkiej obserwowanej serii użyj **Rozmowa i serie →
Scenariusz: Kółko i krzyżyk → Wariant**. Nowe pozycje:
**Samodzielna strategia**, **Strategia z refleksją** oraz
**Strategia ze wsparciem solvera**. Start odbywa się zwykłym przyciskiem
**Rozpocznij eksperyment**, bez osobnego preflight.

Plansza pokazuje faktycznie wykonane ruchy i liczniki propozycji modelu,
pogorszeń pozycji, pominiętych wygranych oraz interwencji. W wiadomościach
widnieją osobno propozycja modelu i wykonany ruch. Wariant wspomagany jest
wyraźnie oznaczony; interwencja CPU nie generuje kolejnej odpowiedzi LLM.
Nielegalna propozycja lub niejednoznaczny format nadal kończą próbę błędem.

Refleksja ustawia trzy gry i pamięć, wymaga minimum dwóch pełnych partii.
Po każdej partii każdy gracz osobno dostaje wynik i maksymalnie trzy własne
błędy wraz z lepszymi ruchami. Generuje krótką prywatną notatkę widoczną przy przebiegu bieżącej partii
po lewej stronie. Do następnej gry trafia wyłącznie własna notatka danego gracza;
wynik i ruchy poprzednich gier są publiczne. Generacje notatek są rozliczane,
podlegają STOP, wspólnej dzierżawie oraz budżetom. Nie są treningiem wag.

Nowe warianty używają rzeczywistych ustawień temperatury/top-p i nie maskują
listy legalnych współrzędnych. Krótka odpowiedź jest mapowana do pojedynczego
ruchu bez zgadywania. Historyczne „Gra naprzemienna” i „Gra, aby wygrać”
zachowują dotychczasowy protokół oraz sposób dekodowania. Nowe konfiguracje
mają schema_version=5 i scheduler=live-game-strategy-v1. Historia/eksport
zawierają zdarzenia planszy, propozycje, oceny, interwencje i refleksje.

Zakładka **Gry i strategie** pozostaje osobną ścieżką ewaluacji hurtowej.
Ten etap dotyczy podglądu i wariantów w **Rozmowa i serie**.


W „Rozmowa i serie” lewa kolumna pokazuje planszę, wiadomości i notatki
aktualnej partii, także po jej zakończeniu. Po rozpoczęciu następnej partii
przebieg po lewej przełącza się na nią. Po prawej, pod „Propozycje organizacji”,
znajdują się historia prób oraz panel „Wyniki serii”: tabela statystyk strategii,
bilans A/B/remis i tabela partii z wynikiem oraz liczbą ruchów. Panel wyników
nie zawiera kopii rozmów. Zapisane dane i eksporty pozostają bez zmian.
