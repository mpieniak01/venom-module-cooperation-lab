# Jawne mapowanie odpowiedzi gier — lokalny odbiór 2026-10-22

Kod 3753bb5, lokalna gałąź codex/rwkv7-g1k-2.9b. Bez publikacji GitHub.
Na prośbę użytkownika dodano mapowanie odpowiedzi zamiast wymagania identycznego
formatu od wszystkich modeli. Wersja action-map-v1 zapisuje przekształcenie
obok surowej odpowiedzi; nie zmienia silnika gry ani nie podpowiada ruchu.

## Kontrakt

API response_mode: strict_json (domyślne API i stare zapisy) lub mapped.
Nowy formularz domyślnie wybiera Mapowanie odpowiedzi; stare konfiguracje bez
pola przywracają strict_json. Wyboru dokonuje operator przed preflight/START.
Nie zmieniono dawnych wyników, parsera v1 ani istniejącego maskowania TTT.

Mapowanie obsługuje:
- JSON akcji zgodny z grą, pojedynczy blok json, jawny prefiks Answer/Final answer,
  oraz końcową akcję po zamkniętym bloku think;
- Sokoban: move right lub obiekt action=move z move/value;
- Nim: take N stone(s) from heap H, z zachowaniem podanych liczb i indeksu;
- Memory: cards/reveal I and J lub cards I,J, bez zgadywania wartości kart;
- TTT: pojedyncza współrzędna A1–C3, opcjonalnie z prefiksem move.

Nie przeszukuje rozumowania w poszukiwaniu korzystnego ruchu. Odpowiedź
niejednoznaczna, echo obserwacji, kilka obiektów lub niedokończony think pozostają
błędem. W trybie mapped duplikaty kluczy i liczby niefinitywne są odrzucane.
Walidator gry nadal odrzuca ściany, zajęte pola, błędne indeksy i inne nielegalne
akcje. Nie dodano retry/fallback/modelu naprawiającego ani rozwiązania solvera.
Nie udajemy, że mapowanie jest ogranicznikiem dekodowania TTT: nie wymusza ono
wyboru legalnej akcji podczas generacji.

response_mapping w decyzji zawiera version/mapped/rule. Raport by_game liczy
mapped_responses, a response_mapper wskazuje wybrany tryb. Surowy response oraz
raw_response pozostają zachowane; szczegóły mapowania są w dzienniku i JSON.

## Rzeczywiste próby po wdrożeniu

Po jednej nowej próbie sokoban-push-v1 na trzech modelach, historia świeża,
greedy, seed17, 128 tokenów, limit90s, kontekst2048, Huginn8iteracji.
Instrukcje i obserwacje identyczne jak we wcześniejszych ścisłych próbach.
Wynik wszystkich: jedno legalne pchnięcie right, success=true, game_completed.

| Model | Zapisana odpowiedź | Zmapowana akcja | Czas decyzji |
|---|---|---|---:|
| HRM-Text | move right | {"move": "right"} | 2.22 s |
| Huginn | {"action": "move", "move": "right"} | {"move": "right"} | 9.64 s |
| Gemma4 | {"action": "move", "value": "right"} | {"move": "right"} | 13.78 s |


Nie powtarzano RWKV na GPU: poprzednie odpowiedzi były niedokończonym
rozumowaniem bez końcowej akcji i parser jawnie je odrzuca. Sprawdzono offline
pierwsze odpowiedzi wszystkich 12 poprzednich prób, bez nadpisywania wyników:
odzyskano cztery wcześniej odrzucone legalne akcje (HRM Nim i Sokoban,
Huginn Sokoban, Gemma Sokoban). To analiza formatu, nie cztery nowe zaliczone gry.
Nie naprawiano limitu kontekstu Ollama/Memory w tej zmianie.

## Kontrole i wdrożenie

- make pr-fast HOST=/home/ubuntu/venom PASS: 638 Python, coverage96,99%,
  44 frontend, Ruff/format/mypy/hostcontracts; nowe linie96,21% / próg80%.
- Testy odrzucają niejednoznaczne odpowiedzi i potwierdzają brak korekty
  nielegalnego ruchu, brak retry, zachowanie surowego tekstu i starego trybu.
- Oficjalny mirror modułów odświeżony; API przeładowano bez aktywnych eksperymentów.
- Playwright Windows: wybór Format odpowiedzi widoczny, mapped domyślnie;
  przełączanie strict_json działa. Zero błędów konsoli; powłoka nadal emituje
  ostrzeżenia. Nie uruchamiano dodatkowego eksperymentu z przeglądarki.
- Po każdej rzeczywistej próbie runtime available / active_operations=0.

Surowe eksporty, skrypt prób i analiza offline pozostają poza Git:
~/.local/state/venom/cooperation-lab/acceptance/action-map-20261022/.
Identyfikatory:
- HRM-Text: e6bbebbafdb248d48cdce5aaef3c2a8c.
- Huginn: 7855d677e5f34b5aa948d4d9d3f33413.
- Gemma4: b75dbe35685e43b887f7cf0a9cbd44f3.
