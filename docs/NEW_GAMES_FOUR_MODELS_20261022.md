# Nowe gry — cztery modele, po jednej próbie, 2026-10-22

Lokalne wdrożenie c86b655 na codex/rwkv7-g1k-2.9b. Bez publikacji GitHub.
Dodano replay v2 do istniejącego adaptera Ollama (Gemma4). Weryfikacja tożsamości,
izolacja A/B, ograniczenia kontekstu i zachowanie protokołu v1 pozostają aktywne.
Nie dodano nowego runtime ani modelu; brak natywnego stanu/iteracji dla Ollama.

## Warunki

12 zaplanowanych, 12 rozpoczętych, 12 terminalnych prób, bez pominięć i ponowień.
Jedno niezależne wywołanie ewaluacji dla każdej kombinacji model/gra:
nim-winning-v1 ([3,4,5], model A przeciw optymalnemu botowi B),
memory-seed17-v1 (solo 4×4), sokoban-push-v1 (solo, jedna skrzynia, jeden ruch).
History replay, fresh, reflection off, greedy, seed 17, legal moves listed,
128 tokenów/odpowiedź, 90 s/decyzję, kontekst 2048. Huginn: rzeczywiste 8 iteracji.
Seed decyzji jest deterministycznie wyprowadzany z przypadku i epizodu.
Nie używano maskowania, korekty JSON, dodatkowych prób ani fallbacku modeli.
Ukryte karty i wyniki solvera nie są częścią obserwacji modelu.

## Wyniki

Czasy decyzji obejmują wywołania modelu, a nie samą generację tokenów.
Czas całej próby obejmuje również ładowanie i zwalnianie runtime.

| Model | Gra/przypadek | Status epizodu | Legalne ruchy modelu | Decyzje łącznie | Cała próba |
|---|---|---|---:|---:|---:|
| RWKV-7 2.9B | nim-winning-v1 | invalid_format | 0 | 10.06 s | 51.63 s |
| RWKV-7 2.9B | memory-seed17-v1 | invalid_format | 0 | 10.37 s | 22.05 s |
| RWKV-7 2.9B | sokoban-push-v1 | invalid_format | 0 | 8.50 s | 18.05 s |
| HRM-Text | nim-winning-v1 | invalid_format | 0 | 1.88 s | 16.05 s |
| HRM-Text | memory-seed17-v1 | invalid_format | 0 | 1.16 s | 9.10 s |
| HRM-Text | sokoban-push-v1 | invalid_format | 0 | 1.13 s | 7.02 s |
| Huginn | nim-winning-v1 | invalid_format | 0 | 87.45 s | 152.90 s |
| Huginn | memory-seed17-v1 | invalid_format | 0 | 88.68 s | 155.34 s |
| Huginn | sokoban-push-v1 | illegal_action | 0 | 9.71 s | 75.25 s |
| Gemma4 (gemma4:latest) | nim-winning-v1 | game_completed | 2 | 17.74 s | 19.04 s |
| Gemma4 (gemma4:latest) | memory-seed17-v1 | context_limit | 1 | 3.25 s | 4.01 s |
| Gemma4 (gemma4:latest) | sokoban-push-v1 | illegal_action | 0 | 3.50 s | 4.01 s |


Jedna gra rozegrana do końca: Gemma4 przegrała Nim po 4 ruchach łącznie
(2 modelu i 2 bota). Pierwszy ruch [3,4,5] → [0,4,5] utracił pozycję wygrywającą
(nim-sum 2 → 1); optymalny bot następnie wymusił porażkę. Zero wygranych/rozwiązanych
zadań w całym zestawie. Zewnętrzny status completed oznacza zakończenie procedury,
nie zaliczenie zadania: status epizodu i wynik trzeba czytać oddzielnie.

## Przyczyny i ograniczenia interpretacji

- RWKV: trzy odpowiedzi wykorzystały całe 128 tokenów na rozumowanie zamiast
  zwrócić końcową akcję. To wynik dla tego budżetu i protokołu, nie ogólna ocena modelu.
- HRM-Text: odpowiedzi naturalnym językiem zamiast wymaganego JSON; w Sokobanie
  poprawny kierunek „move right” nie spełnił kontraktu akcji.
- Huginn: Nim/Memory kopiowały fragmenty obserwacji. Sokoban podał right,
  ale z dodatkowym polem action; ścisły walidator odrzucił obiekt.
- Gemma4: Nim działa formatowo, błąd jest strategiczny. Memory zatrzymało się po
  jednym legalnym odsłonięciu (0 par), zanim wykonano drugą generację: konserwatywny
  limit adaptera UTF-8 bytes + overhead przekroczył budżet 2048. To ograniczenie
  integracji/estymacji, nie dowód wyczerpania rzeczywistego tokenizowanego kontekstu
  ani ocena pamięci modelu. Sokoban wskazał right pod kluczem value i z polem action;
  obiekt nie odpowiadał schematowi move.
- Sprawdzono instrukcję: Sokoban przekazuje action_schema z kluczem move oraz
  legalną akcję right; walidator wymaga dokładnie tego klucza. Nie poprawiano
  zapisanych odpowiedzi po testach.
- Pojedyncza próba nie ustanawia rankingu ani nie bada uczenia między epizodami.

Do dalszego rozwoju: jawnie wersjonowana obsługa odpowiedzi właściwa dla adapterów
oraz poprawny pomiar/budżet kontekstu replay. Nie należy udawać przegranej
strategicznej, kiedy zadanie zatrzymał format lub adapter.

## Dowody

Wszystkie legalne akcje odtworzono offline przez replay_episode, bez nowych
wywołań modeli; wynik Nim i stan Memory zgodne z zapisami. Po każdej próbie runtime
available, active_operations=0. Po całym zestawie API i panel /cooperation-lab HTTP200.
Nie sterowano robotem/kamerą ani globalnym modelem operatora.

Przed próbami make pr-fast HOST=/home/ubuntu/venom PASS: 617 Python PASS,
coverage 96,93%, 44 frontend PASS, Ruff/format/mypy oraz host contracts PASS;
coverage nowych linii 96,04% (próg 80%). Dwa nowe testy sprawdzają replay Ollama,
izolację, zachowanie starego limitu wiadomości i odrzucanie nieobsługiwanych profili.
Nie zmieniono zależności ani progów skanerów; brak nowego zdalnego skanu/PR.

Pełne odpowiedzi i eksporty pozostają poza Git:
~/.local/state/venom/cooperation-lab/acceptance/new-games-four-models-20261022/.
Historia panelu: Ewaluacja gier. Identyfikatory prób:

- RWKV-7 2.9B, nim-winning-v1: d17670e9bc614bfea2ae60b92c7825e0.
- RWKV-7 2.9B, memory-seed17-v1: 0982429ec5ab482d850f224968afdd78.
- RWKV-7 2.9B, sokoban-push-v1: 9695b72541d84a98816400740e2dff55.
- HRM-Text, nim-winning-v1: 5724f12ec4d143e880e1184c8b3f2668.
- HRM-Text, memory-seed17-v1: f3a165b3995b443d910d31d183638178.
- HRM-Text, sokoban-push-v1: ce534c1e98b04cca91a402ccd4a7c0f0.
- Huginn, nim-winning-v1: 23a6f7694ebd4849aa2b39688d0a93f6.
- Huginn, memory-seed17-v1: 235f6554ca15441a932bd591397fee5b.
- Huginn, sokoban-push-v1: 7d4db2f031a844a7aa76997ff053c860.
- Gemma4, nim-winning-v1: 63cd3f9bab084d08a4aa80dfaf53a1a3.
- Gemma4, memory-seed17-v1: 12e1144620064e019e44940adc998634.
- Gemma4, sokoban-push-v1: de6e9ea1fc684e1f8a451fba123d73ce.
