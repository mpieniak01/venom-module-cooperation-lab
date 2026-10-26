# Wydanie strategii gier — 2026-10-26

Zakres obejmuje warianty standard/reflection/assisted ewaluacji oraz warianty
samodzielny/refleksja/solver w zakładce „Rozmowa i serie”. Przebieg bieżącej
partii jest po lewej, historia i tabelaryczne wyniki serii po prawej. START
w ewaluacji sam wykonuje preflight; zaawansowane ustawienia są zwijane.

Aktywny profil live: `schema_version=8`, `ttt-coaching-v4`. Refleksja jest wyborem
reguły `win_now`/`block_win` z jawnego katalogu hosta. Jej użyteczność taktyczna
jest sprawdzana na własnym błędzie i 8 orientacjach planszy. Kontrola nie
potwierdza nauczenia się reguły przez model. Przy decyzji reguła jest
przypominana, a dziennik i UI odróżniają okazję, zastosowanie i zignorowanie.
Notatki są generowane wyłącznie między partiami. Stare wyniki i batch parsery
nie są retrospektywnie poprawiane. Mapped rule-choice nie wybiera za model.

HRM używa dotychczasowej reprezentacji planszy po negatywnej próbie jej
kompresji. RWKV/Huginn mają explicit-cells-v1. HRM/Huginn korzystają z jawnego
profilu angielskiego; Huginn ma wybór 8/16/32/64 kroków. Odtworzenie historycznej
próby bez num_steps przywraca 8, bez przejmowania wartości poprzedniego formularza.

## Odbiór i ograniczenia

Pełna lokalna bramka make pr-fast obejmuje Ruff/mypy/pytest/coverage,
TypeScript/ESLint/UI oraz kontrakty hosta. Aktualne liczby i przypięty SHA
należą do raportu kontroli PR, nie zastępują jakości modelu.

W małym deterministycznym pilocie 2-partiowym RWKV ukończył 2/2 partie zamiast
wcześniejszego 1/2; HRM zachował 3 pogorszenia pozycji, zmniejszył pominięte
wygrane 3→1 i zużycie wejścia 6608→4715 tokenów. Trajektorie partii są różne;
część oszczędności wynika z mniejszej liczby ruchów i braku końcowych notatek.
To nie dowód trwałego uczenia ani istotnej statystycznie przewagi. Modele
nadal ignorują część własnych reguł. Próba Huginn v4 nie osiągnęła generacji,
gdyż środowisko WSL utraciło odpowiedź podczas przygotowania; wynik interrupted
nie jest oceną jakości. Usługi zostały przywrócone, runtime zweryfikowany jako
available bez aktywnych operacji. Pełne eksporty, prywatne identyfikatory prób,
kopie SQLite i surowe odpowiedzi pozostają poza Git.

Zasady eksperymentów i wersje: [GAME_EVALUATION.md](GAME_EVALUATION.md).
