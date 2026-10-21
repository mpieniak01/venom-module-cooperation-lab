# Małe eksperymenty współpracy — L5

Status: kod planowania/oceny i testy deterministyczne są lokalnie zaimplementowane.
Realny odbiór wspólnego C0 + L2 + L3 + L4 pozostaje **pending**, dopóki koordynator
nie zapisze rzeczywistych receiptów i dokładnych SHA. Test fixture nie jest próbą
modelu, a poprawny transport nie dowodzi nauki lub przewagi jakościowej.

## Zamrożony zestaw

Metadane [experiments-v1.json](experiments-v1.json) są jawnie publicznymi danymi
syntetycznymi. Rubryka jest osobną implementacją w `experiments.py`; nie odczytuje
pola `expected` runnera ani konsensusu uczestników. Zmiana faktów/celu wymaga nowej
wersji dataset/rubric, zamiast poprawiania reguły po obejrzeniu odpowiedzi.

| Scenariusz v1 | Prywatne A | Prywatne B | Niezależny wynik |
| --- | --- | --- | --- |
| split_facts | pierwsza litera R | druga litera K | RK |
| organization | liczba 17 | liczba 25 | 42 |
| correction | liczba 17 | liczba 25; publiczna propozycja to 41 | 42 |

| Tryb | Informacja | Uczestnicy/komunikacja |
| --- | --- | --- |
| single | wszystkie fakty w jednym kontekście | jedna tura A, uprzywilejowany baseline |
| self_correction | wszystkie fakty | A koryguje własną odpowiedź, uprzywilejowany baseline |
| no_contact | rozdzielona | A/B naprzemiennie, brak przekazania wiadomości |
| dialog | rozdzielona | A/B, bez przydzielania ról przez hosta |
| dialog_encouraged | rozdzielona | A/B, zachęta do zaproponowania organizacji |

To nie jest ślepy ranking: single/self_correction dostają więcej informacji niż
no_contact/dialog. Jednakowe limity nie oznaczają równego faktycznego kosztu.
Porównujemy koszty actual i charged, liczbę tur, czas i przepływ informacji.
Scenariusz organization pozwala obserwować deklaracje planu; samo 17+25 nie jest
przekonującym zadaniem dowodzącym wykonania podziału pracy. Wykonanie zobowiązań
pozostaje `unscorable`, dopóki nie powstanie niezależnie obserwowalne zadanie.

## Budżet i uruchamianie

Domyślny plan ma tylko dwa krótkie przypadki: po jednym dialog_encouraged /
split_facts dla RWKV i istniejącego Qwen. Bez `--execute` nie ma nawet HTTP.
Pełna opcjonalna macierz: 2 modele × 3 sceny × 5 trybów = 30 prób, jawne
`--matrix --execute --max-runs 30`. Tylko 2 lub 4 tury, do 32 tokenów wyjścia,
seed 17, temperature/top_p 0. Bez treningu, pobierania lub wyboru globalnego LLM.
Host wymusza dodatkowo limity kontekstu/tokenów/kroków i pojedynczy lease C0.
Szczegóły uruchomienia i wycofania: [RUNBOOK](RUNBOOK.md).

CLI przyjmuje tylko HTTP istniejącego hosta `127.0.0.1:8800`, wyłącza proxy i
redirecty; nie przyjmuje adresu endpointu. Mutacje nadal przechodzą politykę hosta.
Preflight wymaga ready, qualified dla wybranych modeli oraz wersji scenariusza.
Start zapisuje własny UUID idempotency przed HTTP; utracona odpowiedź jest
ponawiana z identycznym body/key, najwyżej raz. Nie uruchamia drugiej generacji
pod nowym kluczem. Timeout anuluje wyłącznie znany własny run. Kolejny przypadek
nie rusza bez terminalnego exportu i potwierdzenia `quiescent=true`.

## Ocena i raport

Wynik wymaga zgodnego config_hash, celu i rozdziału informacji, zakończenia runu
oraz zgodnego końcowego zdarzenia/quiescence. Niepełny journal, konflikt seq,
fałszywy adresat lub niespójne reply są odrzucane. Deduplikacja identycznego
zdarzenia jest dozwolona. Ocena nie wybiera najlepszej odpowiedzi z historii.
Ostatnia odpowiedź każdego uczestnika i ostatnia odpowiedź runu są jawne.

Akceptujemy krótki jednoznaczny wynik, proste równanie, dokładny JSON `answer`
lub jeden końcowy marker Final. Niejednoznaczna narracja/format to `unscorable`,
nie wymyślony sukces i nie automatycznie błędna odpowiedź. Błędny jawny wynik jest
`incorrect`. Unknown actual tokens/czas pozostają `null`, nie są zastępowane zerem;
charged to osobna konserwatywna miara. W raporcie: load/device/precision/runtime,
TTFT, generation i wall time, input/output actual/charged, konfiguracja/budżet.

`peer_deliveries` łączy seq źródła, późniejszą turę adresata i reply. Automatyczne
`reply_source=host_context` oznacza zachowaną relację kontekstu, nie semantyczną
zgodę modelu. Proposal/accept są deklaracjami; dopiero jawne structured accept z
modelowym linkiem do proposal liczy się jako explicit_acceptance. Ani to, ani
zgodność wyniku nie dowodzą wykonania zobowiązania, uczenia lub przyczynowej poprawy.

Agregat grupuje wyniki według trybu oraz model+tryb; małe zadania i jeden seed nie
uzasadniają rankingu. `quality_gain_claim=false` jest celowe. Ujemny lub nieznany
wynik jest poprawnym wynikiem eksperymentu. Publikować tylko agregaty lub jawne
syntetyczne przypadki; prywatne prompty/eksporty zostają lokalnie poza Git.
