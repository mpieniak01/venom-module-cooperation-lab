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


## Podgląd na żywo w „Rozmowa i serie”

Wybierz **Rozmowa i serie → Scenariusz: Kółko i krzyżyk → Wariant**:
**Samodzielna strategia**, **Strategia z refleksją** lub
**Strategia ze wsparciem solvera**. Start odbywa się przyciskiem
**Rozpocznij eksperyment**, bez osobnego preflight. Zakładka **Gry i strategie**
pozostaje osobną ścieżką ewaluacji hurtowej.

Lewa kolumna pokazuje planszę, wiadomości i refleksje aktualnej partii, również
po jej zakończeniu. Rozpoczęcie następnej partii przełącza przebieg po lewej.
Po prawej, pod „Propozycje organizacji”, są historia prób i „Wyniki serii”:
statystyki strategii, bilans A/B/remis oraz tabela partii z liczbą ruchów.
Wyniki nie zawierają kopii rozmów.

W wiadomościach propozycja modelu i wykonany ruch są zapisane osobno.
Nielegalna propozycja lub niejednoznaczny format kończą próbę błędem.
W refleksji i samodzielnej strategii ruch nie jest zmieniany przez hosta.
Wariant wspomagany jawnie oznacza interwencje CPU i `result_scope=assisted`;
wyników wspomaganych nie należy przypisywać samemu modelowi.

### Aktywny kontrakt live v4

Nowe warianty mają `schema_version=8`, `scheduler=live-game-strategy-v4`
i `strategy_version=ttt-coaching-v4`. Używają faktycznych ustawień
temperatury/top-p, bez wymuszania legalnej współrzędnej i bez ukrytych ponowień.
Historyczne „Gra naprzemienna” i „Gra, aby wygrać” zachowują swój protokół
oraz sposób dekodowania. Stare konfiguracje, wyniki i parsery batch nie są
retrospektywnie zmieniane.

HRM i Huginn otrzymują jawny profil angielski. `model_language` opisuje język
zadania, a `communication_language` zachowuje wejście operatora. HRM otrzymuje
dwa przykłady formatu pojedynczego ruchu. Dla Huginn w sekcji modelu można
wybrać 8/16/32/64 kroki; API sprawdza obsługiwaną architekturę, a `usage`
zapisuje faktyczną wartość. Historyczna próba bez `num_steps` przywraca 8 kroków.

RWKV i Huginn mają `observation_profile=explicit-cells-v1`: stan dziewięciu
komórek jest jawny (`A1=empty/X/O`). Huginn otrzymuje aktualny stan bez
redundantnego dawnego przekazu, przy zachowaniu pełnego dziennika dostarczeń.
RWKV nadal dopisuje kontekst rekurencyjny. W porównaniu kompresja pogorszyła
taktykę HRM, dlatego zachowuje on `board-and-peer-with-reminder-v1`:
dotychczasową planszę i ostatni przekaz przeciwnika. W każdym profilu własna
przyjęta reguła jest dodatkowo przypominana przy decyzji.

### Sprawdzanie refleksji i jej wykorzystania

Refleksja domyślnie ustawia trzy gry i pamięć; wymaga minimum dwóch pełnych
partii. Generacja notatek odbywa się **wyłącznie między partiami**. Po ostatniej
nie ma wywołań notatek. Rezerwa obejmuje maksymalnie `2 * (liczba_partii - 1)`
generacji. **Tokenów na notatkę** ma osobny limit 128 (zakres 32–256), niezależny
od limitu ruchu. Generacje podlegają STOP, admission i wspólnym budżetom.

Model wybiera regułę `win_now` lub `block_win` z jawnego katalogu hosta.
Host sprawdza jej politykę na rzeczywistym własnym błędzie gracza oraz ośmiu
obrotach/odbiciach planszy. Bezpośrednia wygrana ma pierwszeństwo przed blokiem.
Reguła bloku wymaga braku własnej wygranej i pojedynczego bezpośredniego zagrożenia.
Pominięta natychmiastowa wygrana może być lekcją także bez spadku minimax,
jeśli model zachował możliwość wymuszonej późniejszej wygranej.

Katalog nie obejmuje wszystkich błędów pozycyjnych i forków. Bez wspierającej
lekcji notatka jest jawnie pominięta, bez generacji i bez liczenia jej jako
odrzuconej. Błędny format lub niepoparta reguła nie nadpisują poprzedniej pamięci.
Do następnej partii trafia tylko własna przyjęta reguła i maksymalnie trzy same
wyniki wcześniejszych gier, bez ich współrzędnych i surowych transkryptów.

`note_source=model_selected_host_catalog_rule` oznacza, że model wybrał regułę,
a jej opis pochodzi z katalogu. `validation.future_model_behavior_verified=false`
wyklucza traktowanie tej kontroli jako dowodu nauczenia się jej przez model.
UI odróżnia to od historycznej kontroli samego formatu notatki.

`rule-choice-map-v1` przyjmuje obiekt z jednym polem `rule_id`, pojedynczy jawny
identyfikator albo string JSON z identyfikatorem. Nie wybiera za model, nie
wyciąga fragmentów z prozy lub listy i nadal wymaga dowodu taktycznego.
`response_mapping` zapisuje normalizację, `raw_content` zachowuje oryginał.

`rule_application` ocenia wyłącznie pierwotną legalną propozycję modelu.
`rule_opportunities`, `rule_followed` i `rule_ignored` liczą decyzje, dla których
własna aktywna reguła ma zastosowanie. Brak okazji nie jest zaliczany jako sukces.
Ocena jest widoczna przy ruchu i w tabeli wyników; nie zmienia wykonanej akcji.

Wagi są utrzymywane przez całą serię, a prywatne stany resetowane między partiami.
Łączenie partii amortyzuje ładowanie bez obchodzenia admission. Nie jest to
trening wag ani dowód trwałego uczenia. Odbiór i ograniczenia małego pilota:
[LIVE_STRATEGY_RELEASE.md](LIVE_STRATEGY_RELEASE.md). Próba Huginn v4 przerwana
podczas przygotowania przez utratę odpowiedzi WSL nie jest wynikiem jakości.
