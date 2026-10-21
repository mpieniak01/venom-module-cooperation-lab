# Formularz laboratorium — scenariusz określa przebieg

Lokalna poprawka po zgłoszeniach niewidocznej gry oraz stanu „Trwa” bez generacji.
API zawierało grę, ale filtr UI ukrywał ją przy wariancie operatora/recenzji.
Wszystkie scenariusze pozostają teraz widoczne. Wariant nie zmienia scenariusza.

## Kolejność ustawień

1. **Zadanie i przebieg**: scenariusz, potem wyłącznie dozwolone warianty.
   Gdy scenariusz ma jeden przebieg, lista wariantu jest zablokowana i wyjaśniona.
2. **Model i język**: jeden model, osobne konteksty A/B, język komunikacji.
3. **Limity próby**: tury, tokeny na turę, seed. Dla operatora pokazujemy także
   liczbę pełnych zadań, dla gry liczbę ruchów.

| Scenariusz | Dostępne warianty | Tury | Co po START |
|---|---|---|---|
| Rozdzielone informacje, wspólne obliczenie, korekta propozycji | Samodzielnie, samokorekta, bez komunikacji, dialog, dialog z zachętą | 1–8 | Modele zaczynają automatycznie |
| Rozmowa operatora | Rozmowa z operatorem, głuchy telefon | 2/4/6/8 | Operator wpisuje wiadomość i wysyła |
| Kółko i krzyżyk | Stały: gra naprzemienna A/B | 1–9 | Modele zaczynają grę automatycznie |
| Propozycja, recenzja, poprawa | Stały: A → B → A | 3/6 | Operator wpisuje zadanie i wysyła |

Zmiana scenariusza ustawia jego domyślny limit: 8 dla zwykłych zadań i rozmowy,
9 dla gry, 6 dla recenzji. Zgodny poprzedni wariant jest zachowany; niezgodny
zastępuje domyślny. Model, język, tokeny i seed pozostają bez zmian.

Tryb operatora, który nie otrzymał wiadomości, pokazuje **Czeka na Twój wpis**,
a nie ogólne „Trwa”. Obliczenia ruszają po wysłaniu. W Ollamie samo przygotowanie
sprawdza metadane; pusty `/api/ps` przed wpisem nie oznacza awarii ładowania.
Ten komunikat wynika z utrwalonego zdarzenia operator/waiting, a po zakończeniu
próby pierwszeństwo ma jej rzeczywisty stan końcowy.

Ustawienia aktywnej próby pozostają zablokowane: aby zmienić scenariusz, zatrzymaj
próbę albo zaczekaj na jej zakończenie. Poprawka nie restartuje API i nie wysyła
wiadomości w imieniu użytkownika. Nie uruchamia też generacji przy wyborze pola.

Źródło reguł formularza: `web-next/lib/experiment-settings.ts` (wybór scenariusza,
dozwolone warianty, domyślne tury i ich krok). Odtwarzanie zapisanej próby nadal
korzysta z jej niezmiennej konfiguracji, a zmiana modelu/języka nie zmienia zadania.
Zablokowany pojedynczy wariant oznacza stały przebieg, nie awarię formularza.

Odbiór: 304 testy Python i 24 frontendowe PASS, Ruff/mypy/TS/lint/kontrakty PASS.
Chrome 1366×900 i 390×844: wszystkie scenariusze widoczne, poprawne przełączenia
gra/recenzja/rozmowa/zadanie oraz brak poziomego przepełnienia na telefonie.
Test formularza korzystał z rzeczywistego katalogu API; wyłącznie w karcie testowej
GET historii zwracał pustą listę, aby nie zmieniać aktywnej próby użytkownika.
Po teście przywrócono rzeczywistą historię. Bez POST, nowych generacji, restartu
API i publikacji GH. Zrzut i logi są w lokalnym katalogu artefaktów Codex/hosta.
