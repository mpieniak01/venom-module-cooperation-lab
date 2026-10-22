# Klasyczna gra kółko i krzyżyk — pięć partii, 2026-10-22

Użytkownik poprosił o powtórzenie porównania na dotychczasowej grze zamiast
nowego protokołu ewaluacji. Nie zmieniano implementacji ani ustawień runtime.
Kod lokalny 2485e0e (późniejszy a72d82f zawiera tylko poprzedni raport).

## Protokół i pamięć

Każdy model grał dwoma oddzielnymi sesjami A/X i B/O; A zawsze zaczynał.
`scenario_id=tic_tac_toe`, `mode=game_competitive`, `game_count=5`,
`remember_games=true`, język PL, seed 17, do 9 ruchów/partię, budżet 256 tokenów.
Istniejący runner wymusza dla tej trójki structured, temperature=0/top_p=0,
a także wybór jednej z legalnych współrzędnych przez `allowed_outputs`.

Wagi były ładowane raz na serię, lecz natywny stan resetowany między partiami.
Pamięć stanowi tekstowe podsumowanie maksymalnie trzech wcześniejszych gier.
To **nie jest native/carry L7** ani trening wag. Solverów nie przekazywano modelom;
minimax użyto dopiero offline do oceny zapisanych ruchów.

## Wyniki

| Model | Ukończone | A wygrał | B wygrał | Remisy | Różne przebiegi | Czas całej serii |
|---|---:|---:|---:|---:|---:|---:|
| rwkv7-g1k-2.9b | 5/5 | 5 | 0 | 0 | 2 | 113.5 s |
| hrm-text-1b | 5/5 | 5 | 0 | 0 | 1 | 29.2 s |
| huginn-0125 | 5/5 | 5 | 0 | 0 | 2 | 129.6 s |

Czas obejmuje ładowanie, grę i zakończenie po odpowiedzi START; nie jest samym
czasem generacji. Wszystkie 15 partii ukończone, bez błędów formatu/runtime.
Po każdej serii admission available, active_operations=0.
Wyniki wszystkich plansz odtworzono niezależnie i potwierdzono zgodność sędziego.

## Strategia i powtarzalność

| Model | Przeoczone natychmiastowe wygrane A/B | Przeoczone blokady A/B | Ruchy zachowujące wartość minimax |
|---|---|---|---|
| rwkv7-g1k-2.9b | 8 / 4 | 4 / 13 | 20/41 (48.8%) |
| hrm-text-1b | 0 / 0 | 0 / 5 | 20/35 (57.1%) |
| huginn-0125 | 0 / 4 | 4 / 5 | 16/35 (45.7%) |

To liczba okazji do taktycznych decyzji; jeden ruch może mieć kilka flag.
Minimax ocenia wartość pozycji, więc ruch z już przegranej pozycji może zachować
wartość bez możliwości uratowania wyniku. Mała seria nie ustanawia rankingu modeli.

- RWKV: druga partia była krótsza i miała mniej błędów; partie 3–5 powtórzyły
  przebieg pierwszej. Brak utrzymującej się poprawy.
- HRM-Text: wszystkie pięć partii identyczne, po 7 ruchów. Brak widocznej adaptacji.
- Huginn: od drugiej partii zmienił przebieg, lecz 2–5 były identyczne, po 7 ruchów.
  Zmiana nie poprawiła wyniku ani taktyki: B nadal przeoczał blokadę i od drugiej
  partii również własną okazję wygranej.

Klasyczny transport gry działa. Legalność odpowiedzi jest wspierana przez
ogranicznik generacji; nie dowodzi samodzielnej obsługi JSONv2. Włączenie pamięci
tekstowej nie przyniosło tu trwałej poprawy strategii. Nie można z tego wyciągać
wniosku o braku zdolności modeli do adaptacji przy innym mechanizmie pamięci.

## Odtworzenie

Panel: Laboratorium → Rozmowa i serie → Historia prób.

- `rwkv7-g1k-2.9b`: `51dde318d12b4255a33e96cb4c7d6028`.
- `hrm-text-1b`: `54efa1b1381f4f6a81d506d1b5cca41f`.
- `huginn-0125`: `0a9f5901eb404aafb7e8ebeeb792be0f`.

Surowe eksporty i analiza są poza Git:
`~/.local/state/venom/cooperation-lab/acceptance/classic-five-20261022/`.
Poprzedni [test ścisłego carry](CARRY_FIVE_20261022.md) pozostaje odrębnym
wynikiem negatywnym. Nie zmieniono jego danych ani parsera dla poprawienia oceny.
Publikacja GH nie była wykonywana.
