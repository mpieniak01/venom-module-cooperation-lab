# Limity i profile modeli — lokalne wdrożenie 2026-10-22

Kod 6812b3a, gałąź codex/rwkv7-g1k-2.9b, bez publikacji GH.
Użytkownik wymaga przywracania ostatnio zapisanych wartości po zmianie modelu.

## Analiza i dostępne limity ewaluacji v2

| Model | Potwierdzona konfiguracja checkpointu | Limit kontekstu laboratorium | Maksimum odpowiedzi |
|---|---|---:|---:|
| RWKV-7 G1k 2.9B | nazwa przypiętego checkpointu ctx25600 | 8192 | 1024 |
| HRM-Text 1B | max_position_embeddings=4096 | 4096 | 1024 |
| Huginn-0125 | block_size=4096 | 4096 | 1024 |
| Gemma4/Ollama | istniejący adapter v2 | 8192 | 1024 |

Dotychczasowe 2048/256 były częściowo limitami naszej implementacji.
Zmiana przechodzi przez formularz, API, GenerationParameters i RwkvParameters,
z zachowaniem starego protokołu v1 (2048/256). API preflight nadal odrzuca budżet
większy niż możliwości adaptera. Wejście i odpowiedź mieszczą się wspólnie
w kontekście. Nie zastosowano RoPE scaling ani rozciągania kontekstu HF poza 4096.

Podstawy analizy: odczyt config.json rzeczywiście zainstalowanych checkpointów
HRM 22097cbcecdd1301afe30a19a3ee61b96a9863e5 i Huginn
bb6621b65e90b6a4b9b29ef88dc83866d450470c; nazwa przypiętych wag RWKV.
Źródła producentów:
- [HRM config](https://huggingface.co/sapientinc/HRM-Text-1B/blob/main/config.json).
- [Huginn config](https://huggingface.co/tomg-group-umd/huginn-0125/blob/main/config.json).
- [RWKV checkpointy](https://huggingface.co/BlinkDL/rwkv7-g1/tree/main).

To limity udostępnione do kontrolowanych eksperymentów, nie wynik nowego testu
wydajności przy maksymalnej długości wszystkich modeli. Dłuższa odpowiedź nadal
może osiągnąć limit czasu. Huginn jest szczególnie kosztowny; nie podniesiono
automatycznie wszystkich wartości domyślnych ani liczby iteracji.

## Operator i trwałość

Laboratorium → Ewaluacja gier → Ustawienia:
1. Wybierz model. Formularz od razu przywraca jego ostatnio zapisane limity.
2. Zmień Tokenów na decyzję, Budżet kontekstu i Czas decyzji (s).
3. Zapisz limity modelu utrwala te trzy wartości w magazynie Venoma.
4. Po przełączeniu na inny model i powrocie wracają wartości zapisane dla
   wybranego modelu; niezapisane edycje nie nadpisują profilu.
5. Zapis działa także bez wybranej gry. Nie uruchamia modelu ani eksperymentu.
   Do START nadal potrzebne jest osobne aktualne sprawdzenie konfiguracji.

Czas decyzji można ustawić do 300 s, a cała seria nadal ma ograniczenie 1800 s.
Pozostały limit historii 16 KiB/512 wiadomości i budżet zapisu. Ollama nadal używa
konserwatywnego oszacowania bajtowego; większy kontekst nie dowodzi naprawy strategii.

Profil jest wspólny dla tej instancji Venoma, dostępny po odświeżeniu i w innej
przeglądarce. Nie jest wyłącznie localStorage. Zawiera tylko trzy liczby i odcisk
tożsamości modelu/runtime. Magazyn settings ma istniejący limit 100 dokumentów;
nowy zapis zastępuje poprzedni profil modelu, nie tworzy kolejnych wersji.
Zmiana checkpointu/runtime lub zmniejszenie dopuszczalnych limitów oznacza profil
jako nieaktualny i wymaga ponownego zapisu. Wybranie innego istniejącego modelu
normalnie przywraca jego własny ostatni zapis.

Parametry wykonanej próby pozostają zamrożone w jej konfiguracji. Zapis profilu
nie zmienia trwającej ani historycznej serii. Dawne snapshoty formularz odtwarza
z zapisanej konfiguracji próby; przełączenie modelu znów korzysta z jego profilu.

API GET/PUT /evaluations/model-settings/{model_id}; zapis ma ścisłą walidację
i dotychczasowe uprawnienia modułu/magazynu. Nie rozszerzono globalnej konfiguracji
LLM ani panelu klasycznych rozmów. Limity dotyczą nowego toru ewaluacji gier.

## Odbiór lokalny

- make pr-fast HOST=/home/ubuntu/venom PASS: 663 Python, coverage 96,93%,
  45 frontend, TypeScript/lint/Ruff/mypy 39 źródeł oraz kontrakty hosta.
  Coverage zmienionych linii 96,11% / próg 80%.
- Testy: niezależność profili, tożsamość checkpointu, walidacja większych budżetów,
  brak ładowania adaptera podczas zapisu/odczytu, odtworzenie po zmianie modelu
  i ponownym zamontowaniu formularza.
- Playwright Windows: zapisano RWKV-7 2.9B: 8192/512/180 s; przełączenie
  RWKV→HRM→RWKV automatycznie przywróciło zapis. Pełne odświeżenie strony
  i ponowny wybór RWKV również przywróciły 8192/512/180 s. Profil pozostawiono
  jako gotową konfigurację operatora. Inne profile nie były nadpisywane.
- Przeglądarka: 0 błędów konsoli; istniejące ostrzeżenia powłoki nadal obecne.
- API i panel HTTP200, runtime available/0. Oficjalny mirror zsynchronizowany.
  Nie wykonano nowej generacji modeli, ARM ani zmiany kamery robota.

Prywatny zapis odbioru:
~/.local/state/venom/cooperation-lab/acceptance/model-budgets-20261022/.
Nie pobierano nowych pakietów ani wag, nie publikowano na GH.
