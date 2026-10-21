# L6 — wydanie rozszerzonego laboratorium

Gałąź: `codex/lab-language-chat-local`, baza: scalone L1–L5 na `main`.
Repozytorium: `mpieniak01/venom-module-cooperation-lab`. Publikacja i scalenie
obejmują moduł; nie wymagają zmiany core ani kodu robota.

## Zachowanie operatora

- Scenariusz wyznacza dozwolone warianty i limity. Wszystkie scenariusze są
  widoczne, w tym kółko i krzyżyk. Wariant nie przełącza ukradkiem scenariusza.
- Język rozmowy PL/EN jest odrębny od języka panelu. Czat ma role, dokładny czas,
  odniesienia do wiadomości, przewijanie i odtwarzanie trwałego journalu.
- Operator może dołączyć do rozmowy A/B, przekazać wiadomość przez A do B
  (głuchy telefon) albo zlecić cykl propozycja A → recenzja B → poprawa A.
  Po START tych trybów widoczne jest oczekiwanie na wpis, bez pustej generacji.
- W grze sędzia sprawdza ruchy i wynik; modele nie rozstrzygają wyniku deklaracją.
  Każda tura ma aktualną planszę i ostatnią wiadomość przeciwnika, bez kumulowania
  starych plansz i powielania reguł. Wersja `board-state-v2`, limit bez zwiększenia.
- Silnik → Model korzysta z reguł lokalnego katalogu hosta i metadanych Ollamy,
  bez auto-heal, chmury, pobierania wag lub zmiany globalnego modelu. Obecnie
  dostępnych jest 10 unikalnych modeli Ollamy; `can_run` nie wymaga receipt.
  Opcjonalny techniczny test dwóch kontekstów ma odrębny `qualified`.
- Nowa próba, START/STOP, odświeżanie snapshotu/replay i archiwum zachowują
  rozdział bieżącego formularza od niezmiennej konfiguracji poprzedniego wyniku.

## Kontrakty i zasoby

Zachowane są host ABI 1.0.0, jeden aktywny silnik/generacja przez admission,
STOP z potwierdzonym cleanup, ograniczenia dysku i czasu, lokalna polityka dostępu
oraz idempotency startu i wpisów operatora. Benchmark v1, jego hash i rubryka
nie zostały zmienione. Nowe interakcje mają jawne wersje konfiguracji/harmonogramu.
Bez nowych zależności, venv, wag, sterowania robotem lub narzędzi wykonawczych LLM.

## Dowody odbioru

- Pełny lokalny make check: 318 testów Python PASS, pokrycie 97,55%;
  27 frontend PASS; Ruff/mypy (23 źródła), TypeScript, lint i kontrakt modułu PASS.
  Dwie istniejące deprecjacje narzędzi są ostrzeżeniami.
- Rzeczywisty browser desktop/mobile: scenariusze, przełączanie modeli,
  odświeżanie, START/STOP, następna próba, przewijanie i brak poziomego overflow.
- Llama1B: dwie odpowiedzi w oddzielnych kontekstach, completed i cleanup.
- Gemma2: zwykły eksperyment bez receipt ukończony (6,12 s), potem kolejny START,
  odświeżenie oczekującego czatu i STOP bez dodatkowej generacji.
- Qwen3: rzeczywiste trzy etapy recenzji odebrane technicznie; jakość odpowiedzi
  niepotwierdzona. Zapisy operatora na Gemmie4 potwierdzają także cykl A/B/A.
- Błąd rzeczywistej gry Gemmy4: dwa legalne ruchy, trzecia tura przekroczyła
  konserwatywny limit 2237/2048. Poprawka daje 897/2048 dla tego samego stanu;
  wygrana i pełny remis PL/EN przechodzą produkcyjny guard adaptera z transportem
  fixture. Nie deklarujemy pełnej nowej partii na rzeczywistym modelu.
- Surowe eksporty, prompty operatora i logi pozostają prywatne poza Git modułu.
  Dokumenty lokalnych etapów opisują ich historyczny stan; bieżący zakres to ten
  dokument. Kontrole GitHub/review potwierdzane są osobno dla końcowego SHA PR.

## Jawne ograniczenia

Nie jest to dowód samoorganizacji ani jakości któregokolwiek modelu. Niepełny
lub nielegalny ruch jest jawnym błędem, bez ukrytego poprawiania przez hosta.
Dłuższe dialogi nadal mogą wyczerpać budżet 2048. Odpowiedź JSON w bloku Markdown
jest traktowana jako tekst, nie protokół; nie zmieniamy zamrożonego parsera v1.
Scenariusze dostarczają odpowiedzi w czacie i eksport przebiegu JSON, bez osobnego
renderowania plików/obiektów. multi_runtime, vLLM i ONNX nie mają adaptera generacji
Lab; są widoczne z powodem blokady. Nowe architektury wymagają osobnego odbioru.
Most katalogu używa prywatnych helperów hosta przypiętego w kompatybilności/CI;
zmiana ich sygnatur wymaga ponownego sprawdzenia, bez mutowania konfiguracji.

## Wdrożenie i wycofanie

Po scaleniu pobrać main modułu, przygotować mirror przez oficjalny skrypt hosta
`web-next/scripts/prepare-optional-module-node-paths.mjs`. API przeładować jedynie
przy braku aktywnych prób, nie przerywać sesji operatora. Nie uruchamiać modeli
na startupie. Rollback: odwrócić commit scalenia po zatrzymaniu własnych prób;
nie usuwać namespace bazy, receipt ani historycznych journalów. Nie ma migracji
schematu bazy. Nowe konfiguracje/historyczne wersje pozostają w zapisanych JSON.


## Poprawki po recenzji PR #16

Naprawiono dwa P2: odzyskiwanie START po utracie odpowiedzi i zmianie katalogu
oraz trwałość idempotency wpisu operatora po usunięciu jobu/restarcie. Nowe
regresje obejmują ponowienie zwykłego START i diagnostyki przy niedostępnym modelu,
konflikt innego requestu oraz ponowienie wiadomości po ponownym otwarciu SQLite.
Potwierdzono brak drugiego runu lub drugiego wpisu. Kontrakt powyżej bez migracji.
