# Powtórzenia gier ograniczonych budżetami — 2026-10-22

Lokalnie, gałąź codex/rwkv7-g1k-2.9b, kod 361bf40. Bez publikacji GH.
Wykonano siedem nowych prób. Powtarzano przypadki zatrzymane przez ograniczenia,
a nie zwykłe porażki strategiczne lub powtórzenie już dopasowanych kart HRM.

## Warunki

Ten sam manifest, przypadki i seed 17, greedy, history_replay, jawne legalne
akcje. Jedna odpowiedź na decyzję, bez ukrytych ponowień, podstawiania modelu,
naprawiania wybranego ruchu lub wymuszania legalnego wyjścia.
RWKV i Gemma: fresh/mapped; Huginn: carry/strict_json, przeciwnik model.
Huginn powtórzył wyłącznie pierwszy epizod dawnej serii pięciu partii, nie całą serię.
Generacje wykonywano kolejno przez wspólny admission.

## Wyniki

| Model / przypadek | Nowy budżet: odpowiedź / kontekst / czas decyzji | Wynik |
|---|---|---|
| RWKV Nim [3,4,5], optymalny przeciwnik | 512 / 8192 / 180 s | 0 legalnych ruchów; 251 tokenów, pełne JSON kopiujące obserwację i listę akcji zamiast wyboru; illegal_action |
| RWKV Memory | 512 / 8192 / 180 s | 1 legalny ruch, 0 par; druga odpowiedź urwana na 512 tokenach, brak końcowej akcji; invalid_format |
| RWKV Sokoban, jedna skrzynia | 512 / 8192 / 180 s | 0 ruchów; urwane rozumowanie na 512 tokenach; invalid_format |
| Huginn TTT v2, otwarcie | 256 / 4096 / 300 s | Decyzja 207,60 s zamiast wcześniejszego timeoutu 90 s; 256 tokenów kopiujących obserwację, brak akcji; invalid_format |
| RWKV Memory | 1024 / 8192 / 180 s | Nadal 1 legalny ruch, 0 par; druga odpowiedź urwana na 1024 tokenach; invalid_format |
| RWKV Sokoban | 1024 / 8192 / 180 s | Nadal 0 ruchów; odpowiedź urwana na 1024 tokenach; invalid_format |
| Gemma4 Memory | 128 / 16384 / 90 s | 25 legalnych ruchów, 1 para, 21 pominiętych znanych par; następna decyzja context_limit |

Pierwotne RWKV miało 128/2048/90. Gemma przy poprzednim 128/8192/90 wykonała
12 legalnych ruchów, znalazła 1 parę i pominęła 8 znanych par przed context_limit.
Większy budżet Gemmy wydłużył próbę, bez poprawy liczby znalezionych par.
Czasy całych prób (z przygotowaniem): RWKV Nim 51,14 s; Memory512 64,21 s;
Sokoban512 34,25 s; Huginn 278,32 s; Memory1024 105,08 s;
Sokoban1024 51,23 s; Gemma 130,57 s. Nie są to same czasy inferencji.

Status serii completed oznacza zakończenie pracy runnera. Status epizodu
context_limit/invalid_format/illegal_action nie jest zaliczeniem gry.
Pary i pominięcia odtworzono niezależnie z zapisanych legalnych akcji przez
replay_episode, także gdy terminalny snapshot ma result=null.

## Interpretacja i ograniczenia

- Huginn: zwiększenie czasu pozwoliło zakończyć generację, ale nie uzyskać akcji.
  Pozostaje ograniczenie odpowiedzi 256 i kopiowanie promptu. Nie wykonano
  kolejnych kosztownych prób ani nie zmieniano liczby iteracji.
- RWKV: zamknięty think oraz JSON pierwszego ruchu Memory są poprawnie mapowane.
  Kolejna odpowiedź może pozostawać w niedokończonym rozumowaniu nawet przy 1024.
  Nie wyciągamy ruchu z niedokończonego toku rozumowania ani listy możliwości.
- Gemma: lokalne metadata Ollama wskazują context_length=131072. Laboratorium
  udostępnia kontrolowane maksimum 16384, nie pełne natywne maksimum.
  Konserwatywny licznik bajtowy adaptera oraz osobna granica historii
  16 KiB/512 wiadomości nadal obowiązują. context_limit nie dowodzi wyczerpania
  fizycznego okna tokenów modelu. Nie usuwano ani nie skracano historii w trakcie.
- Więcej legalnych ruchów nie dowodzi uczenia, pamięci skutecznej ani strategii.
  Wagi pozostały zamrożone. Nie zwiększano dalej budżetów dla uzyskania sukcesu.

## Zapis i weryfikacja

Identyfikatory prób kolejno jak w tabeli:
0da37657403f4cbbb376c136f5f0e5bc,
734f163f60614f8fa7e5de1b3641e963,
2fa08fa669194a38ba6ee03745704793,
6394be858d86484d8941a1a045850b93,
de929cbbed824e6ea86b7217f40f41ef,
8d50a58bf5f04c0a9101cf96c3944ef8,
e511b5f54bb7412c9de4a2dd59c1d796.

Prywatne snapshoty, konfiguracje, surowe odpowiedzi oraz analiza replay:
~/.local/state/venom/cooperation-lab/acceptance/limit-retries-20261022/
i limit-retries-final-20261022/. Próby widoczne w historii ewaluacji panelu.
Surowe odpowiedzi pozostają poza Git. Zachowano wcześniejsze próby operatora;
nie wyłączano istniejącej rotacji terminalnych rekordów.

Dla zmiany limitu Gemmy make pr-fast HOST=/home/ubuntu/venom PASS:
663 Python, 45 frontend, coverage 96,93%, zmienione linie 96,11% / próg 80%,
Ruff/mypy/TypeScript oraz kontrakty hosta PASS. Oficjalny mirror zsynchronizowany.
Końcowy odczyt API i /cooperation-lab HTTP200; runtime available, active_operations=0.
Bez pobierania modeli, nowych venv, ARM, ruchu ani zmiany kamery.
