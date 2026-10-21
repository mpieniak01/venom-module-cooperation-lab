# L6 — kółko i krzyżyk: kontekst po pierwszej parze ruchów

Lokalna poprawka, bez GH, na `codex/lab-language-chat-local`.

## Zapis błędu

Partia `e3ab51c8c6d4450982e1e65796b415a5`, Gemma4, PL, 9 tur i 128 tokenów
na odpowiedź. A wykonał A2 (11,72 s), B wykonał A1 (4,53 s). Oba ruchy przyjęte
przez sędziego, bez wygranej/remisu. Tura 3 została zatrzymana przed wywołaniem
modelu: `context_budget_exceeded`. Cleanup potwierdzony, nie utrata transmisji
ani decyzja modeli o zakończeniu gry.

Adapter używa jawnego konserwatywnego ograniczenia: 256 + bajty UTF-8 i narzut
ról + rezerwa odpowiedzi. Odtworzona trzecia tura: 2237 przy limicie 2048.
Powielano reguły/cel w systemie i wiadomości użytkownika oraz dopisywano pełne
plansze i wiadomości z kolejnych tur. Testowy adapter CPU nie egzekwował dotąd
tego samego limitu co rzeczywista Ollama; dlatego pełna testowa partia przechodziła.

## Poprawka

- Osobna krótka instrukcja systemowa gry, bez sprzecznego ogólnego protokołu JSON.
- Bez duplikacji całego celu jako kolejnej wiadomości.
- Każda tura zawiera instrukcję, ostatnią faktycznie dostarczoną wiadomość
  przeciwnika (z identyfikatorem) i jedną aktualną planszę. Starsze stany pozostają
  w journalu. Wszystkie legalne ruchy są uwzględnione w autorytatywnej planszy.
- Ten sam stan trzeciej tury po poprawce: 897, przy niezmienionym limicie 2048
  i rezerwie 128. Nie zwiększamy budżetów, nie usuwamy błędów ani nie podmieniamy
  błędnych ruchów ruchem wybranym przez hosta.
- Nowe próby mają scheduler `board-state-v2`, schema 3 i sufiks scenariusza
  `-board-context-2`. Zapisy starych prób i zamrożony benchmark v1 bez zmian.
- Adapter RWKV przy nieprzyrostowej historii resetuje własny stan uczestnika;
  pozostałe scenariusze zachowują dotychczasową politykę kontekstu.

## Weryfikacja

Pełne partie wygranej i dziewięciu ruchów/remisu w PL i EN są odtwarzane przez
rzeczywisty `OllamaAdapter.generate` z kontrolowanym transportem CPU. Każdy prompt
przechodzi produkcyjny guard, zachowuje jeden aktualny stan planszy i identyfikator
ostatniej wiadomości. Bez inferencji i bez twierdzenia o jakości strategii modelu.
36 testów celowanych PASS. Pełny make check: 315 Python PASS, 27 frontend PASS,
Ruff/mypy/TS/lint/kontrakt modułu PASS. Nie wymuszamy restartu w trakcie próby
operatora ani nie uruchamiamy hurtowych testów modeli.
