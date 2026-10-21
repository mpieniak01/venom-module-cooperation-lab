# L2 — modele i adaptery

Status: implementacja adapterów; formalny odbiór współdzielonego kontraktu C0
pozostaje oddzielnym krokiem. `ModelSpec.qualified=false` jest celowe: obecność
pliku ani wstępna próba nie odblokowują automatycznie eksperymentu.

## Zamrożone modele

| ID laboratorium | Artefakt | Tożsamość | Runtime |
| --- | --- | --- | --- |
| `rwkv7-g1d-0.4b` | `BlinkDL/rwkv7-g1`, `rwkv7-g1d-0.4b-20260210-ctx8192.pth`, 901776749 B | revision `2a17e911155a5be23a4ed2792e978c77038f14e2`; SHA256 `947cb9b8013224e06b112b72204256bec65096cc935a7767ce63d8e3ddef83bb` | RWKV 0.8.32, istniejący Torch 2.13.0+cu130, CUDA FP16, bez kompilacji custom kerneli |
| `qwen3-4b-control` | Istniejący `qwen3:4b`, Q4_K_M | digest `359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7` | Ollama 0.40.6; nie pobieramy nowych wag |

RWKV ma 450767872 parametrów, 24 warstwy, hidden 1024 i vocabulary 65536.
Licencja modelu i runtime: Apache-2.0. To model bazowy z danymi instrukcji/rozmów,
nie gwarancja poprawnego JSON ani samoorganizacji. Mały rozmiar służy kwalifikacji
nowej architektury i dwóch oddzielnych stanów, nie rozstrzyga wartości rodziny.

Tokenizer `rwkv_vocab_v20230424.txt` z tego samego przypiętego koła ma SHA256
`8324476023347dec2964625ccb2075c864d250a9c6d9a74f36daba628de8c008`.
Adapter używa własnego parsera `ast.literal_eval`, zamiast upstream `eval`.
Szablon odpowiada separatorom `System:`, `User:`, `Assistant:` autora; wejścia
normalizują wielokrotne puste wiersze. Wersja i hash szablonu są częścią spec.
Qwen tokenizer jest częścią GGUF objętego digest; hash jego szablonu z `/api/show`
to `2d54db2b9bb29ce7db54fea63a891f5859603813c555b1f88b5e0994652897f9`.

Źródła autorów: [karta RWKV](https://huggingface.co/BlinkDL/rwkv7-g1),
[przewodnik promptów](https://github.com/BlinkDL/RWKV-LM/blob/main/RWKV-v7/RWKV7-G1x-templates.txt),
[runtime PyPI](https://pypi.org/project/rwkv/0.8.32/),
[implementacja autora](https://github.com/BlinkDL/ChatRWKV/tree/main/rwkv_pip_package).

## Interfejs i izolacja

`adapters` eksportuje `list_model_specs`, `get_model_spec`, `create_adapter`,
`ChatMessage`, `GenerationParameters`, `GenerationResult` i `ModelSpec`.
Discovery nie wykonuje I/O sieci, pobierania ani inferencji. Factory przyjmuje
wyłącznie znane ID i lease hosta. Ścieżki plików należą do konfiguracji hosta,
nie pól API lub odpowiedzi modelu.

Metody synchroniczne `load(deadline_s)` i
`generate(participant_id, messages, parameters, deadline_s)` przyjmują bezwzględny
termin `time.monotonic()`. Runner uruchamia je przez `asyncio.to_thread` pod
kontraktem C0. Dodatkowo: `cancel`, `reset`, `state`, `close`, `is_quiescent`.
`load/generate` mają własne `lease.operation`; `close` używa `lease.cleanup`,
który działa również po anulowaniu. Outer runner nie zwalnia lease przed close.

RWKV to jeden izolowany proces, jedne niezmienne wagi, prywatne tensory i historie
A/B. Dopisywany kontekst zachowuje stan; zmiana wcześniejszych wiadomości jawnie
odtwarza kontekst od zera. Reset jednego uczestnika nie zmienia drugiego. Reset
runu kończy proces. CUDA synchronizuje się przed potwierdzeniem końca generacji;
pełny `is_quiescent` wymaga końca procesu. Linux parent-death SIGKILL, daemon
process i bounded terminate/kill/join zabezpieczają przed osieroconym workerem.
Brak potwierdzenia końca oznacza quarantine.

Ollama otrzymuje osobną pełną historię uczestnika w każdym `/api/chat`, `think=false`
i `keep_alive=0`. Anulowanie blokuje następną turę, ale bieżący stream jest
odczytywany do faktycznego `done`. Zamknięcie socketu nie jest dowodem końca GPU.
`close` dodatkowo potwierdza brak własnego modelu w `/api/ps`. Timeout lub zerwany
stream bez `done` daje quarantine, nie pozorne zwolnienie zasobu. Runtime nie ma
kwalifikowanego natychmiastowego preemption; czas anulowania może obejmować resztę
ograniczonej generacji. Nie zatrzymujemy serwera ani cudzych modeli.

Parametry są frozen: do256 output tokenów, do2048 kontekstu, seed, temperature,
top_p. RWKV egzekwuje faktyczny limit tokenów; Ollama stosuje konserwatywny górny
limit bajtów UTF-8 z marginesem szablonu przed wywołaniem, zamiast cichego
przycinania. Faktyczne usage z runtime albo jawne `None`; runner rozlicza także
powtarzane wejścia i konserwatywny limit przy brakujących metrykach.

## Odtworzenie komponentu

Nie ma pobierania przy imporcie/startupie/API. Operator jawnie uruchamia:

```sh
python scripts/provision_rwkv.py \
  --model-root "$COOPERATION_LAB_RWKV_MODEL_ROOT" \
  --runtime-root "$COOPERATION_LAB_RWKV_RUNTIME_ROOT" \
  --storage-root /mnt/f
```

Ścieżki muszą być bezwzględne. Skrypt sprawdza fizyczny backing volume, limit
jednego pliku, SHA256, integralność istniejących plików i bezpieczne ścieżki ZIP.
Rozpakowuje tylko przypięty mały runtime do wydzielonego katalogu, bez nowego
venv i zmian pakietów Full. Rejestr domyślnie wskazuje centralny research model
store oraz wydzielony komponent użytkownika; produkcyjny host ustawia własne
wartości zmiennych administracyjnych. Nie kopiować tych ścieżek do requestu API.
Usuwanie modeli użytkownika i globalne zmiany Ollama są poza tym skryptem.

## Wstępna feasibility — 2026-10-21

Pojedyncza próba z RTX3060 12GiB, bez zmiany wyboru operatora:

| Pomiar | Wynik |
| --- | --- |
| Cold start procesu+runtime+wagi | 2.78s |
| Load samych wag | 1.15s |
| Pierwsza krótka odpowiedź, w tym pierwszy JIT/prefill | TTFT4.45s; całość4.71s; 24input/6output |
| Drugi uczestnik | TTFT0.57s; całość0.73s; 25input/8output |
| Kontynuacja A | TTFT0.18s; całość0.34s; 18input/9output |
| Peak alokacji Torch GPU | 938104832B (~895MiB) |
| Peak RSS procesu | 1705885696B (~1.59GiB) |
| Cancel w rzeczywistym prefill | 43.5ms do potwierdzenia końca |
| VRAM systemowy przed/po cleanup | 1625/1624MiB |

Uzyskano poprawne krótkie odpowiedzi o dodawaniu i stolicy Francji oraz
kontynuację wcześniejszego pytania A. B pozostawał pusty po próbie A; wykonanie
B nie zmieniło fingerprintu A; brak współdzielonych storage tensorów. Reset A
pozostawił B bez zmian. Proces zakończony. To dowód techniczny, nie benchmark
jakości współpracy ani formalny odbiór C0. Prywatny pełny receipt jest lokalny.
Kontrolna inferencja Qwen i pełny receipt hosta wymagają późniejszego, oddzielnego
odbioru pod C0. CI korzysta z deterministycznych fixture i nie ładuje modeli/GPU.
