# RWKV — protokół rozmowy i gry v2

Źródła autorów (odczyt 2026-10-22):
- https://huggingface.co/BlinkDL/rwkv7-g1
- https://github.com/BlinkDL/RWKV-LM/blob/main/RWKV-v7/RWKV7-G1x-templates.txt
- https://github.com/BlinkDL/ChatRWKV/blob/main/rwkv_pip_package/src/rwkv/utils.py

## Co pokazały dostępne próby

Przegląd 100 ostatnich wpisów (80–84 dostępne na początku prac): 33 próby
RWKV 0,4B, w tym 4 gry; na 2,9B początkowo jedna gra i kwalifikacja, podczas
analizy doszły kolejne próby. W dwóch zakończonych błędem grach 2,9B pierwsze
ruchy A1/B2 przyjęto, a trzeci ruch C3 lub C1 odrzucono jako invalid_game_move,
ponieważ był opakowany w `Message <id> from A: ...`. Oba pola były legalne.
Próba anulowana bez ruchu nie jest próbką jakości gry. Mały 0,4B również
odtwarzał opisy planszy, z których nie można uczciwie wybrać pojedynczego ruchu.
Rozmowa o sumie powtarzała błędne 34 i techniczne prefiksy: transport completed
nie oznacza poprawnej współpracy. Nie zmieniamy historycznych wyników ani rubryki v1.

## Adapter i stan

Wagi pozostają niezmienne. Każdy uczestnik ma prywatną historię i stan RNN.
Dopisanie historii używa wyłącznie nowego sufiksu. Zmiana dawnych wiadomości
jawnie resetuje i odtwarza stan; anulowana częściowa generacja go nie zatwierdza.
Separator kończący odpowiedź jest już przetworzony przez model: kolejna tura
nie dopisuje go ponownie. EOS/limit długości wymagają dodania separatora.
Token 0 to koniec dokumentu. Prompt pozostaje System/User/Assistant, bez końcowej
spacji, z oczyszczonymi separatorami wewnątrz wiadomości.

Runtime identity zawiera `rwkv-chat-v2`: zmiana wymaga nowej jawnej kwalifikacji.
Nie podmieniamy receiptów ani historii. Surowy tekst z separatorami jest zachowany
w `raw_content`; tekst użytkowy w `content`, przyczyna zakończenia w usage.

## Gra

Nowe próby: board-context-5 / board-state-v4. Dotychczasowe próbki nie są
przeliczane. Zwykłe modele zachowują kompaktowy kontekst planszy. RWKV ma
rosnącą historię własnych tur i krótkie autorytatywne obserwacje planszy,
zamiast resetu w każdej turze. Własna poprzednia odpowiedź pozostaje w stanie,
a nowa obserwacja zawiera aktualną planszę i listę wolnych pól. Komunikat o ruchu
przeciwnika nie zawiera technicznych identyfikatorów. Identyfikatory i routing
pozostają w dzienniku. Limit 2048 tokenów nadal obowiązuje.

Profil `structured` RWKV: temperature=0, top_p=0, kary presence/frequency=0.
Efektywne parametry są zapisane w usage; ustawienia czatu pozostają oddzielne.
To kontrola formatu, nie algorytm wybierający ruch za model.

Parser akceptuje pełną odpowiedź jako współrzędną, pojedynczy blok/backtick,
jednoznaczną etykietę Move/Ruch albo dokładny znany prefiks Message/Wiadomość.
Nie szuka współrzędnych wewnątrz dowolnej prozy, planszy lub rozumowania.
Kilka propozycji i niepełny wynik nadal są błędem formatu. Legalność i zajętość
pola sprawdza osobny sędzia. `game_move` i `move_format` ujawniają interpretację,
bez zastąpienia oryginalnego content. Dawne błędy pozostają widoczne.

Nie włączamy automatycznie trybu think, nie zgadujemy odpowiedzi z rozumowania,
nie wybieramy najlepszego pola za model i nie ponawiamy ruchu do skutku.

Po pierwszej próbie poprawionego protokołu (da968e3d…): A1/B2/A3 było poprawne,
a następne B2 było już realnym wyborem zajętego pola. Dlatego profil gry RWKV
jawnie ogranicza tokeny wyjścia do zakodowanych współrzędnych aktualnie wolnych
pól. Host wyznacza legalny zbiór, model wybiera tokeny według własnych logits;
nie ma minimax ani zastępczego wyboru ruchu. Usage zawiera allowed_outputs oraz
decoding_constraint=allowed_outputs, stop_reason=allowed_output. To gra z
ograniczeniem legalności, a nie dowód spontanicznego przestrzegania reguł.
Zwykły czat nie stosuje tego ograniczenia. Sędzia nadal niezależnie waliduje ruch.

## Końcowy odbiór lokalny 2026-10-22

- make check: 359 Python PASS, coverage 97,58%; frontend/TS/lint i kontrakt hosta PASS.
- Odtworzenie obu wcześniejszych błędów: 3 legalne ruchy, ostatnie C3/C1; historia bez zmian.
- Ponowna kwalifikacja obu RWKV po zmianie runtime identity: completed, quiescent=true.
- Jedna gra 2,9B z legal-choice: `76e21bfb4c8241e8aa7b11e6247699fc`, completed.
- Ruchów: 9; zwycięzca: A; remis: False.
- Usage potwierdza replay przy pierwszym wejściu każdego uczestnika i append w kontynuacji, allowed_outputs i zerowe kary.
- Po cleanup admission available, active_operations=0. Nie jest to benchmark siły gry ani samoorganizacji.
