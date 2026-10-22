# Serie gier i adaptacja w kontekście

Lokalnie, 2026-10-22. W ustawieniach scenariusza **Kółko i krzyżyk** wybierz
**Liczba gier: 1–10**. Dla serii obowiązuje do 9 ruchów na partię, zakończenie
po rzeczywistej wygranej/remisie i jeden wspólny STOP. **Pamięć poprzednich gier**
jest domyślnie włączona. Wyłącz ją w osobnej serii, aby uzyskać punkt odniesienia.

To badanie adaptacji na podstawie kontekstu, nie trening wag ani dowód poprawy.
RWKV-7 aktualizuje swój stan przy przetwarzaniu kontekstu; HRM wspiera few-shot,
a Huginn zwiększa obliczenia przez rekursję. Żaden z naszych adapterów nie
uruchamia gradientów, optymalizatora ani zapisu zmienionych wag.

## Polityka pamięci

- Jedna seria to jedna próba w historii i jedno załadowanie wag.
- Przed nową partią resetowane są plansza i oba stany/cache robocze. Wagi zostają
  w procesie. Przy pamięci ON oba oddzielne konteksty otrzymują publiczny zapis
  ruchów i wyniki **ostatnich trzech ukończonych partii** wraz z własną rolą A/B.
  Model może wykorzystać je jak przykłady. Pamięć OFF nie przekazuje tych danych.
- To świadoma ograniczona polityka replay, również dla RWKV: nie zachowujemy
  nieograniczonego ukrytego stanu między partiami. RWKV nadal zachowuje swój stan
  w obrębie partii. Inaczej dotychczasowy limit 2048 tokenów kończyłby serię.
- Nie przekazujemy prywatnych rozumowań przeciwnika, gotowych rad strategicznych
  ani ruchów minimax. Zachowany jest dekoder legalnych pól dla RWKV/HRM/Huginn.
- Po zakończeniu serii pamięć sesji znika; zapis wyników pozostaje w historii.
  Nowa próba nie dziedziczy doświadczeń poprzedniego uruchomienia.

## Co widać

Numer aktualnej partii, wynik A/B/remisy i lista wyników poszczególnych partii.
Wiadomości ruchów mają numer partii. Pełny eksport zawiera przebieg oraz
niezmienną konfigurację: `game_count`, `remember_games`, scheduler
`board-series-memory-v1`, schema 4. Dla jednej gry zachowano dawny kontrakt.

Porównuj serie tego samego modelu i wariantu z pamięcią ON/OFF. Sama liczba
wygranych nie dowodzi uczenia: obie strony są tym samym modelem, A zawsze
zaczyna jako X, a dekoder usuwa nielegalne odpowiedzi. Wyniki mogą być identyczne
lub gorsze mimo przekazanych przykładów. Nie liczymy fikcyjnej metryki „nauki”.

## Ograniczenia i kontrola

Do 10 partii, kontekst nadal 2048 tokenów; budżety sumaryczne skalowane liczbą
gier, czas całej próby do 1800 s i limit dyskowy bez zmian. Pamięć i dziennik
są ograniczone. Panel przechowuje do 512 zdarzeń, catch-up do 8 stron po 100,
co obejmuje maksymalną serię 90 ruchów. STOP/błąd kończy serię bez uruchamiania
kolejnych partii. Nie wykonujemy automatycznej kontynuacji po restarcie API.

Testy sprawdzają reset planszy, inicjatywę A, izolację A/B, przeniesienie tylko
rzeczywistych ukończonych wyników, ON/OFF, retencję 3 partii, wspólne budżety,
idempotencję i prezentację wyników. Próby GPU potwierdzają integrację, nie
statystyczną poprawę jakości.

Źródła:
- https://github.com/BlinkDL/RWKV-LM
- https://huggingface.co/sapientinc/HRM-Text-1B
- https://huggingface.co/tomg-group-umd/huginn-0125


## Odbiór lokalny

Rzeczywiste serie z pamięcią ON, po dwie gry, 2026-10-22:

| Model | ID próby | Wyniki | Obsługa serii |
|---|---|---|---|
| RWKV-7 0.4B | `b8ccf904e6da4306a699de94bcd874e0` | A, A | completed, bez błędów |
| HRM-Text-1B | `c8a47e75c39b4286b9d2533cd9bbe62a` | A, A | completed, bez błędów |
| Huginn-0125 | `7e1a5444382646869c74fd2248ad31d0` | A, B | completed, bez błędów |

Po każdej próbie wspólny runtime: available / 0 aktywnych operacji.
Prywatne eksporty: `~/.local/state/venom/cooperation-lab/acceptance/series-20261022`.
Powyższe próby nie dowodzą uczenia ani przewagi pamięci; brak statystycznego
porównania ON/OFF. Pamięć OFF oraz dokładną zawartość przekazanego doświadczenia
sprawdzono testami runnera. Przeglądarka: wpisanie 3 gier zachowuje 9 ruchów na
partię, odblokowuje przełącznik pamięci i pozostawia dostępny START.

Kontrole końcowe: **382 Python PASS, 96,19% coverage, 32 frontend PASS**;
Ruff, mypy, TypeScript, lint i kontrakt opcjonalnego modułu hosta PASS.
