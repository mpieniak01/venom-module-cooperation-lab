# Odbiór Cooperation Lab — 2026-10-21

Stan: **lokalny odbiór techniczny GPU, macierzy L5, browser/SSE/STOP i OFF
wykonany**. L1–L4 i C0 są scalone; L5 PR #13 do main oczekuje recenzji, kontroli
i scalenia. Próba zwykłego chatu po laboratorium zwróciła HTTP 400 przed pierwszą
treścią; to nierozwiązany blocker końcowego odbioru. Całe wydanie nie jest jeszcze zakończone. Wyniki CPU, rzeczywistej inferencji
i bramek wydania są rozdzielone. Działający transport nie dowodzi nauki ani
poprawy jakości modeli.

## Tożsamość wykonanej próby

Formalny harness działał w kanonicznej przestrzeni pamięci hosta przez publiczny
`get_runtime_admission()`. Koordynator zatrzymał wyłącznie API na czas próby,
zapewnił pusty `/api/ps` Ollama i uruchomił modele **kolejno**. Nie zmieniono
wyboru modelu operatora. Import modułu nie zaimportował Torch w procesie hosta;
Torch/RWKV ładowano dopiero w izolowanym procesie po uzyskaniu lease.

| Element | Rewizja / środowisko |
| --- | --- |
| Kod core podczas kwalifikacji | `711d70b33ca4b18c3711907e3bb72ee3fdbe7433` |
| Kod modułu/adapterów podczas kwalifikacji | `becd08b876d5b2fe7166c12b74a23721e5f61b28` |
| Scalony C0, do którego przypięto kompatybilność i CI | `aa2d612434949f1149d27f64ff10e5dd05334e8e` |
| Sprzęt | NVIDIA GeForce RTX 3060, 12288 MiB VRAM |
| Preset próby | maks. 32 tokeny wyjścia, kontekst 2048, seed 0, temperature 0, top_p 0 |
| Budżet | do 120 s/model, do 360 s łącznie; rzeczywiście 56.48 s łącznie |

Pełne receipty z odpowiedziami i pomiarami pozostają lokalnie poza Git.
Wygenerowano kandydatów `qualified=false`, `approval_required=true`; harness nie
wpisał sam kwalifikacji do bazy. Zaufany administrator osobno zatwierdza ryzyka
i zgodność pełnej tożsamości modelu przed aktywacją. Rewizja próby nie jest
zastępowana późniejszym SHA integracji. Końcowe SHA wydania/deploymentu zostaną potwierdzone
po scaleniu L5; prywatne identyfikatory prób nie są publikowane.

Artefakty, pełne digest/tokenizer/template i odtworzenie:
[modele L2](RWKV_L2.md). Kwalifikacja jest związana ze wszystkimi niezmiennymi
polami [kontraktu](CONTRACTS.md), także runtime i kwantyzacją.

## Stan scalenia etapów

| Etap | PR i stan | Rewizja |
| --- | --- | --- |
| L1 | [moduł #9](https://github.com/mpieniak01/venom-module-cooperation-lab/pull/9), scalony | `d4797d7e04c00d5948c2a257c6ab92038c7a53a4` |
| C0 | [Venom #552](https://github.com/mpieniak01/Venom/pull/552), scalony | `aa2d612434949f1149d27f64ff10e5dd05334e8e` |
| L2 | [moduł #10](https://github.com/mpieniak01/venom-module-cooperation-lab/pull/10), scalony | `95aa0bc60b86b9be737bbb9805eb648277bc9213` |
| L3 | [moduł #11](https://github.com/mpieniak01/venom-module-cooperation-lab/pull/11), scalony | `b4623ff151ff3991f374d4b6c6caf668336bfe97` |
| L4 | [moduł #12](https://github.com/mpieniak01/venom-module-cooperation-lab/pull/12), scalony; CI/contracts, Sonar, Snyk, GitGuardian i niezależny review PASS | merge `1021bb3a37bde64ca286b83607abae0109c408bf`; kod `6fb761393f202fe7e0ad338704deeeda6778fb47` |
| L5 | [moduł #13](https://github.com/mpieniak01/venom-module-cooperation-lab/pull/13), otwarty do main; recenzja, końcowe kontrole i scalenie pozostają do wykonania | końcowy SHA pending |

## Rzeczywiste wyniki C0/L2

Każdy model wykonał trzy krótkie generacje: A, osobne B, kontynuację A oraz
oddzielną próbę anulowania aktywnego, rzeczywiście posiadanego wątku.

| Pomiar | RWKV-7 G1d 0.4B | Qwen3:4b — kontrola |
| --- | ---: | ---: |
| Runtime | RWKV 0.8.32, Torch 2.13.0+cu130 | Ollama 0.40.6 |
| Efektywne wykonanie | `cuda:0`, `torch.float16` | GPU potwierdzone przez `/api/ps`, Q4_K_M |
| Czas całej kwalifikacji modelu | 11.42 s | 43.84 s |
| Ładowanie wag raportowane przez adapter | 1.45 s | Nieznane; `load()` weryfikuje metadane, `weights_loaded=false` |
| TTFT A / B / kontynuacja A | 3.65 / 0.61 / 0.21 s | 34.92 / 2.34 / 2.31 s |
| Generacja A / B / kontynuacja A | 3.90 / 0.81 / 0.35 s | 35.24 / 2.67 / 2.64 s |
| Input tokeny A / B / kontynuacja A | 25 / 26 / 18 | 32 / 32 / 85 |
| Output tokeny A / B / kontynuacja A | 6 / 8 / 6 | 32 / 32 / 32 |
| Zakończenie zwykłych odpowiedzi | `stop_sequence` ×3 | `length` ×3 |
| Od żądania cancel do końca rzeczywistego wątku | 0.115 s | 2.64 s |
| Cleanup, zwolnienie lease i host `available` | PASS | PASS |

RWKV używał jednej kopii niezmiennych wag i osobnych stanów tensorów A/B.
Rzeczywisty worker potwierdził fingerprinty, brak wspólnego storage tensorów,
brak zmiany A podczas B, zachowanie B podczas kontynuacji A oraz reset A do zera
bez zmiany B. Proces zakończył się z kodem 0. Overlay rzeczywiście zaimportował
certifi 2026.10.19 i filelock 4.2.1 bez zmiany pakietów Full.

Ollama potwierdziła osobne pełne historie A/B, reset A bez zmiany B, terminalne
`done` oraz wyładowanie własnego modelu z `/api/ps` przed zwolnieniem lease.
Publiczne API Ollama nie udostępnia fingerprintów latent KV: takiej inspekcji
nie wykonano. C0 blokował zwykły `host_chat` podczas lease obu modeli. Po próbie
koordynator przywrócił API i UI. Późniejsza rzeczywista próba normalnej rozmowy
nie przeszła; jej wynik i granica diagnozy są opisane osobno poniżej.

## Rzeczywista macierz L5 — zamrożone v1

Koordynator wykonał pełne 2 modele × 3 scenariusze × 5 trybów. Tabela obejmuje
jeden kompletny przebieg po poprawce czasu cleanup, bez mieszania go z wcześniejszą
przerwaną próbą i bez wybierania najlepszych odpowiedzi. Wszystkie **30/30**
runów zakończyły się technicznie `completed` i potwierdzonym quiescence.
W **12/12** runach dialog/dialog_encouraged jest dowód dostarczenia wiadomości
oraz późniejszej odpowiedzi uczestnika. Pozostałe 18 runów to warianty kontrolne
bez komunikacji. To dowód działania przepływu, bez twierdzenia o wykonanej
samoorganizacji czy jakości rozwiązania.

Ścisła rubryka v1 oznaczyła **30/30 jako `unscorable`**, z powodem
`ambiguous_format`: zero wyników ocenialnych, zatem **accuracy jest nieznane
(`null`), a nie 0%**. Prompt v1 prosi o zwięzłą odpowiedź albo wiadomość i opcjonalny
envelope JSON; nie wymaga końcowego formatu, który dałby się niezależnie ocenić
ścisłą rubryką. Wszystkie 27 generacji Qwen skończyły się `length` przy 32 tokenach;
6 z 27 generacji RWKV też osiągnęło limit. Nie poprawiamy parsera po zobaczeniu
wyniku i nie wybieramy najlepszego fragmentu wypowiedzi.

Preset: seed 17, temperature 0, top_p 0, maks. 2 tury i 32 output tokeny/turę,
kontekst 2048. `single` wykonał jedną turę; inne tryby po dwie. Łącznie 54 generacje,
7371 input / 1293 output tokeny, 146.37 s generacji i 221.39 s sumy czasów runów.
Czas runu obejmuje także przygotowanie i cleanup. To nie jest czas samej inferencji
ani ranking modeli. Pełne precyzyjne liczby i przypięte tożsamości modeli:
[zredagowane wyniki JSON](EXPERIMENT_RESULTS_V1.json), bez promptów, odpowiedzi,
idempotency keys, prywatnych ścieżek lub surowych eksportów.

W tabelach: komunikacja `tak` = journal potwierdza dostarczenie i późniejszą
odpowiedź; `—` = wariant bez komunikacji. Ocena `U` = `unscorable` w niezmienionej
rubryce v1. Wszystkie wiersze mają status techniczny `completed` i quiescence.
`Obcięcia` liczą generacje, nie całe runy.

### RWKV-7 G1d 0.4B

| Nr | Scenariusz | Tryb | Tury | Input/output | Generacja [s] | Run [s] | Obcięcia | Komunikacja | Ocena |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 1 | split_facts | single | 1 | 120/8 | 2.79 | 5.63 | 0 | — | U |
| 2 | split_facts | self_correction | 2 | 132/17 | 3.19 | 5.98 | 0 | — | U |
| 3 | split_facts | no_contact | 2 | 228/17 | 3.87 | 6.68 | 0 | — | U |
| 4 | split_facts | dialog | 2 | 266/41 | 4.77 | 11.13 | 1 | tak | U |
| 5 | split_facts | dialog_encouraged | 2 | 324/41 | 5.54 | 8.36 | 1 | tak | U |
| 6 | organization | single | 1 | 124/9 | 2.71 | 5.55 | 0 | — | U |
| 7 | organization | self_correction | 2 | 136/19 | 3.38 | 6.30 | 0 | — | U |
| 8 | organization | no_contact | 2 | 236/15 | 3.89 | 6.88 | 0 | — | U |
| 9 | organization | dialog | 2 | 274/42 | 5.47 | 12.79 | 1 | tak | U |
| 10 | organization | dialog_encouraged | 2 | 333/42 | 5.45 | 9.58 | 1 | tak | U |
| 11 | correction | single | 1 | 136/12 | 2.73 | 5.66 | 0 | — | U |
| 12 | correction | self_correction | 2 | 148/25 | 3.61 | 6.54 | 0 | — | U |
| 13 | correction | no_contact | 2 | 260/29 | 4.77 | 11.15 | 0 | — | U |
| 14 | correction | dialog | 2 | 309/56 | 5.48 | 8.37 | 1 | tak | U |
| 15 | correction | dialog_encouraged | 2 | 371/56 | 6.07 | 8.84 | 1 | tak | U |

### Qwen3:4b — kontrola

| Nr | Scenariusz | Tryb | Tury | Input/output | Generacja [s] | Run [s] | Obcięcia | Komunikacja | Ocena |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 16 | split_facts | single | 1 | 114/32 | 10.02 | 14.16 | 1 | — | U |
| 17 | split_facts | self_correction | 2 | 275/64 | 12.78 | 13.39 | 2 | — | U |
| 18 | split_facts | no_contact | 2 | 216/64 | 5.35 | 5.94 | 2 | — | U |
| 19 | split_facts | dialog | 2 | 280/64 | 5.31 | 5.90 | 2 | tak | U |
| 20 | split_facts | dialog_encouraged | 2 | 340/64 | 5.21 | 9.37 | 2 | tak | U |
| 21 | organization | single | 1 | 124/32 | 2.38 | 2.91 | 1 | — | U |
| 22 | organization | self_correction | 2 | 294/64 | 4.77 | 5.37 | 2 | — | U |
| 23 | organization | no_contact | 2 | 232/64 | 4.93 | 5.50 | 2 | — | U |
| 24 | organization | dialog | 2 | 296/64 | 4.75 | 5.31 | 2 | tak | U |
| 25 | organization | dialog_encouraged | 2 | 357/64 | 4.73 | 5.29 | 2 | tak | U |
| 26 | correction | single | 1 | 140/32 | 2.88 | 3.44 | 1 | — | U |
| 27 | correction | self_correction | 2 | 327/64 | 4.88 | 9.00 | 2 | — | U |
| 28 | correction | no_contact | 2 | 264/64 | 5.01 | 5.57 | 2 | — | U |
| 29 | correction | dialog | 2 | 328/64 | 4.84 | 5.40 | 2 | tak | U |
| 30 | correction | dialog_encouraged | 2 | 387/64 | 4.82 | 5.38 | 2 | tak | U |

Następny research wymaga **jawnego kontraktu końcowej odpowiedzi v2**: nowa wersja
promptu/datasetu/rubryki, wymagany format odpowiedzi, odpowiedni budżet i osobne
wyniki. Dataset, prompty i parser v1 pozostają zamrożone; nie przeliczamy tej
macierzy jako sukcesu po zmianie reguł.

## Rzeczywisty odbiór browser/SSE/STOP

Koordynator sprawdził żywy panel i fizyczne wykonanie RWKV. Publikowany opis
pomija identyfikator sesji, prompty, odpowiedzi i lokalne artefakty.

| Sprawdzenie | Rzeczywisty wynik |
| --- | --- |
| START w panelu | Powstała jedna próba RWKV i wiadomości obu uczestników A/B |
| Reload/reconnect | Ten sam zapis próby; liczba wiadomości wzrosła z 1 do 4, bez nowego START |
| Same-origin SSE przez port UI 3300 | HTTP 200, `text/event-stream`; replay po kursorze 2 dostarczył zdarzenia do seq 17 |
| STOP | `cancelled`, `quiescent=true`; brak utożsamiania zamknięcia karty z końcem GPU |
| Zwolnienie zasobu po STOP | lease `available`, `active_operations=0`, Ollama `/api/ps=[]` |
| Stabilność paska sterowania | Przed pracą i w trakcie identyczny prostokąt: x=348, y=278.5, szerokość=950, wysokość=64 px |
| Desktop 1366×900 / mobile 390×844 | Ponowny smoke finalnego refaktoru PASS; mobile scrollWidth 382 ≤ 390, bez poziomego overflow |
| Mobilny pasek sterowania | x=28, y=340, szerokość=326, wysokość=136 px; START x=41/right=229.8, STOP x=237.8/right=329.45 — oba widoczne |
| PL / EN / DE | Etykiety sprawdzone w rzeczywistym DOM; przywrócono PL |
| Konsola | Podstawowy smoke: 0 błędów; ostrzeżenia wykresów hosta nadal występowały. Dodatkowa weryfikacja usunięcia: 1 oczekiwany błąd HTTP 404 w konsoli |
| Wybór historii Qwen→RWKV | Rzeczywiście odtworzono identyfikator modelu z kropkami i limity 2 tury / 32 tokeny |
| Eksport własnej anulowanej próby | Pobranie pliku przez przeglądarkę PASS; bez publikacji surowych danych |
| Usunięcie własnej próby | Usunięcie i potwierdzenie braku zapisu przez HTTP 404 PASS |

Ponowny smoke po wdrożeniu finalnego refaktoru L4 wykonano na lokalnej rewizji
`382dd65`: PL/EN/DE, desktop/mobile i stałe kontrolki PASS, 0 błędów konsoli
w tym przebiegu (ostrzeżenia wykresów hosta pozostawały). Wcześniejszy odbiór
eksportu/usunięcia dotyczy rewizji `b3dcc43`; oczekiwany probe 404 jest oddzielnym
dowodem i nie jest ukrywany w liczniku finalnego smoke. Rewizje lokalnych prób
nie są deklaracją końcowego SHA wydania L5.

Powyższe potwierdza konkretny lokalny przepływ. Długie treści, równoległe karty,
negatywne odpowiedzi i skrajne stany UI mają dodatkowe testy fixture; nie
przedstawiamy każdego z tych wariantów jako osobnej próby na GPU/przeglądarce.

## Rzeczywisty odbiór OFF

PASS na podstawie zapisanego `off-acceptance.json`: po uruchomieniu hosta z
wyłączonym modułem jego trasy API były nieobecne, hash bazy laboratorium pozostał
bez zmian, trasy Rider nadal były obecne, health hosta zwrócił HTTP 200 i
Ollama `/api/ps` było puste. Pierwszy probe 10 s był zbyt krótki na start hosta;
PASS dotyczy późniejszego potwierdzonego wyniku, a nie pominięcia tego oczekiwania.
To odbiór API/stanu danych. Włączony panel i rzeczywisty START/STOP odebrano
oddzielnie powyżej. Wynik zwykłego chatu jest opisany w następnej sekcji.
Końcowe scalenie/deployment oraz widoczność menu w stanie OFF nie są potwierdzane
samym brakiem tras API.

## Nierozwiązany odbiór zwykłego chatu hosta

Jeden rzeczywisty probe po laboratorium zakończył się **FAILED — HTTP 400 przed
pierwszą treścią odpowiedzi**. Dotychczasowy wybór operatora `gemma2:2b`
(legacy, interfejs completion-only) pozostał bez zmian. Oryginalne body błędu
nie zostało zachowane, więc nie przypisujemy przyczyny modułowi, transportowi
ani modelowi na podstawie samego kodu HTTP.

Po tym probe zaobserwowano `quarantine=1`. Poprawka core obsługi cleanup
typowanego błędu transportu jest w toku; ten follow-up dotyczy zwolnienia zasobu,
nie poprawki parametru legacy adaptera. Jego odbiór i ponowna rzeczywista próba
czatu pozostają wymagane. Wcześniejsze `available`, `active_operations=0`
i puste `/api/ps` po próbach modułu potwierdzają ich cleanup, ale nie zastępują
odpowiedzi zwykłego chatu. Nie oznaczamy tego kryterium jako PASS i nie zamykamy
całego wydania przed rozstrzygnięciem.

## Testy regresji i niezależne przeglądy

| Zakres i dowód | Wynik |
| --- | --- |
| Pełna lokalna integracja przed końcowym wydaniem | `make check`: 252 testy Python PASS, coverage 97% (1993 statements / 55 miss); mypy 20 źródeł; 15 testów frontendowych PASS, line coverage 96,02%; TS/lint i kontrakty hosta PASS |
| L4, końcowy kod `6fb7613` | CI/contracts, Sonar, Snyk i GitGuardian PASS; niezależny review PASS. PL/EN/DE: 97 kluczy na język i 0 różnic tekstów przed/po refaktorze; bounded replay i dotychczasowe testy zachowane |
| L3 po integracji z C0, `ee3b34afdc2a0a60bd2c3c3630c947b7f08c7852` | Pełne `make check`: 168 pytest PASS, coverage 96.95%, mypy 19 źródeł, Ruff/format, TS/lint, 4 testy webowe i kontrakty opcjonalnego modułu PASS |
| Niezależny L5 po `c9fcb8b28516795685290a36788655dd2daf85d4` | 60 targeted testów CPU PASS; powtórzone konkretne repro uwag przeglądu |
| C0/L2 — niezależny przegląd | Zweryfikowane admission/cancel/cleanup oraz tożsamość artefaktów i izolacja; brak deklaracji skanów jako dowodu inferencji |
| Przegląd L3 — naprawione uwagi | Single-owned close i późny cleanup; namespace przed migracją/recovery; pełna tożsamość kwalifikacji, w tym runtime/revision/quantization; SETTINGS jako źródło flag |
| Przegląd L5 — naprawione uwagi | Sprzeczny adresat odrzucany; generating→usage→message z właściwym turn_id wymagane do oceny sukcesu; stop_reason, efektywne parametry i obcięcie zachowane w raporcie |

Liczniki wcześniejszych etapów pozostają historycznymi dowodami. Ostatnia pełna
regresja integracji nie zastępuje kontroli końcowych scalonych SHA w CI. Testy CPU używają jawnych fixture i rzeczywistego ledgeru
C0; nie zastępują testu GPU/przeglądarki.

## Granice interpretacji

1. **To odbiór techniczny, nie ranking ani dowód nauki.** Małe scenariusze mają
   jeden seed i ograniczony output. Single/self_correction otrzymują komplet
   informacji; no_contact/dialog — podział. Jednakowe limity nie oznaczają
   takiego samego faktycznego kosztu ani dostępu do informacji. Proposal/accept
   i zgodna odpowiedź nie dowodzą wykonania podziału pracy.
   `commitment_execution=unscorable` i `quality_gain_claim=false` pozostają jawne.
   Ujemny lub niejednoznaczny wynik jest poprawnym wynikiem eksperymentu.
2. **32 tokeny i cold start ograniczają porównanie.** Wszystkie trzy odpowiedzi
   Qwen zostały obcięte limitem, więc brak pełnego wyniku nie rozstrzyga zdolności
   modelu. Pierwsze TTFT Qwen obejmuje zimne ładowanie wag; nie jest porównywalne
   z samym `load_s` RWKV. Pojedynczy czas cancel nie jest gwarancją stałej latencji
   STOP: Ollama odczytuje ograniczoną generację do rzeczywistego `done`.
3. **Brak nowych zgłoszeń overlay nie oznacza security PASS całego Full.** Lokalny
   skan efektywnej unii 35 zależności po overlay pozostawił pięć odziedziczonych
   ID Torch (1 High, 4 Medium), już obecnych w Full PR #546. Dziewięć nowych ID
   certifi/filelock nie wystąpiło. Nie dodano ignore ani nie ogłoszono zera
   podatności. Szczegóły i granice znajdują się w [L2](RWKV_L2.md); decyzja ryzyka
   pozostaje osobnym warunkiem wydania.

## Rzeczywiste próby a granice testów fixture

| Zakres | Rodzaj dowodu |
| --- | --- |
| Dwa modele, izolacja/reset/cancel/cleanup | Rzeczywista kwalifikacja GPU C0/L2 |
| Macierz 30 i dostarczenie wiadomości | Rzeczywisty runner, 30/30 completed i 12/12 dialogów z komunikacją |
| Browser START/reload/SSE/STOP, układ, responsive, i18n | Rzeczywisty odbiór powyżej |
| OFF i zachowanie bazy/Ridera | Rzeczywisty odbiór API/danych |
| Crash/interrupted bez auto-resume | Testy fixture; bez celowego crash procesu podczas realnej inferencji |
| Retencja, limity dysku/runów, storage-full i OOM | Testy fixture; bez zapychania dysku lub wymuszania realnego GPU OOM |
| Zwykła rozmowa hosta po laboratorium | Jedna rzeczywista próba FAILED: HTTP 400 przed pierwszą treścią; wybór operatora niezmieniony. Body błędu utracono, przyczyna nieustalona; cleanup transportu i ponowny odbiór pozostają otwarte |

## Stan końcowego odbioru i pozostałe potwierdzenia

| Warunek | Stan / wymagany dowód |
| --- | --- |
| Browser L4: start, A/B, STOP, reload/reconnect, responsive i i18n | PASS — rzeczywisty odbiór; końcowy release SHA pozostaje odrębny |
| Same-origin SSE proxy i replay | PASS — HTTP 200/text/event-stream, kursor 2→seq 17 i rzeczywisty reload |
| Realna macierz L5 obu modeli z niezależną rubryką i śladem delivery | PASS techniczny 30/30 i komunikacja 12/12; jakość 30/30 unscorable, accuracy=null |
| Pełna macierz 30 przypadków | WYKONANA; wyniki powyżej i w zredagowanym JSON; bez zmiany zamrożonej rubryki v1 |
| OFF → restart: API nieobecne, baza bez zmian, Rider obecny, Ollama puste | PASS — realny off-acceptance.json |
| Panel ON oraz menu OFF | Panel ON/START/STOP PASS; ukrycie menu OFF ma kontrakt/fixture, nie osobne potwierdzenie DOM |
| Zwykła rozmowa hosta po laboratorium | BLOCKER — rzeczywisty probe HTTP 400 przed pierwszą treścią; po nim quarantine=1, poprawka core i ponowny odbiór pending. Brak body uniemożliwia pewne przypisanie przyczyny |
| Eksport i usunięcie własnej anulowanej próby | PASS — rzeczywiste pobranie przez przeglądarkę i potwierdzenie usunięcia HTTP 404 |
| Pełny lokalny `make check` i kontrole wydania | Lokalny gate 252 Python / 15 frontend PASS, mypy/TS/lint/host contracts PASS. L4 scalony z CI/contracts/Sonar/Snyk/GitGuardian i niezależnym review PASS; L5 PR #13 do main wymaga końcowych kontroli i scalenia |
| Dokładne SHA końcowego core/module/deployment i decyzja ryzyka | PENDING — uzupełnia koordynator przed zamknięciem odbioru |

Sposób uruchomienia, retencja, OFF i rollback:
[RUNBOOK](RUNBOOK.md). Kryteria pełnego MVP: [ACCEPTANCE](ACCEPTANCE.md).
