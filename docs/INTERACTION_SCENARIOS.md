# Interakcje modeli — analiza i kolejny scenariusz

Status: lokalny rozwój. Nie opublikowano nowego PR. Kandydaci poniżej to projekt
eksperymentów, nie potwierdzone zdolności modeli. A/B są odrębnymi kontekstami;
mogą korzystać z tych samych wag bez dwóch jednocześnie ładowanych modeli.

## Możliwe interakcje

| Interakcja | Co może sprawdzić operator | Stan / warunki |
|---|---|---|
| Dialog, wymiana brakujących informacji | Czy uczestnicy przekazują użyteczne fakty | Istniejące tryby; osobne dane prywatne |
| Głuchy telefon | Utrata lub dodanie szczegółów podczas przekazywania | Istnieje; B nie widzi oryginału |
| **Propozycja → recenzja → poprawa** | Czy konkretna uwaga B została uwzględniona przez A | **Zrealizowany następny scenariusz** |
| Dwie niezależne propozycje → porównanie | Różnice i zgodność odpowiedzi sprzed kontaktu | Kandydat; ujawnić propozycje dopiero po obu generacjach |
| Debata za/przeciw | Argumenty i kontrargumenty względem jednej tezy | Kandydat; człowiek ocenia dowody, brak automatycznej wygranej |
| Nauczyciel → uczeń → sprawdzenie | Czy B potrafi zastosować wyjaśnienie A do nowego pytania | Kandydat; oddzielne pytanie kontrolne, nie trening wag |
| Planista → wykonawca → kontrola | Zgodność wykonania z planem | Kandydat; początkowo wyłącznie tekst, bez narzędzi i działań robota |
| Negocjacja podziału zasobów | Czy wynik spełnia jawne ograniczenia | Kandydat; potrzebny deterministyczny walidator małego zadania |
| Pytania doprecyzowujące → odpowiedź | Czy model pyta o rzeczywiście brakujące dane | Kandydat; jawny limit pytań, operator jako źródło odpowiedzi |

Wybrano recenzję/poprawę: trzy widoczne artefakty i konkretne przekazanie
kontekstu pozwalają porównać przed/po. Dwa modele mogą wspólnie powielać błąd;
sama zgoda, krytyka lub płynność dialogu nie potwierdza poprawności.

## Zrealizowany plan

1. Osobny scenariusz `peer_review` i tryb `operator_review`; konfiguracja v3,
   scheduler `author-review-revise-v1`. Benchmark v1 pozostaje zamrożony.
2. Operator podaje zadanie; oba prywatne konteksty je otrzymują.
3. A przygotowuje propozycję. Host przekazuje ją do B.
4. B ocenia ją względem zadania, wskazuje konkretne uwagi albo brak zastrzeżeń.
   Host przekazuje recenzję do A.
5. A poprawia odpowiedź lub wyjaśnia niezgodę z recenzją. Wynik trafia do
   operatora; etykieta „Poprawa” oznacza etap, nie gwarancję lepszego wyniku.
6. Wszystkie etapy są zapisane, odtwarzane i eksportowane wraz z `phase` oraz
   rzeczywistą trasą. Deklaracja complete modelu nie pomija recenzji/poprawy.
7. Testy obejmują faktyczne treści kontekstów, porządek A/B/A, dwie rundy,
   STOP podczas recenzji i brak zmyślonej odpowiedzi końcowej po przerwaniu.

## Jak używać

W ustawieniach wybierz scenariusz **Propozycja, recenzja, poprawa** albo wariant
**Autor A → recenzent B → poprawa A**. Wybierz model i język, rozpocznij próbę,
a następnie wpisz zadanie pod czatem. Przykład: „Napisz trzyzdaniową opowieść o zgubionym kluczu.
Zachowaj imiona bohaterów: Ola i Marek”.

Limit 3 lub 6 tur to odpowiednio 1 lub 2 zadania; jeden wpis zużywa trzy
kolejne generacje. Nadal maksymalnie 2000 znaków na wpis, kontekst 2048 tokenów,
360 sekund całej sesji, jeden aktywny silnik/generacja i istniejące limity dysku.
Każde kolejne zadanie recenzenckie zaczyna się w wyczyszczonych kontekstach A/B,
ale poprzednie etapy pozostają w czacie i eksporcie. Role i harmonogram nadaje
host: ten wariant nie bada spontanicznego podziału ról. STOP nie wymaga ukończenia rundy. Przy przerwaniu nie dopisujemy fikcyjnej
recenzji ani poprawy. Szczegóły trwałości i retencji: [czat operatora](LOCAL_OPERATOR_CHAT.md).

## Dalsze kroki przed rozbudową

- Zbierać małe, jawnie opisane zadania z konkretnymi kryteriami oceny.
- Porównywać propozycję i poprawę: usunięty błąd, pominięta uwaga, nowy błąd,
  nieuzasadniona krytyka. Ocena ręczna, nie automatyczny wynik benchmarku v1.
- Dopiero po tych obserwacjach wybierać następny scenariusz. Nie uruchamiać
  automatycznie pozostałych kandydatów ani pobrań nowych modeli.

## Odbiór lokalny

- Pełne kontrole: 304 testy Python PASS, pokrycie 97,48%; 23 testy frontendowe
  PASS; Ruff/mypy/TypeScript/lint/kontrakty PASS. Dwa istniejące ostrzeżenia pytest.
- Rzeczywista przeglądarka: wybranie scenariusza ustawia właściwy wariant i krok
  trzech tur. Qwen3 4B wykonał propozycję, recenzję i poprawę, zapisano cztery
  wiadomości z trasami i fazami; completed, końcowy runtime available / 0 operacji.
- Pierwszy probe wykrył context_budget_exceeded. Usunięto powielany cel oraz
  rozbudowany protokół JSON z promptu tego wariantu; instrukcja pojedynczego
  etapu nie zostaje na stałe w historii. Budżet kontekstu nadal 2048. Dodano
  test konserwatywnego limitu bajtowego Ollamy dla krótkiego zadania i odpowiedzi
  po 512 bajtów. Nie jest to gwarancja zmieszczenia dowolnego długiego wpisu.
- Jakość: Qwen w tej próbie pisał rozwlekły angielski tekst rozumowania mimo
  języka PL i osiągnął limit 128 tokenów w każdym etapie. Przepływ jest odebrany,
  ale nie uznajemy tego za skończoną, jakościowo poprawioną odpowiedź ani sukces
  nauki współpracy. Nie poprawiano modelu dodatkowymi benchmarkami lub pinami.
- Nie pobierano wag, nie zmieniano modelu globalnego operatora i nie wydawano GH.
  Pełne prywatne receipty/logi są w katalogu raportów hosta, poza tym repo.
