# Rozszerzenie katalogu laboratorium — odczyt lokalny 2026-10-21

Laboratorium wykonuje inferencję i porównania, nie trening wag. Modele nie muszą
być adapterami Academy. Obecny rejestr jest celowo statyczny: RWKV 0.4B i Qwen3
4B, z osobnymi kontekstami A/B i przypiętymi receiptami kwalifikacji.

## Zainstalowane modele tekstowe Ollamy

Odczytano lokalne /api/tags i /api/show (metadane, bez ładowania wag): 12 nazw,
10 unikalnych digestów, wszystkie z completion i szablonem. Rozmiary poniżej są
zaokrąglonym rozmiarem modelu według API w GB dziesiętnych, nie zajętością VRAM
ani dodatkowym zapotrzebowaniem na dysk; warstwy mogą być współdzielone.

| Model / wagi | GB | Laboratorium obecnie |
|---|---:|---|
| Qwen3 4B | 2,50 | Zakwalifikowany |
| Llama 3.2 1B | 1,32 | Wymaga rejestracji/krótkiej kwalifikacji |
| Gemma 2 2B | 1,63 | Jak wyżej |
| Zachowany adapter self_learning (Gemma 2) | 1,64 | Jak wyżej; nie wymaga ponownego treningu |
| Qwen2.5 Coder 3B | 1,93 | Jak wyżej |
| Gemma 3 4B | 3,34 | Jak wyżej |
| Qwen2.5 Coder 7B | 4,68 | Jak wyżej |
| Qwen3.5 9B | 6,59 | Jak wyżej |
| Gemma 4 | 9,61 | Jak wyżej; osobna ocena pamięci |
| Codestral 22B | 12,57 | Jak wyżej; osobna ocena pamięci/offload |

qwen3.5:latest / :9b oraz gemma3:latest / :4b są aliasami tych samych digestów.
Nie należy przedstawiać ich jako dodatkowych niezależnych wag. RWKV 0.4B jest
osobnym istniejącym komponentem poza tą listą Ollamy.

## Dlaczego nie kopiować katalogu core wprost

GET /api/v1/models zwraca także cache, metadata, manifests-v2, preprod,
sonar-regression-20261018 i research jako vllm/chat_compatible=true. Odczyt
potwierdził brak config.json w ich korzeniach: cache zawiera huggingface/pip,
preprod i sonar-regression tylko ollama_models_cache.json, manifests-v2 jest
pusty, research jest kontenerem rwkv7-g1, metadata zawiera metadane digestów.
To nie są pojedyncze modele do załadowania przez vLLM. Reguła zgodności core
domyślnie dopuszcza takie katalogi i nie weryfikuje dla vLLM kompletności wag.

ONNX Gemma i własny multi_runtime wymagają adaptera laboratorium; sama deklaracja
chat_compatible nie dowodzi obsługi generate/cancel/reset i wspólnego admission.
Piper i model podłogi Rider nie są tekstowymi rozmówcami. Zdalni dostawcy są
oddzielnym zakresem: adapter, koszty, poświadczenia i decyzja o wysyłaniu treści.

## Proponowany zakres realizacji

1. Dynamiczny katalog rzeczywistych modeli lokalnych, początkowo Ollama:
   capability completion, szablon, digest, deduplikacja aliasów. Bez pobrań.
2. Zachować historyczne ID/hash kontrolnego Qwen i RWKV. Nowe specyfikacje
   przypinać do digestu/szablonu/runtime, nie do zmiennego aliasu latest.
3. Pokazywać stany: gotowy, do sprawdzenia, brak adaptera, inna modalność.
   Odczyt katalogu nie uruchamia prób ani nie zmienia globalnego wyboru modelu.
4. Krótka jawna kwalifikacja wybranego modelu: load, ograniczona odpowiedź,
   dwa konteksty, reset/cancel i zwolnienie zasobu. Nie duży benchmark wszystkich
   modeli i nie szkolenie. Zmiana digestu unieważnia dawny receipt.
5. Wybór modelu dotyczy jednych wag i oddzielnych kontekstów A/B; różne modele
   dla A i B byłyby dodatkową przebudową, nie efektem samego poszerzenia listy.
6. Oddzielnie naprawić klasyfikację katalogów pomocniczych w core. Nie usuwać
   ich przy tym automatycznie i nie udostępniać ich jako uruchamialnych modeli.

Na tym etapie wykonano wyłącznie analizę/metadane. Nie włączono dodatkowych
modeli, nie uruchamiano inferencji i nie zmieniano rejestru ani katalogu core.

## Doprecyzowanie po sprawdzeniu plików i selektora czatu

Nie utożsamiać cache z odpadami. W cache potwierdzono rzeczywiste wagi Gemma 2
(około 5,23 GB), MiniLM (dwa snapshoty po około 91 MB), Depth Anything V2 i
SegFormer. Sam katalog cache jest kontenerem, nie modelem vLLM do uruchomienia.
`research` zawiera zakwalifikowany RWKV, więc również nie jest katalogiem do
usunięcia. Żadnych danych w tej analizie nie kasowano.

Potwierdzono kompletne pliki wymagane przez indeks wag i tokenizer dla trzech
checkpointów: Gemma 3 bazowa, checkpoint training_20260314 (Gemma 3) oraz
self_learning (Gemma 2). To pełne checkpointy, mimo nazwy venom-adapter;
nie same pliki adapterów LoRA. Shardy mają różne inode i nlink=1, nie są tymi
samymi plikami przez hardlink. Nie liczono pełnych hashy wielu GB i nie badano,
jak duże są różnice wytrenowanych wag. ONNX Gemma 3 ma dekoder oraz około
5,38 GB danych zewnętrznych. Piper i rider-floor mają realne wagi, innej modalności.

Brak wag potwierdzono w preprod, sonar-regression-20261018, metadata,
manifests-v2, pustym gemma-3-4b-it-onnx-cpu-int4 i good--model-onnx z samymi
metadanymi. Brak wag nie dowodzi, że każdy plik pomocniczy jest zbędny.

### Co już ma czat Venoma

Czat `/chat` używa `getUnifiedModelCatalog()` z
`GET /api/v1/system/llm-runtime/options`, a nie wyłącznie surowego `/models`.
Ten katalog prawidłowo odfiltrował opisane pomocnicze foldery:

- Ollama: online, 10 unikalnych zestawów wag, adapter self_learning oznaczony
  jako adapter_artifact; widoczne pozostałe modele bazowe.
- vLLM: inactive; trzy rzeczywiste checkpointy tekstowe.
- multi_runtime: inactive; skonfigurowany google/gemma-4-E2B-it. Sama deklaracja
  katalogowa nie stanowi testu ładowania tego silnika/modelu.
- ONNX: offline/runtime_not_installed, bez modeli w zunifikowanym selektorze.
  Istnienie plików ONNX nie potwierdza gotowości tego runtime.
- Dostawcy chmurowi: disabled/configured=false; lista nazw to nie dostępność.

Komponent ChatComposer w cockpit-chat-thread.tsx jest powiązany z trybami czatu,
adapterami Academy, wdrożeniem adaptera, aktywacją modelu i globalnymi setterami
silnika. Hook use-cockpit-model-activation może wywołać setActiveLlmServerFn lub
setActiveLlmRuntimeFn. Tego zachowania laboratorium nie powinno dziedziczyć.
Wspólny SelectMenu jest natomiast elementem prezentacyjnym sterowanym propsami.

### Decyzja projektowa

Najmniejszy spójny zakres: **reuse zunifikowanego katalogu i małych kontrolek,
prosty selektor laboratorium Silnik → Model**. Nie kopiować całego ChatComposer
ani nie tworzyć drugiego skanera wszystkich katalogów. Wybór zapisuje tylko
konfigurację próby; uruchomienie nadal przechodzi przez admission laboratorium,
adapter, przypiętą tożsamość modelu i jawny stan gotowości. Pozycje bez adaptera
lub działającego silnika mają wyjaśniony stan zamiast obietnicy działania.
Nie filtrujemy modeli po trainable: inference-only również jest właściwe.
Dla osobnych wag A/B potrzebny byłby osobny zakres zmiany runnera.

Ta część jest analizą bez zmiany selektorów, usług i aktywnego modelu.
