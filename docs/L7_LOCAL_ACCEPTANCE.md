# L7 — odbiór lokalny 2026-10-22

Repo: venom-module-cooperation-lab; gałąź `codex/rwkv7-g1k-2.9b`.
Zachowano cały wcześniejszy zaległy kod (RWKV 2.9B, HRM/Huginn, serie gier).
Nie pracowaliśmy na main, więc nie tworzono kolejnej pustej gałęzi.
Brak publikacji, PR i scalenia na GH w tym etapie.

## Zakres

Cztery środowiska, 13 wersjonowanych przypadków, referencje minimax/nim-sum/
pamiętające ujawnienia/BFS. Nowy protokół game-eval-v2, niezależne stany A/B,
fresh/carry, replay/native RWKV, budżet Huginn, trwałe wyniki i jawne wznowienie.
Nowa zakładka ewaluacji obok istniejącej rozmowy, PL/EN/DE, preflight, START/STOP,
Resume i terminalne DELETE bez potwierdzenia. JSON/JSONL/CSV zachowuje podejścia.
Reguły Nim/Memory adaptowano z TextArena MIT bez całego pakietu; pełna licencja
jest w repo. Nie doinstalowano pakietów, modeli ani kolejnego venv.

## Wewnętrzny przegląd

Trzej workerzy realizowali oddzielnie reguły/referencje, adaptery/pamięć oraz UI.
Integracja i wspólne API/storage miały jednego właściciela. Dodatkowy przegląd
krzyżowy i regresje wykryły i usunęły: guard wyłączonego modułu, fałszywie wczesny
terminal przed unload, stuck cancelling, ponowny cleanup po close=False,
brak wyniku poprzedniej partii w carry, blokadę wznowienia infrastrukturalnego,
zamianę stron model–model, wyścig capabilities w UI i odczyt cache po retencji.
Nie zmieniano historycznych wyników ani parsera v1.

## Rzeczywiste próby modeli

Przypadki: ttt-win-v1, nim-last-stone-v1, memory-seed17-v1, sokoban-push-v1.
Jedna odpowiedź na decyzję; brak maskowania, retry i naprawiania odpowiedzi.
Najpierw RWKV przy 64 tokenach (4 invalid_format), następnie jawna nowa seria
z 256 tokenami, limitem 30 s i seed=17. Surowe dane zachowano poza Git.

| Model / konfiguracja | Zaplanowane | Rozpoczęte | Wyniki |
|---|---:|---:|---|
| RWKV-7 2.9B replay/fresh, 256 tokenów | 4 | 4 | 4 invalid_format |
| HRM-Text-1B replay/fresh, 256 tokenów | 4 | 4 | 4 invalid_format |
| Huginn 8 kroków, 256 tokenów / 30 s | 4 | 1 | 1 decision_timeout, 3 skipped |
| RWKV native/fresh, dwie partie Nim | 2 | 2 | 2 invalid_format |
| RWKV native/carry, dwie partie Nim | 2 | 1 | 1 invalid_format, 1 skipped po błędzie bloku |
| Huginn 16 / 32 / 64, jeden Nim każdy | 3 | 3 | timeout / illegal_action / timeout |
| Huginn 8 kroków, 32 tokeny / 90 s | 4 | 4 | 3 invalid_format, 1 illegal_action |

We wszystkich ukończonych przebiegach kontrolnych runtime wracał do available,
active_operations=0. Pierwszy test odkrył przedwczesny completed przed unload;
został zachowany, poprawiony i osłonięty testem regresji. Nie przedstawiamy
pierwszej obserwacji owned po completed jako PASS.

To negatywne wyniki zgodności odpowiedzi/latencji, nie dowód poprawnej strategii
lub nauki. Szczególnie carry zakończone po pierwszym błędzie nie potwierdza
adaptacji przez kolejne rzeczywiste partie; izolacja/ciągłość mają oddzielne testy
CPU, a nie sfabrykowane wyniki GPU. Koszt missing/null pozostaje brakiem pomiaru.

## Bezpieczeństwo i skanery

Lokalny Snyk 1.1302.0 dla requirements.txt, organizacja mpieniak01: exit0,
ok=true, uniqueCount=0. Obejmuje dwie zależności aplikacyjne i ich rozwiązanie
w istniejącym host venv; nie jest nowym audytem całego opcjonalnego stosu ML.
Znane ograniczenia Torch z wcześniejszej kwalifikacji nie znikają przez ten wynik.
Sonar PR/CI nie uruchomiono: zgodnie z zakresem nie ma PR GitHub. Lokalny
Docker/scanner nie był dostępny (daemon nie działa); nie ogłaszamy Sonar PASS.
Nie zmieniono progów, definicji new code ani wyjątków skanerów.

## Dane i wdrożenie

Surowe próby lokalne: `~/.local/state/venom/cooperation-lab/acceptance/l7-20261022`.
Raporty mają prywatny status, nie trafiają do Git. Stare próby operatora zachowane.
Host pozostaje /home/ubuntu/venom w Ubuntu-Venom, API 8800/UI 3300, core 4ef755a6.
Mirror odtwarza oficjalny prepare-optional-module-node-paths.mjs; nie kopiowano
sekretów i nie przełączano globalnego modelu operatora. Nie wykonano ARM, ruchu
ani zmiany kamery robota. Bieżące SHA wdrożenia i końcowe kontrole poniżej.

## Końcowe lokalne kontrole

- Python: **611 PASS**, 2 ostrzeżenia deprecacji z FastAPI/Starlette hosta;
  coverage **96,99%** (próg 90). Ruff/format oraz mypy 37 źródeł PASS.
- Pełne `make pr-fast HOST=/home/ubuntu/venom` PASS na kodzie 54f303c;
  katalog/grupy, host contracts i nowe linie **96,17% / próg 80** PASS.
- Po osobnej poprawce historii UI: **44 frontend PASS**, TS/lint PASS,
  coverage **98,33%**. Ponownie sprawdzono katalog/grupy/coverage Python — bez
  zmiany produkcyjnego Pythona ani podmiany raportu. Drobne formatowanie czasu
  ogranicza prezentację do 3 miejsc; eksport zachowuje pełną dokładność.
- Rzeczywisty Playwright w Windows: dotychczasowa rozmowa obecna; nowa zakładka,
  preflight, START/STOP własnej próby, anulowanie, powrót admission do available/0,
  eksport JSONL, DELETE bez potwierdzenia oraz404 po DELETE PASS. Stare próby
  operatora zachowano; usunięto wyłącznie własny anulowany test 4409fa6e.
- Historia Huginn przywraca właściwy model,4 przypadki, 32 tokeny i 90 s. Terminalna
  seria automatycznie wyłącza STOP i włącza eksport/Delete. Konsola: 0 błędów;
  pozostają ostrzeżenia preload fontów z powłoki hosta.
- API/panel HTTP200; finalny runtime available, active_operations=0.
  Backend wdrożony 54f303c; późniejsze commity dotyczą UI/dokumentacji, oficjalny
  mirror zsynchronizowany. Core 4ef755a6 ma wyłącznie wcześniejsze/generowane
  pliki rejestracji i next-env.d.ts, bez ręcznie dopisanej funkcji L7.

Zrzuty i pobrany eksport pozostają w prywatnym output/playwright hostaWindows.
Nie wykonano ani push, ani utworzenia PR, ani merge. Kolejnym krokiem wydania
mogą być zdalne kontrole po osobnej autoryzacji publikacji, z jawnymi
ograniczeniami jakości modeli i bez przypisywania im zaliczonych rozgrywek.
