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
Host pozostaje /home/ubuntu/venom w Ubuntu-Venom, API8800/UI3300, core4ef755a6.
Mirror odtwarza oficjalny prepare-optional-module-node-paths.mjs; nie kopiowano
sekretów i nie przełączano globalnego modelu operatora. Nie wykonano ARM, ruchu
ani zmiany kamery robota. Bieżące SHA wdrożenia i końcowe kontrole poniżej.
