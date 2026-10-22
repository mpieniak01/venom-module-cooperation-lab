# Nim i Memory — dopasowanie formatu i lokalne próby, 2026-10-22

Gałąź codex/rwkv7-g1k-2.9b, lokalnie bez publikacji GH. Końcowy kod 1e1405d
(poprzednie kroki a008472, 876b873). API 8800/UI 3300, core 4ef755a6.

## Wprowadzone zmiany

- Mapper action-map-v2: Nim heap=H take=N, jawne zdanie take N stones from heap H,
  koperty JSON action=take/remove z heap i take/count. Memory cards=I,J,
  reveal/flip/match I and J, obiekt cards, card1/card2 oraz tablica JSON [I,J].
  Zachowuje podane liczby; nie zmienia indeksów zero-based i nie wybiera ruchów.
- Osobne krótkie instrukcje akcji Nim/Memory, przy kolejnych decyzjach krótka
  przypominajka formatu. Zwarty JSON; identyfikatory diagnostyczne są w dzienniku,
  nie zajmują już promptu tych gier. Wszystkie obserwacje gry i surowe odpowiedzi
  pozostają w historii. Reguły przekazywane raz jak wcześniej.
- W HRM PrefixLM usunięto z game-eval-v2 obce przykłady arytmetyki i stolicy Francji.
  W próbie kontrolnej model powtórzył Paris z naszego szablonu. Nowy warunek
  direct-game-v2 zawiera wyłącznie rzeczywiste komunikaty gry; dawny v1 bez zmian.
  To korekta promptu, nie nowy checkpoint ani trening.
- Większy kontekst jest jawny: zweryfikowany adapter Ollama/gemma4 deklaruje do 8192,
  pozostałe adaptery nadal 2048. Formularz pokazuje Budżet kontekstu i ustawia 8192
  po wybraniu Gemmy4. API nadal domyślnie 2048; większą wartość trzeba przesłać jawnie.
  Ograniczenie dotyczy v2, stary GenerationParameters/v1 nadal odrzuca większy budżet.
  Preflight blokuje nadmiarowy budżet innych adapterów. Poprawiono również inicjalizację
  GenerationParameters w serwisie: protokół v2 musi być ustawiony przed walidacją.
- Limit historii 16 KiB/512 wiadomości i konserwatywne szacowanie UTF-8 adaptera Ollama
  pozostają aktywne. Nie podmieniono ich na niezweryfikowany tokenizer ani nie
  obcinano historii. Większy budżet nie jest obietnicą ukończenia całej gry.
- Konfiguracja i decyzje rejestrują wersję mappera, prompt_policy i kodowanie.
  Wznowienie nie miesza wersji: niezgodność mappera/polityki HRM wymaga nowej serii.
  Nie nadpisano wyników wcześniejszych prób.

## Rzeczywiste wyniki

Nim [3,4,5] przeciw optymalnemu botowi, model A, bez zamiany stron.
Memory 4×4 seed przypadku 17, solo, bez ujawniania zakrytych kart.
Fresh/history_replay, greedy, 128 tokenów/decyzję, 90 s, seed 17; Huginn 8 iteracji.
Budżet Gemmy 8192, pozostałe 2048, zatem to test obsługi, nie równy ranking jakości.

| Model | Nim | Memory |
|---|---|---|
| RWKV-7 2.9B | brak końcowej akcji w 128 tokenach | brak końcowej akcji w 128 tokenach |
| Huginn | echo promptu, nie akcja | echo promptu, nie akcja |
| HRM-Text po korektach | odpowiedź 1, brak pełnego ruchu | pierwszy ruch [0,5] trafia parę; drugi powtarza już dopasowane karty i jest prawidłowo odrzucony |
| Gemma4 | gra ukończona; 2 legalne ruchy modelu, przegrana z botem | 12 legalnych ruchów, 1 para, potem context_limit |

Format Gemmy4 jest poprawny w obu grach. W Nim pierwsza decyzja traci pozycję
wygrywającą. W Memory 12 ruchów zamiast wcześniejszego 1, jednak powtarza wybory
i pomija 8 znanych par; nie można ogłosić poprawnej strategii ani skutecznego uczenia.
Rzeczywisty prompt_eval_count przed zatrzymaniem Memory wynosi 2825: context_limit
wynika z konserwatywnego limitu bajtowego adaptera, a nie z potwierdzonego
wyczerpania 8192 rzeczywistych tokenów. Jawne ograniczenie pozostaje widoczne.

HRM w Memory nie ma już błędu formatu: obie odpowiedzi [0,5] są mapowane.
Druga jest nielegalna ze względu na stan gry. Samego 1 w Nim ani niedokończonego
rozumowania RWKV nie da się zmapować bez wymyślenia brakującej decyzji.
Huginn nie otrzymał kolejnych prób po wykryciu echa. Wagi i generacja nie były
maskowane do listy legalnych odpowiedzi, w odróżnieniu od klasycznego TTT.

## Próby i ich przejrzystość

Pierwsza partia 8 prób wykryła domieszkę przykładów HRM oraz błąd inicjalizacji
większego kontekstu Gemmy (2 runtime_error przed generacją, nie błędy modelu).
Po konkretnych naprawach powtórzono tylko 4 próby HRM/Gemma; na podstawie odpowiedzi
HRM [0,5] dodano obsługę tablicy i wykonano 1 kontrolę Memory HRM.
Łącznie 13 nowych zapisów, bez ukrytych retry wewnątrz decyzji. Wszystkie zachowane.
Nie powtarzano RWKV/Huginn w poszukiwaniu korzystnego wyniku.

Końcowe identyfikatory:
- RWKV Nim dd0fce6aa42d422f9e80c044da77b92a; Memory49cc3ebb51a34bebb8de4dd89e59f0b6.
- Huginn Nim e11d14b4200b4e9cae8a22b2e891a7c7; Memory1df0d0c3dec34926a1352d486c7a064b.
- HRM Nim1bd8649c2bc64942a82435b9e36e319f; Memory14ca4d80d63a4f98b89128feb48a703c.
- Gemma Nim1058f9ef105b44e7bc79f0df6466c90e; Memorydac848aaac2840a2a0a05d2c405f0f0a.

Surowe dane poza Git pod ~/.local/state/venom/cooperation-lab/acceptance/:
nim-memory-format-20261022, nim-memory-format-corrected-20261022,
nim-memory-hrm-array-20261022. Legalne akcje odtworzono offline bez generacji.

## Weryfikacja

make pr-fast HOST=/home/ubuntu/venom PASS: 657 Python, coverage 96,99%;
44 frontend, Ruff/format/mypy 38 źródeł, hostcontracts; nowe linie 96,22% / próg 80%.
Testy obejmują rzeczywiste warianty odpowiedzi, brak zgadywania, legalność,
przekazanie 8192przez serwis, wyłączenie obcych przykładów HRM i ochronę zakrytych kart.
Nie zmieniono pakietów, progów skanerów ani kwalifikacji innych modeli.

Playwright Windows: Format odpowiedzi/Mapowanie odpowiedzi i Budżet kontekstu
widoczne; wybór Gemmy ustawia 8192. Bez dodatkowego START z przeglądarki.
Po próbach runtime available / active_operations=0, API i panel HTTP200.
Oficjalny mirror zsynchronizowany, nie zatrzymywano aktywnych eksperymentów.
Nie wykonano ruchu robota ani zmian kamery. Publikacji GH nie wykonywano.

Dalsze ograniczenia: dla modeli bez końcowej decyzji potrzebny byłby osobno
opisany tryb ograniczonej generacji (warunek wspomagany, jak TTT); nie należy
udawać, że zwykłe mapowanie już go zapewnia. Pełne długie Memory wymaga też
dokładniejszego pomiaru tokenów/budżetu i oddzielnej oceny korzystania z historii.
