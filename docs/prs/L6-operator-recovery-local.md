# L6 — poprawka odbiorowa: formularz i bezpośrednie użycie modeli

Status: wdrożone lokalnie, ta sama gałąź `codex/lab-language-chat-local`, bez GH.

## Przyczyny

- Zainstalowane modele Ollamy niepotrzebnie wymagały dodatkowego receipt przed
  zwykłym START. Ostatnia diagnostyka Gemmy4 faktycznie wygenerowała odpowiedź
  (28,78 s), lecz została anulowana przed drugą odpowiedzią; receipt słusznie nie
  powstał, ale blokowanie zwykłego eksperymentu było zbędnym wymaganiem UI.
- Odświeżenie pobierało katalog/listę, ale nie ponawiało snapshotu i replay
  wybranej próby. Nie miało czytelnego stanu odświeżania.
- Nowa próba zachowywała niedostępny model i sprawiała wrażenie braku działania.
- Formularz zmieniał podpis i planszę historycznego wyniku. Błąd utrwalony w journalu
  nie był prezentowany po odtworzeniu historii.

## Zmiana

- Osobne `can_run` (adapter i lokalny model dostępne) i `qualified` (opcjonalny
  test ukończony). Wszystkie 10 aktualnych modeli Ollamy można uruchomić przez START.
  Nadal sprawdzamy digest, template i wersję silnika przed generacją; admission,
  limity, STOP i zakaz pobrań pozostają. Brak adaptera nadal uniemożliwia wykonanie.
- Opcjonalny test ma jawny opis. Nie uruchamia się przez sam wybór modelu.
- Nowa próba czyści wybraną historię i błędy, otwiera formularz oraz wybiera model
  dostępny do wykonania, jeżeli poprzedni wybór nie miał adaptera. Odświeżenie nie
  przywraca samoczynnie starego archiwum. Aktywna próba nadal ma pierwszeństwo.
- Odśwież pobiera bieżący snapshot, replay, katalog i listę; pokazuje postęp,
  pozostawia STOP dostępny i zachowuje ochronę przed spóźnionymi odpowiedziami.
- Wynik i czat są powiązane z niezmienną konfiguracją rzeczywistej próby, a nie
  scenariuszem dopiero wybieranym do następnego uruchomienia.

## Rzeczywisty odbiór

1. Archiwalny błąd → niedostępny adapter → Odśwież → Nowa próba → wybór Ollamy
   i Gemmy2 2B bez receipt → START zwykłego scenariusza: PASS.
2. `21e7cfe434d7422bb1c6c0a1f611728b`: completed, 143 tokeny wejścia / 5 wyjścia,
   6,12 s generation / 6,09 s TTFT. Bez wcześniejszej kwalifikacji, bez pobierania.
3. Po completed kolejny START rozmowy operatora, odświeżenie podczas oczekiwania,
   STOP i odzyskany START: PASS. Próba `0c2112d0c6454aac8a4bad3c8b7fbd0a` anulowana,
   bez wysłanego promptu i bez dodatkowej generacji.
4. Kontrola aktualnego katalogu: 10/10 modeli Ollamy ma `can_run=true` niezależnie
   od receipt. To kontrola katalogu/adaptera, nie 10 osobnych prób inferencji.
   Rzeczywistą inferencję potwierdzają bieżąca Gemma2 i wcześniejsze Qwen3, Llama1B
   oraz odpowiedź Gemmy4; nie deklarujemy jakości ani zgodności każdego scenariusza.
5. Kontrole automatyczne obejmują dwa starty z innymi kluczami idempotency,
   direct START bez receipt, Nową próbę po błędzie, odświeżanie/replay i STOP.

Raw eksporty i logi są prywatne w katalogu raportów hosta, poza repo modułu.

Końcowy `make check`: 315 Python PASS, coverage 97,55%; 27 frontend PASS.
Ruff/mypy (23 źródła), TypeScript, lint i kontrakt modułu PASS. Dwie istniejące
deprecjacje pozostają ostrzeżeniami. Lokalny runtime available/0, Ollama ps[]
po testach; brak publikacji na GitHub.
