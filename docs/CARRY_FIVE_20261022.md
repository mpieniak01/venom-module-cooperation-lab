# Pięć rund ciągłych — 2026-10-22

Użytkownik wybrał RWKV-7 2.9B, HRM-Text i Huginn. Lokalny kod rotacji 2485e0e;
bez publikacji GH. Nie jest to ranking wszystkich modeli Venoma.

## Ustawienia

- Nowa ewaluacja `game-eval-v2`, `ttt-opening-v1`, pięć epizodów w jednym bloku.
- `carry`, dwie odrębne sesje A/B tych samych wag, `opponent=model`.
- A zaczyna; brak zamiany stron w tej krótkiej serii. Wagi zamrożone.
- RWKV: native_incremental; HRM/Huginn: history_replay z zachowaną historią.
- Greedy, seed 17, 256 tokenów, 90 s/decyzję, kontekst 2048; Huginn 8 kroków.
- Legalne akcje widoczne, bez maskowania, napraw i automatycznych powtórek.
- Błąd w carry kończy blok; dalsze rundy mają skipped, bez fikcyjnej kontynuacji.

## Wyniki

| Model | Zaplanowane | Rozpoczęte | Ukończone gry | Pominięte | Pierwsza decyzja | Czas decyzji |
|---|---:|---:|---:|---:|---|---:|
| rwkv7-g1k-2.9b | 5 | 1 | 0 | 4 | invalid_format | 14.00 s |
| hrm-text-1b | 5 | 1 | 0 | 4 | invalid_format | 1.89 s |
| huginn-0125 | 5 | 1 | 0 | 4 | decision_timeout | 90.04 s |

Żaden model nie wykonał legalnego ruchu przed zakończeniem pierwszej próby.
RWKV zwrócił256 tokenów odpowiedzi niespełniającej ścisłego formatu akcji,
HRM zakończył odpowiedź po 1 tokenie bez poprawnej akcji. Huginn przekroczył90 s;
nie uzyskano końcowej odpowiedzi ani wiarygodnego pomiaru tokenów/VRAM.
To **nie jest 15 rozegranych gier** ani wynik wygranych/przegranych. Łącznie:
15 zaplanowanych, 3 rozpoczęte, 0 ukończonych gier,12 pominiętych. Nie ma materiału
potwierdzającego poprawę strategii lub naukę między pięcioma partiami.
Nie porównujemy tego z dawnym TTT z wymuszaniem legalnych współrzędnych.

## Historia i zasoby

- `rwkv7-g1k-2.9b`: `e5437893683b4a3a9d34f0d2418228f9`, 51.7s od odpowiedzi START do terminalu.
- `hrm-text-1b`: `59a2bb08287c412e8e32341bd6ab7ea1`, 15.0s od odpowiedzi START do terminalu.
- `huginn-0125`: `3011846af9954fc682871cfcf69d137a`, 158.1s od odpowiedzi START do terminalu.

Po każdej serii wspólny runtime był available, active_operations=0.
Surowe zapisy są poza Git:
`~/.local/state/venom/cooperation-lab/acceptance/carry-five-20261022/`.
W panelu: Ewaluacja gier → Historia serii → powyższy identyfikator.

## Rotacja

Włączona automatycznie przy nowym zapisie, wspólny limit 100 prób i serii.
Najstarsze zakończone dane są usuwane razem ze zdarzeniami. Aktywne próby,
cleanup_pending oraz dane innych ownerów nie są kandydatami. Usunięcie i nowy
zapis są atomowe: nieudany INSERT przywraca poprzednią próbę. Idempotentne
ponowienie istniejącego START nie powoduje rotacji. Retencja 14 dni pozostaje.

Regresja:615 Python PASS, 44 frontend PASS, Ruff/mypy/TS/lint/host contracts PASS,
nowe linie 96,04% przy progu 80%. Test SQLite 101. zapisu obejmuje obie historie,
kaskadowe usunięcie zdarzeń, aktywny cleanup, obcego ownera i rollback błędu.
Pierwszy przebieg frontendu odrzucił poprzednią etykietę licznika; poprawiono
oczekiwanie na „Zapisane próby i serie” i ponowiono frontend/pozostałe bramki.
