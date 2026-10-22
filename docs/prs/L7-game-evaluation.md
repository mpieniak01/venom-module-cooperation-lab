# L7 — Gry jako ewaluacja strategii, pamięci i planowania

**Status: PLAN / TODO, bez implementacji i bez publikacji PR.**
Tytuł PR: `feat(evaluation): testowanie modeli w grach — Nim, Memory i Sokoban`.
Repo: `mpieniak01/venom-module-cooperation-lab`. Jeden PR, kroki odbierane osobno.
ID L7 jest numerem planu, nie nadanym numerem GitHub.

## Summary

Obecna seria kółka i krzyżyka działa technicznie, ale nie stanowi dostatecznego
badania strategii lub adaptacji. PR dodaje wspólny kontrakt środowisk, cztery gry,
referencje, jawną politykę pamięci i dekodowania oraz porównywalny raport.
Silnik jest sędzią; decyzję podejmuje wskazany model. Ocena solvera nie trafia do
jego obserwacji. Brak treningu wag, promocji modelu i pobierania nowych checkpointów.

### Punkt wyjścia i zależności

Plan sprawdzono na lokalnym module `c7e11cc` (gałąź `codex/rwkv7-g1k-2.9b`),
core `4ef755a6`. Baza GitHub main modułu i bieżąca gałąź wymagają ponownego
porównania przed rozpoczęciem implementacji. Lokalne adaptery HRM/Huginn i serie
nie mogą zniknąć przy zakładaniu nowej gałęzi. Sprawdzenie po fetch 2026-10-22: nie jesteśmy na main, wszystkie 9 zaległych
commitów są na `codex/rwkv7-g1k-2.9b`; całość L7 kontynuujemy na tej wspólnej
gałęzi. Nie tworzymy następnej kopii ani stosu cherry-picków.
Nie zakładać, że lokalny kod jest już na zdalnym main ani tworzyć PR ze złą bazą.

W badaniu operatora 2026-10-22:

| Model | Ukończone gry | Unikalne przebiegi | Powtarzany błąd |
|---|---:|---:|---|
| RWKV-7 2.9B | 8 | 2 | B: 15 pominiętych blokad, 7 pominiętych wygranych |
| HRM-Text-1B | 10 | 1 | B: 10 pominiętych blokad |
| Huginn-0125 | 4 | 1 | B: 4 pominięte wygrane |

Każdą ukończoną grę wygrał A. ID źródeł: RWKV `7049c58df0b24dbbb2b6209160eb642c`,
HRM `dd98b1beeb1c4cad8374dd2ca4a9628e`, Huginn `5c95d83fcdc24970951b864b9560ef97`.
RWKV i Huginn anulowano; rozpoczętych niedokończonych partii nie liczymy jako
ukończone. Ocena taktyki jest analizą offline, bez podpowiadania modeli.

Wykryte ograniczenia: runner nadpisuje temperaturę 0.8/top_p 0.5 na 0/0,
dekoder wymusza legalne współrzędne, stany są resetowane przed kolejną partią,
pamięć to publiczne wyniki ostatnich 3 gier, brak etapu refleksji i zamiany stron.
Nie wolno przedstawiać dotychczasowych testów transportu jako dowodu nauki.

## Reuse zamiast ponownego budowania wszystkiego

[Decyzja po researchu kodu i licencji](L7-reuse-decision.md): zachować lokalny TTT,
adaptować mały podzbiór TextArena (MIT, przypięty SHA) dla Nim/Memory/Sokobana.
Bez instalacji całego frameworka i jego dodatkowych SDK. W G0 zapisać provenance,
licencje i rzeczywiście przejęte fragmenty; G1/G2 zawierają dostosowanie reguł,
RNG, parsera, widoczności i referencji. Samo istnienie gry upstream nie oznacza
zgodności z naszymi zasadami ani z odbiorem.

## Scope i integracja

Cała planowana implementacja w tym module: `evaluation/`, adaptery, API,
namespacowany zapis, `web-next` i testy. Istniejące `/runs`, stare eksporty,
kwalifikacje i scenariusze współpracy pozostają zgodne; v1 nie jest przeliczany
nowymi regułami. Nowy protokół i manifest: **game-eval-v2 / suite-v1**.

- `BenchmarkService` core: wzorce cyklu życia zadania, historii i agregatów czasu.
  Nie wywoływać jego przełączania globalnego runtime ani kopiować orkiestratora.
- Katalog: istniejący `ModelCatalog` i kontrakt hosta
  `GET /api/v1/system/llm-runtime/options`, rozszerzone metadanymi przypiętych
  lokalnych adapterów RWKV/HRM/Huginn. Brak modelu w katalogu core nie uzasadnia
  podstawienia go innym wykonawcą. Raport wiąże faktyczny digest/checkpoint/runtime.
- Academy: wersjonowane ID modeli i eksport gotowy do przyszłego importera.
  Bez uruchamiania treningu i automatycznego dokładania przebiegów do datasetu.
- C0 runtime admission pozostaje obowiązkowe. Jeden model/generacja na raz.
  Model–model v1: dwie sesje tych samych wag. Nowa ewaluacja model–bot wymaga
  jednej sesji modelu. Memory/Sokoban nie tworzą fikcyjnego przeciwnika B.
- Core nie wymaga zmiany funkcjonalnej według obecnej analizy. Ewentualny brak
  publicznego kontraktu hosta zgłosić przed rozszerzeniem zakresu/repozytorium.

### Gry i referencje

| Gra | Zakres i akcja v2 | Ocena niezależna od modelu |
|---|---|---|
| Kółko i krzyżyk | Obecna gra oraz legalne pozycje: wygrana, blokada, widełki; `{"square":"B2"}` | Minimax: wartość przed/po, utracona wygrana, blokada, gorszy ruch, wynik |
| Nim normal-play | Stosy konfigurowane, domyślnie `[3,4,5]`; `{"heap":0,"take":1}`; ostatni kamień wygrywa | Nim-sum, utrata pozycji wygrywającej; seeded bot losowy/optymalny |
| Memory | Jednoosobowe 4x4, 8 par; `{"cards":[1,5]}`; dwie różne niesparowane karty | Sukces, odsłonięcia kart (2 na decyzję), próby, pominięte znane pary; bot losowy i bot pamiętający |
| Sokoban | Małe wersjonowane plansze z jedną skrzynią; `{"move":"up"}` / down/left/right | Solver: sukces, zakleszczenie, kroki, pchnięcia i odległość od referencji |

Konwencje: Nim `heap` indeksowane od 0, `take` dodatnie i nie większe niż stos;
Memory `cards` to ID 0–15, wierszami od lewego górnego rogu (UI może pokazać A1–D4);
TTT A–C / 1–3; Sokoban `up` zmniejsza indeks wiersza. Granice plansz są częścią
ruleset, nie domysłem parsera. Plansze
Sokobana mają potwierdzenie rozwiązywalności BFS i skrót referencji. Rozróżnić
minimum kroków od minimum pchnięć (nie zakładać, że jedno rozwiązanie minimalizuje
oba). Solver ma limit stanów/czasu; jego błąd/wyczerpanie to błąd środowiska,
a nie modelu. Dla małych plansz zakleszczenie weryfikuje osiągalność celu.

Nim: start o nim-sum=0 jest przegrywający przeciw optymalnemu botowi. Nie karać
za nieuniknioną przegraną; liczyć zmianę wartości pozycji, a nie samą przegraną.
Przeciwnik ma seed i wersję reguły wyboru spośród równorzędnych ruchów.

Memory: obie pozycje wybierane są przed odsłonięciem, w jednej odpowiedzi modelu.
Po próbie widoczne są odsłonięte karty i status dopasowania. Niedopasowane karty
są ponownie zakryte; historia dopuszczonych odsłonięć pozostaje dostępna zgodnie
z polityką pamięci. „Znana para” oceniana jest z wiedzy sprzed decyzji, nie z
pełnego układu silnika. Bot pamiętający korzysta z tej samej informacji i nigdy
z drugiej karty odsłoniętej dopiero po wyborze akcji. Ukryty układ, referencje
solverów i ich ślady przechowywać oddzielnie od model-facing obserwacji/memo.
Nowy epizod dostaje jawne ID talii; carry nie ujawnia kart nowego rozkładu.

## Kontrakt środowiska i decyzji

Planowane typy: `Environment`, `CaseSpec`, `Observation`, `ActionValidation`,
`Transition`, `EpisodeResult`, `ReferenceAssessment`. Operacje:
`reset(case,seed)`, `observe(player)`, `validate(action)`, `step(action)`,
`terminal()`, `result()` oraz replay z manifestu i zaakceptowanych akcji.

Właściwości: deterministyczny silnik, niemutująca obserwacja, zamknięta lista gier,
brak dowolnego kodu/path od modelu. Model zwraca jeden kompletny obiekt akcji
w jednej odpowiedzi. Parser v2 nie wyszukuje pasującego ruchu wewnątrz dowolnej
wypowiedzi. Brak cichej naprawy, retry i dodatkowej szansy po nielegalnej akcji.
Dotychczasowy parser v1 i jego archiwalne wyniki pozostają niezmienione.

### Generacja i legalność — naprawa metodologii

`decoding=greedy|sampled`, jawne temperature/top_p i seed strumienia
`series + case + episode + player + decision`, identyczny schemat dla modeli.
Nie resetować RNG do tego samego seeda dla każdej decyzji w trybie próbkowania.
Backend potwierdza parametry **requested/applied**, bez ukrytego nadpisania 0/0.

`legal_moves=hidden|listed` jest niezależne od `action_constraint=none|masked`.
Pierwszy podstawowy profil v2: `listed + none`; model może popełnić nielegalny
ruch i jest to wynik testu. `hidden + none` daje osobny test znajomości zasad.
Dotychczasowe kółko i krzyżyk zachowuje `listed + masked` jako jawny profil
legacy, którego wyników legalności nie miesza się z v2. Nowe maskowanie jest
obsługiwane tylko przy zadeklarowanej implementacji adaptera dla danej gry;
obecnego coordinate-only `allowed_outputs` nie używać dla akcji Nim/Memory.
Strukturalna gramatyka JSON również musi być ujawniona jako pomoc dekodera.

Różnorodność ruchów/seedów nie oznacza uczenia. Nie wybierać po fakcie najlepszego
wariantu odpowiedzi i nie ukrywać prób błędnych/timeoutów w mianowniku skuteczności.

## Pamięć i możliwości adapterów

Dwie niezależne osie ustawień:

| Oś | Wariant | Kontrakt |
|---|---|---|
| Obserwacje | `history_replay` | Reset uczestnika przed decyzją, odtworzenie zadeklarowanej dopuszczonej historii i własnych działań |
| Obserwacje | `native_incremental` | Oddzielny stan gracza, tylko nowe zdarzenia i cursor; bez ponownego prefill starej historii |
| Epizody | `fresh` | Przed epizodem reset wszystkich stanów i historii poprzedniego epizodu |
| Epizody | `carry` | Zachowanie tekstowej historii/memo albo natywnego stanu przez cały jawny blok |

`carry` ma `block_id`, liczbę epizodów i limit kontekstu/stanu. Przekroczenie
limitu daje jawny status, a nie reset ukryty pod etykietą carry. Replay ma
określoną wersję historii/kompresji i limit; Memory nie może po cichu gubić
odsłonięć. Wariant `bounded_results_v1` pozostaje opisem starej serii L6,
nie udawaną realizacją native carry. Nie zwiększać globalnych limitów w ciemno.
Dane nowego epizodu oraz wynik poprzedniego są zwykłymi dozwolonymi zdarzeniami.

### Macierz startowa, do potwierdzenia testami

| Adapter | Replay fresh/carry | Native fresh/carry | Snapshot po restarcie | Budżet obliczeń |
|---|---|---|---|---|
| RWKV-7 | Tak, jawny reset przed replay | Cel implementacji: izolowane stany A/B + cursor/deduplikacja | Obecnie brak trwałego zapisu tensorów; restart bloku | Istniejący runtime, limit tokenów stanu |
| HRM-Text | Tak, PrefixLM i właściwe warunki zadania | `unsupported`: obecny cache odpowiedzi nie jest sesją wieloepizodową | Brak; tekst replay od granicy bloku/epizodu | Profil istniejącego checkpointu, bez fikcyjnego parametru iteracji |
| Huginn | Tak, własny template, bez cache w obecnym workerze | `unsupported` do kwalifikowanej implementacji cache | Brak; tekst replay od granicy bloku/epizodu | Rzeczywiste `num_steps=8/16/32/64` |
| Inne HRM | `unsupported` bez właściwego adaptera/checkpointu/kodowania | `unsupported` | Brak | Bez automatycznego zastępowania HRM-Text |

`AdapterCapabilities` deklaruje gry, zasady resetu/delta, snapshot/restore,
zakresy kontekstu i iteracji, ograniczenia parsera i metryki. Preflight sprawdza
całą kombinację przed ładowaniem modelu. Brak funkcji to `unsupported` z przyczyną;
brak zasobów jest odrębnym stanem. Sama nazwa modelu/„rekurencyjny” niczego nie
kwalifikuje. Parametry Huginn muszą trafić do `forward(num_steps=...)`, a zastosowana
wartość i tożsamość wykonawcy do każdego rachunku decyzji. Bez downgradu bibliotek.

### Refleksja jako kontrolowany wariant

Dodać profil `reflection=off|episode_note`. Po ukończonej partii `episode_note`
zleca modelowi krótką własną notatkę: jaki błąd zauważył i co zmienić następnym
razem. Osobny jawny etap, budżet/czas/tokeny; nie druga odpowiedź na ruch.
Nie żądać prywatnego toku myślenia. Notatka A i B pozostaje prywatna i jest
przenoszona tylko w carry. Bez wskazania optymalnego ruchu od solvera. Obserwacje
Memory nadal podlegają filtrowaniu. Porównać carry z surowymi wynikami i z notatką;
samo włączenie refleksji nie ma być raportowane jako nauka. Błąd/timeout tego
etapu zostaje zapisany, bez cichego uzupełnienia notatki przez hosta.

## Manifest, raport i kontrola porównań

`evaluation/manifests/suite-v1.json`: schema/ruleset, case ID, konfiguracja,
seed, pozycja/układ startowy, limit działań, strony i bot, skróty fixtures oraz
solver/reference version. Manifest jest przypięty hashem w serii. Publiczna
specyfikacja może zawierać ukryty układ dla odtwarzania środowiska; nie jest
bezpośrednio serializowana do promptu. Testy badają przecieki oddzielnie.

Mała macierz startowa: pozycje taktyczne TTT, Nim o wartości wygrywającej
(`[3,4,5]`, `[1]`) i przegrywającej (`[1,2,3]`, `[1,1]`), ziarna Memory i kilka
potwierdzonych plansz Sokobana. Jawne limity startowe: TTT do 9 ruchów, Nim do
liczby początkowych kamieni, Memory do 64 prób par, Sokoban do 128 ruchów.
Operator może wybrać mniejszy limit; zmiana tworzy inną konfigurację oceny. Zestaw
kalibracyjny i zatrzymany zestaw oceny mają różne case IDs; nie stroić promptu
na zatrzymanych wynikach. Każdy model otrzymuje te same przypadki i schemat
seedów. W grach dwuosobowych zamiana stron i rozpoczynającego; stała referencja
służy pomiarowi, model–model pozostaje osobnym eksperymentem.

Planowane API modułu (nowe, nie istniejące dziś): preflight/capabilities,
`/evaluations` create/list/snapshot, cancel, resume, episode journal,
export JSON/JSONL i podsumowanie CSV. Pola konfiguracji: manifest hash/model
identities/game/opponent, observations, episode_memory, reflection, generation,
legal assistance, applied compute budget i hard limits. UI: osobna zakładka
**Ewaluacja gier** wewnątrz `/cooperation-lab`; obecna rozmowa i sterowanie bez regresu.
Przed START liczba planowanych epizodów/bloków/wywołań i przyczyny unsupported.

Raport rozdziela:
- konfigurację i rzeczywiste wykonawstwo (requested/applied, czas ładowania osobno),
- decyzje: obserwacja widoczna graczowi, response, akcja/odrzucenie, czas i cursor,
- rezultat: game_completed, invalid_format, illegal_action, decision_timeout,
  action_limit, context_limit, runtime_error, environment_error, cancelled,
  interrupted, unsupported oraz osobna przyczyna błędu refleksji,
- koszty: wall time, mediana/p95 decyzji, tokeny, szczyt VRAM jeśli dostępny.

Nieznane metryki = null z przyczyną. Nie sumować szczytów VRAM kolejnych decyzji.
p95 ma zapisaną metodę i liczebność próbki. Planned/started/terminal/success/skipped
podawać oddzielnie od liczby ponowień bloków. Niepełna/nieobsługiwana konfiguracja
nie staje się zerowym wynikiem modelu; błędy modelu i limity nie znikają z oceny.
Metryki strategii porównywać osobno per gra/model/strona/memory/compute/decoder.

W panelu oprócz wyniku: pominięte wygrane/blokady, utracone pozycje, znane pary,
zakleszczenia oraz trendy per epizod. Nie wprowadzać uniwersalnego procentu
„nauczenia się”. Zachować kontrolę z pamięcią OFF i odróżniać zmianę zachowania
od poprawy jakości. Solver ocenia offline lub poza generacją, bez GPU.

## Zapis, przerwanie, wznowienie i dysk

Reuse `LabStore` i namespace hosta: wersjonowana migracja dodatkowych struktur
series/block/episode/decision; stare runs/kwalifikacje pozostają odczytywalne.
Klucz wyniku: seria + konfiguracja + blok + case + epizod + attempt. Zatwierdzenie
wyniku epizodu atomowe i idempotentne. Stan odtwarzalny bez ponownego LLM.

Fresh: wznowienie od kolejnego niezatwierdzonego epizodu. Carry: tylko od początku
bloku, chyba że adapter ma odebrany snapshot/restore wszystkich stanów, cursorów,
RNG, prywatnych memo i tożsamości. Dziś żaden lokalny adapter nie ma takiego trwałego
snapshotu. Restart tworzy nową próbę całego bloku i zachowuje ślad poprzedniej.
Nie scalać wyników przerwanego i nowego bloku w udawaną ciągłą sesję.
Niepoprawna akcja kończy epizod; w carry kończy blok, reszta ma skipped z przyczyną.
STOP kończy własną generację, nie uruchamia następnych bloków, bez auto-resume API.

Przebiegi i prywatne obserwacje poza Git. Jawne limity liczby serii, bloków,
decyzji, bajtów i retencji; naliczać SQLite/WAL oraz JSONL/exporty, aby nie omijać
512 MiB obecnej polityki. Nie podnosić limitu 2 MiB na obecny run w ciemno:
przygotować rozliczane, paginowane dzieci serii i ustalić bounded budget przed
START. Preflight odrzuca zbyt duży plan. Brak miejsca kończy zapis bez
zniszczenia zatwierdzonych wyników. Brak mnożenia venv, wag i trwałych kopii cache.

## Sekwencja implementacji w jednym PR

| Krok | Zakres i odbiór przed następnym |
|---|---|
| G0 | Zamrozić kontrakty, manifesty, capabilities, statusy, politykę RNG/pamięci i limity; testy zgodności v1; ustalić module-owned rejestr testów i pr-fast |
| G1 | Pionowy przekrój TTT + Nim: environment → adapter → ocena → durable wynik → odtworzenie; pierwszy spójny commit |
| G2 | Memory i Sokoban + referencje/solver; testy informacji ukrytych i deterministycznych przebiegów |
| G3 | Prawdziwe replay/native i fresh/carry, refleksja, num_steps Huginn; restart/STOP i izolacja stanu |
| G4 | Raport, UI/i18n PL/EN/DE, eksporty, preflight i zgodność istniejącego laboratorium |
| G5 | Mały odbiór realnych modeli, pełne bramki, przegląd, aktualizacja opisu PR, dopiero publikacja |

Ewentualny podział równoległy dopiero po G0: środowiska/referencje; adaptery/pamięć;
UI/raporty. Wspólne runner/storage/API integruje jeden właściciel. Osobne pliki
własności, bez równoległej edycji kontraktu i bez niezależnych wersji semantyki.
To plan podziału, nie uruchomienie workerów ani zgoda na równoległą inferencję.

## Kryteria odbioru

- [x] TTT v1/rozmowy/model catalog/export/Delete bez regresu; nowy v2 osobno.
- [x] Wszystkie 4 gry mają wspólny kontrakt i pozytywne/negatywne przypadki reguł.
- [x] Nim: bot optymalny i interpretacja przegrywającego startu; Memory bez wiedzy ukrytej.
- [x] Sokoban: solver potwierdza zestaw i metryki/deadlock bez dopowiadania ruchów modelowi.
- [x] Każdy zatwierdzony epizod odtwarza się z manifestu i akcji bez LLM.
- [x] Native przetwarza każde event ID raz, A/B odseparowane; brak podwójnego prefill.
- [x] Fresh i carry zachowują deklarowany typ pamięci; unsupported blokuje start przed load.
- [x] Właściwy forward 8/16/32/64 Huginn sprawdzony CPU; realne iteracje mają osobne wyniki i timeouty, bez cichego fallbacku.
- [x] Boty/strony/manifest/seed identyczne; błędy i pominięcia widoczne w mianownikach.
- [x] Snapshot carry bez wsparcia nie jest obiecywany; restart bloku jawny i idempotentny.
- [x] Metryki strategii/kosztu, JSON/JSONL/CSV i liczniki planned/started/terminal/skipped działają.
- [x] Hard limits/retencja/STOP/cleanup i moduł OFF nie blokują hosta.
- [ ] Zdalne bramki PR/CI i Sonar: nieuruchomione w lokalnej fazie. Lokalne testy, Snyk i przegląd opisane w raporcie; brak fikcyjnego PASS.

## Validation Report — plan oraz dowody lokalne

Nowe testy neutralnie nazwane: `test_game_rules.py`, `test_game_visibility.py`,
`test_game_references.py`, `test_game_sessions.py`, `test_game_resume.py`,
`test_game_reports.py`; bez słów `benchmark` i `integration` w ścieżkach testów
wymaganych do changed-lines coverage. Testy solverów i runnera CPU/deterministyczne,
bez pobierania modeli i wymagania GPU w CI. Frontend: formularz → żądanie,
unsupported, wyniki/filtry, SSE/replay, STOP, eksport i stały układ.

Rzeczywisty odbiór ograniczony: jeden mały jawny zestaw na RWKV-7 2.9B,
HRM-Text-1B i Huginn, pojedynczo; co najmniej gra z ukrytym stanem, planowanie,
kontrola fresh/carry, RWKV native oraz jeden identyczny przypadek z 8/16/32/64
Huginn. Przed uruchomieniem zapisać dokładną liczebność: rdzeń odbioru to po jednym
małym przypadku każdej gry na trzech dostępnych adapterach (12 epizodów), potem
minimalne bloki/pary kontrolne pamięci i 4 decyzje Huginn. Nie uruchamiać całego
iloczynu wszystkich ustawień domyślnie. Bez dużej domyślnej macierzy i bez pobierania specjalizowanego HRM.
Wyniki negatywne są dopuszczalne i mają trafić do raportu.

Bramki modułu: istniejące `make check HOST=/home/ubuntu/venom` (Ruff/mypy,
pytest >=90%, TS/lint/frontend i host contracts), changed-lines coverage z
faktycznego diff do bazy PR, CI `contracts`, Sonar/Snyk i dostępne required checks.
Próg changed-lines zgodny z aktualną polityką/quality gate, bez jego obniżania.

**Historyczna luka rozpoznana w planie (uzupełniona lokalnie):** moduł nie miał `make pr-fast` ani własnego
rejestru katalogu/grup core. W G0 dodać module-owned wejście `make pr-fast`
spinające istniejące kontrole z metadanymi i changed-lines coverage. Nowe testy
zarejestrować w module w `config/testing/test_catalog.json`, synchronizować grupy
oraz potwierdzić obecność w `config/pytest-groups/sonar-new-code.txt`. Obowiązuje
`primary_lane=new-code`, `allowed_lanes=[new-code,ci-lite,release]`. Preferować
wykorzystanie istniejących narzędzi hosta, jeżeli obsługują jawny root modułu;
w przeciwnym razie mały lokalny helper metadanych, bez kopiowania całego test runnera
core. Zaplanowane cele zgodności: `test-catalog-sync`, `test-groups-sync`,
`test-catalog-check`, `test-groups-check`, `check-new-code-coverage-diagnostics`.
Workflow modułu uruchamia końcowo `make pr-fast`, nadal bez ML/GPU w CI.

Przyszła sekwencja z root modułu, po implementacji tych celów:
```
make test-catalog-sync HOST=/home/ubuntu/venom
make test-groups-sync HOST=/home/ubuntu/venom
make test-catalog-check test-groups-check HOST=/home/ubuntu/venom
make check-new-code-coverage-diagnostics HOST=/home/ubuntu/venom
make pr-fast HOST=/home/ubuntu/venom
```
To planowane komendy, nie raport wykonania. W istniejącym aktywowanym venv nie
instalować ponownie stosu. Jeżeli powstaną rzeczywiste zmiany core, odpowiednio
zarejestrować jego testy i uruchomić także `make pr-fast` z root Venom wg aktualnego
`docs/AGENTS.md`. Nie wpisywać ścieżek innego repo do katalogu core jako fikcyjnego
pokrycia. Osobno potwierdzić kompatybilność lokalnego hosta i oficjalnego mirroru.

Opis końcowy PR wg szablonu core: Summary, Scope, Quality Gates, Commands run,
pass/fail, changed-lines coverage, Risks/Limitations/Skips, Evidence. Odznaczać
wyłącznie faktycznie zaliczone kontrole. **Aktualnie: implementacja lokalna,
odbiór CPU/UI i krótkie próby GPU; brak publikacji PR na GH.** Raport wykonania,
ograniczenia modeli i skanerów są w [odbiorze L7](../L7_LOCAL_ACCEPTANCE.md),
a instrukcja w [ewaluacji gier](../GAME_EVALUATION.md).

## Poza tym PR

Trwałe SFT/LoRA/RL, trening Academy, promocja modeli, nowy engine/checkpoint,
płatna infrastruktura, robot/kamera, heterogeniczna para dwóch LLM równocześnie,
pełny dashboard badań. Dalsze gry: Mastermind, Connect Four, Reversi, labirynt
z kluczem i kooperacja — przez ten sam kontrakt w kolejnych zmianach.

## Źródła projektu

- [BenchmarkService](https://github.com/mpieniak01/Venom/blob/main/venom_core/services/benchmark.py)
- [Academy](https://github.com/mpieniak01/Venom/blob/main/docs/PL/THE_ACADEMY.md)
- [Zasady agentów core](https://github.com/mpieniak01/Venom/blob/main/docs/AGENTS.md)
- [Szablon PR core](https://github.com/mpieniak01/Venom/blob/main/.github/pull_request_template.md)
- [Dotychczasowe serie](../GAME_SERIES.md)
- [Wdrożone adaptery HRM/Huginn](../HF_RESEARCH_MODELS.md)
