# Odbiór Cooperation Lab — 2026-10-21

Stan: **kwalifikacja GPU C0/L2, rzeczywista macierz 30 prób i odbiór OFF wykonane;
końcowy odbiór przeglądarki i wydania pozostaje w toku**. Wynik testów CPU, rzeczywistej inferencji i bramek wydania
jest rozdzielony poniżej. Samo przejście kwalifikacji adaptera nie dowodzi
współpracy ani poprawy jakości modeli.

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
| RWKV receipt | `host-227f9eeaed904e22849993c56adfccf0` |
| Qwen receipt | `host-71db1ed56a5846e9b89c310533806b43` |

Pełne receipty z odpowiedziami i pomiarami pozostają lokalnie poza Git.
Wygenerowano kandydatów `qualified=false`, `approval_required=true`; harness nie
wpisał sam kwalifikacji do bazy. Zaufany administrator osobno zatwierdza ryzyka
i zgodność pełnej tożsamości modelu przed aktywacją. Rewizja próby nie jest
zastępowana późniejszym SHA integracji. Dokładny końcowy deployment podano dopiero
po jego odbiorze w tabeli poniżej.

Artefakty, pełne digest/tokenizer/template i odtworzenie:
[modele L2](RWKV_L2.md). Kwalifikacja jest związana ze wszystkimi niezmiennymi
polami [kontraktu](CONTRACTS.md), także runtime i kwantyzacją.

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
koordynator przywrócił API i UI; odbiór normalnej rozmowy po przywróceniu jest
osobnym krokiem.

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

## Rzeczywisty odbiór OFF

PASS na podstawie zapisanego `off-acceptance.json`: po uruchomieniu hosta z
wyłączonym modułem jego trasy API były nieobecne, hash bazy laboratorium pozostał
bez zmian, trasy Rider nadal były obecne, health hosta zwrócił HTTP 200 i
Ollama `/api/ps` było puste. Pierwszy probe 10 s był zbyt krótki na start hosta;
PASS dotyczy późniejszego potwierdzonego wyniku, a nie pominięcia tego oczekiwania.
To odbiór API/stanu danych. Widoczność menu w przeglądarce, ponowne włączenie,
normalna rozmowa hosta oraz końcowy deployment pozostają osobnymi krokami.

## Testy regresji i niezależne przeglądy

| Zakres i dowód | Wynik |
| --- | --- |
| L3 po integracji z C0, `ee3b34afdc2a0a60bd2c3c3630c947b7f08c7852` | Pełne `make check`: 168 pytest PASS, coverage 96.95%, mypy 19 źródeł, Ruff/format, TS/lint, 4 testy webowe i kontrakty opcjonalnego modułu PASS |
| Niezależny L5 po `c9fcb8b28516795685290a36788655dd2daf85d4` | 60 targeted testów CPU PASS; powtórzone konkretne repro uwag przeglądu |
| C0/L2 — niezależny przegląd | Zweryfikowane admission/cancel/cleanup oraz tożsamość artefaktów i izolacja; brak deklaracji skanów jako dowodu inferencji |
| Przegląd L3 — naprawione uwagi | Single-owned close i późny cleanup; namespace przed migracją/recovery; pełna tożsamość kwalifikacji, w tym runtime/revision/quantization; SETTINGS jako źródło flag |
| Przegląd L5 — naprawione uwagi | Sprzeczny adresat odrzucany; generating→usage→message z właściwym turn_id wymagane do oceny sukcesu; stop_reason, efektywne parametry i obcięcie zachowane w raporcie |

Powyższe liczniki dotyczą wskazanych etapów i SHA, nie nieuruchomionej końcowej
regresji całego wydania. Testy CPU używają jawnych fixture i rzeczywistego ledgeru
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

## Stan końcowego odbioru i pozostałe potwierdzenia

| Warunek | Stan / wymagany dowód |
| --- | --- |
| Rzeczywisty browser flow L4: start, A/B, STOP, reconnect, responsive | PENDING — wynik koordynatora i exact deployment SHA |
| Same-origin SSE proxy: brak buforowania, replay/Last-Event-ID i przerwanie | PENDING — test rzeczywistego hosta/proxy |
| Realna macierz L5 obu modeli z niezależną rubryką i śladem delivery | PASS techniczny 30/30 i komunikacja 12/12; jakość 30/30 unscorable, accuracy=null |
| Pełna macierz 30 przypadków | WYKONANA; wyniki powyżej i w zredagowanym JSON; bez zmiany zamrożonej rubryki v1 |
| OFF → restart: API nieobecne, baza bez zmian, Rider obecny, Ollama puste | PASS — realny off-acceptance.json |
| Menu OFF/ponowne włączenie w przeglądarce | PENDING — odbiór operatora |
| Przywrócona zwykła rozmowa hosta bez zmiany modelu operatora | PENDING — realny smoke po zwolnieniu zasobu |
| Końcowy zbiorczy `make check`, CI/review/Snyk/Sonar/GitGuardian | PENDING dla końcowych SHA; wcześniejsze wyniki nie zastępują tych bramek |
| Dokładne SHA końcowego core/module/deployment i decyzja ryzyka | PENDING — uzupełnia koordynator przed zamknięciem odbioru |

Sposób uruchomienia, retencja, OFF i rollback:
[RUNBOOK](RUNBOOK.md). Kryteria pełnego MVP: [ACCEPTANCE](ACCEPTANCE.md).
