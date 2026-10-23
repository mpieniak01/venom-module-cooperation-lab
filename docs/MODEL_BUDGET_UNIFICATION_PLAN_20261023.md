# Wspólne profile budżetów modeli — analiza 2026-10-23

Status: uproszczona poprawka wdrożona lokalnie 2026-10-23; operator wznowił zgodę na publikację,
recenzję i scalenie. Roboczy 5c92b37 został uzupełniony o limity per model
i ograniczanie dopiero po START.

## Potwierdzona przyczyna zgłoszenia

Pierwsza zwykła próba kończyła się poprawnie. Następny POST `/runs` z
`max_new_tokens=1024` był odrzucany przez `RunRequest` (limit 256), przed
utworzeniem próby lub uruchomieniem silnika. Panel nie rozpoznawał listy błędów
walidacji FastAPI i pokazywał ogólne „Nie udało się wykonać operacji”.
Nie dowodzi to braku możliwości uruchomienia RWKV, HRM lub Huginn.

Nowa ewaluacja ma odrębny kontrakt game-eval-v2 i profile modelu, natomiast
Rozmowa i serie nadal korzysta z osobnego formularza i historycznych limitów v1.
To rozjazd dwóch ścieżek tego samego laboratorium.

## Dowody zamiast jednego maksymalnego ustawienia

Źródła: [poprzednia analiza](MODEL_BUDGET_PROFILES_20261022.md),
[rzeczywiste powtórzenia](LIMIT_RETRIES_20261022.md), odczyt bieżącego katalogu
oraz zapisanych profili bez uruchamiania modeli.

| Model | Kontekst checkpointu / obecny limit adaptera | Obecny zapis operatora | Co faktycznie sprawdzono |
|---|---|---|---|
| RWKV-7 G1k 2.9B | ctx25600 / 8192 | 512 output, 8192 context, 180 s | Próby 512 i 1024 wykonano; w Memory/Sokobanie większy budżet nie zapewnił końcowej akcji. |
| HRM-Text 1B | 4096 / 4096 | Brak; fallback 64/2048/30 s | 64 i 256 nie zapewniły poprawnego formatu gry. Nie kwalifikowano lokalnie maksymalnego output 1024. |
| Huginn-0125 | 4096 / 4096 | Brak; fallback 64/2048/30 s | 32/90 s zakończyło generacje technicznie; 256/4096/300 s dało decyzję po 207,60 s, bez końcowej akcji. |
| Gemma4 / Ollama | metadata 131072 / 16384 | Brak; fallback 64/8192/30 s | Nim działał przy 128; Memory 128/16384/90 s wykonało 25 legalnych ruchów przed context_limit. |
| RWKV 0.4B, Qwen3 4B | odpowiednio lokalny limit 8192, 2048 | Brak; fallback 64/2048/30 s | Nie zastępować profilem większego checkpointu lub innej architektury. |

Wartości kontekstu checkpointu pochodzą z wcześniej odczytanych lokalnych
config.json/nazw przypiętych wag. Limity adaptera to zakres implementacji,
a nie pomiar wydajności przy maksimum. Błąd formatu jest oddzielny od błędu
zasobów. Ustawienie output=1024 oznacza górną granicę generacji, nie polecenie
wygenerowania dokładnie 1024 tokenów.

## Realizacja uproszczona według decyzji operatora

- Podczas wpisywania oraz preflight formularz zachowuje podaną wartość.
- Dopiero START ogranicza za duży output do lokalnego limitu wybranego modelu,
  aktualizuje pole i rozpoczyna grę w tym samym działaniu. Bez drugiego kliknięcia.
- API robi tę samą normalizację przed stworzeniem konfiguracji i ładowaniem wag.
  Zapis zachowuje oryginalne żądanie i zastosowany budżet; retry ma ten sam klucz.
- Wartości mniejsze od limitu pozostają bez zmian. Zero, ułamki, tekst i liczby
  poza zakresem bezpiecznego żądania nadal są błędami formularza.
- Jedno źródło lokalnych limitów: model_limits.py. RWKV/Ollama: 1024, kosztowne
  HRM-Text/Huginn: 256 (przetestowany zakres generacji), nierozpoznany adapter:256.
  To lokalna polityka wykonania, nie twierdzenie o fizycznym maksimum checkpointu,
  pojemności VRAM ani gwarancja dobrego ruchu. Nie podnosimy domyślnych wartości.
- Limit kontekstu nadal sprawdza adapter. Nie skracamy ukradkiem historii,
  nie ponawiamy błędnych ruchów i nie zmieniamy iteracji Huginn ani czasu decyzji.
- Istniejące profile operatora i wyniki nie są nadpisywane. Zapis profilu pozostaje
  jawny; parametr ponad zmniejszony limit HF wymaga zapisania zgodnego profilu.
- Pełna przebudowa kontekstu/czasu/profili dla zwykłych rozmów pozostaje dalszym
  zakresem, poza tą korektą startu. Nie dodajemy trybu eksperymentalnej zgody.

## Odbiór

Regresje CPU i przeglądarkowe sprawdzają wpisanie większej wartości bez zmiany,
START, aktualizację pola, użyty budżet, mniejsze wartości oraz idempotencję.
Jedna minimalna rzeczywista gra po wdrożeniu; bez serii kosztownych prób maksimum.
Scalenie po zielonych kontrolach i recenzji jest ponownie autoryzowane. Niezależny PR core dotyczy owner_pid.

### Wynik odbioru lokalnego 2026-10-23

- `make pr-fast HOST=/home/ubuntu/venom`: PASS, 697 Python, 50 frontend,
  coverage Python 96,93%; Ruff/mypy/TS/lint i kontrakt hosta PASS.
- Pokrycie zmienionych linii po dodaniu nowych plików sprawdzone osobno
  przez `make check-new-code-coverage-diagnostics` (próg 80%, PASS).
- Chrome Playwright: RWKV-7 0.4B, zwykła gra naprzemienna, jedna partia.
  Wpisane 4096 pozostaje w polu przed START; po START 1024. Nie było dodatkowego
  potwierdzenia ani drugiego kliknięcia. API zapisało requested=4096/applied=1024.
- Próba `2cf7c7293a2d4eed826ea213fa806b8a`: completed, sześć legalnych ruchów,
  wygrał B/O; quiescent=true. To sprawdzenie startu/formatu, nie dowód strategii;
  zwykła gra używa dotychczasowego jawnego ograniczenia do legalnych pól.
- API po zakończeniu available/0; przycisk kolejnego startu aktywny. Zapisanych
  danych i profili nie usuwano ani nie nadpisywano. Publikacja i scalenie są autoryzowane po odebraniu poprawki.
- Zrzut lokalny: Playwright `.playwright-cli/page-2026-10-23T07-26-51-651Z.png`.
