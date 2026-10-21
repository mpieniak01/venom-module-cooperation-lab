# Pulpit operatora L4

Ekran `/cooperation-lab` jest opcjonalnym modułem. Otwarcie ekranu pobiera metadane i historię, bez uruchomienia modelu. START i STOP pozostają w górnym pasku; ustawienia można zwinąć. Sesje A/B dzielą niezmienne wagi, ale mają prywatne konteksty. Propozycje organizacji pochodzą z modeli; deklaracja complete nie jest oceną jakości.

## Użycie

1. Wybierz zakwalifikowany model, scenariusz i warunek eksperymentu. Ustaw limit tur, tokenów i seed.
2. START zapisuje idempotentne żądanie, po czym pokazuje niezależny stan obliczeń i połączenia. Retry nie powiela generacji.
3. STOP anuluje bieżącą próbę. Stan cancelling trwa do potwierdzonego zakończenia pracy. STOP podczas oczekiwania na potwierdzenie START zapisuje żądanie anulowania nowej próby; nie anuluje poprzedniego archiwum.
4. Historia jest zablokowana podczas aktywnej próby, aby nie ukryć jej STOP. Po zakończeniu można wybrać wcześniejszy zapis, wyeksportować JSON albo usunąć konkretną próbę po potwierdzeniu.

## Połączenie i metryki

Jeden EventSource, trwały seq, ograniczony replay i deduplikacja. Reconnect korzysta z Last-Event-ID/query after, bez jednoczesnego pollingu. Po utracie kanału przycisk Połącz ponownie odtwarza journal. Odświeżenie metadanych nie udaje naprawy SSE. Zamknięcie przeglądarki nie oznacza STOP silnika. Nieznany usage jest pokazany jako nieznany, naliczony budżet osobno.

PL/EN/DE mają te same klucze; model/scenario ID pozostają identyfikatorami technicznymi. UI renderuje zwykły tekst wiadomości, bez HTML lub wykonywania poleceń.

## Weryfikacja

`make check-web HOST=/home/ubuntu/venom` działa również w odrębnym worktree: pomocnik generuje ignorowaną konfigurację wskazującą istniejący host/node_modules, nie instaluje pakietów ani nie zmienia konfiguracji hosta. TypeScript i ESLint PASS; 7 testów React/Node PASS, pokrycie frontendowe 95,7%. Fixture metadanych pochodzi z rzeczywistej serializacji L3 i ma test wykrywający zmianę kontraktu w Pythonie.

Odbiór rzeczywistego hosta, streaming przez proxy i responsive pozostają osobnym krokiem przed wydaniem, wraz z CI/Sonar. Fixture i JSDOM nie są dowodem współpracy modeli.
