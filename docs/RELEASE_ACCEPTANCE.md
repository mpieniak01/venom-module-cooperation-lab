# Odbiór Cooperation Lab — 2026-10-21

Stan: **kwalifikacja techniczna C0/L2 wykonana; końcowy odbiór operatora i wydania
pozostaje w toku**. Wynik testów CPU, rzeczywistej inferencji i bramek wydania
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

## Oczekujące potwierdzenia końcowego odbioru

| Warunek | Stan / wymagany dowód |
| --- | --- |
| Rzeczywisty browser flow L4: start, A/B, STOP, reconnect, responsive | PENDING — wynik koordynatora i exact deployment SHA |
| Same-origin SSE proxy: brak buforowania, replay/Last-Event-ID i przerwanie | PENDING — test rzeczywistego hosta/proxy |
| Mała realna próba L5 obu modeli z niezależną rubryką i śladem delivery | PENDING — receipty runnera; formalny harness adaptera jej nie zastępuje |
| Pełna opcjonalna macierz 30 przypadków | PENDING / opcjonalna; nie jest obowiązkowym benchmarkiem wydania ani pretekstem do wielogodzinnego ponawiania modeli |
| OFF → restart → brak menu/model work; ponowne włączenie | PENDING — odbiór lifecycle rzeczywistej instancji |
| Przywrócona zwykła rozmowa hosta bez zmiany modelu operatora | PENDING — realny smoke po zwolnieniu zasobu |
| Końcowy zbiorczy `make check`, CI/review/Snyk/Sonar/GitGuardian | PENDING dla końcowych SHA; wcześniejsze wyniki nie zastępują tych bramek |
| Dokładne SHA końcowego core/module/deployment i decyzja ryzyka | PENDING — uzupełnia koordynator przed zamknięciem odbioru |

Sposób uruchomienia, retencja, OFF i rollback:
[RUNBOOK](RUNBOOK.md). Kryteria pełnego MVP: [ACCEPTANCE](ACCEPTANCE.md).
