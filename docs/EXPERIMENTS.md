# Małe eksperymenty współpracy — L5

Status: formalna kwalifikacja GPU C0/L2 i rzeczywista pełna macierz L5 wykonane.
30/30 runów zakończyło się technicznie, komunikacja 12/12 w trybach dialogowych.
Strict-v1: 30/30 unscorable z powodu formatu, accuracy=null (nie 0%). Realny OFF
API/danych oraz rzeczywisty browser/SSE/STOP/layout/i18n PASS. Końcowe kontrole
i scalenie L4/L5 pozostają pending; chatu po laboratorium nie uruchamiano, a
crash/retencja/quotas mają dowody fixture.
[Dokładne wyniki](RELEASE_ACCEPTANCE.md), [zredagowany JSON](EXPERIMENT_RESULTS_V1.json).
Test fixture nie jest próbą modelu, a poprawny transport nie dowodzi nauki lub
przewagi jakościowej.

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


### Spójność transportu i ograniczenie odpowiedzi

Evaluator sprawdza zgodność `recipient` z faktycznym `delivered_to`, rozwiązuje
`all` wyłącznie do drugiego uczestnika i odrzuca self-recipient. Wynik tasku nie
jest scorable bez pełnej relacji generating-turn → usage → message z tym samym
turn_id, właściwym nadawcą i kolejnością seq. Sama wiadomość z poprawnym tekstem
nie potwierdza wykonania generacji. Niepotwierdzona relacja ma
`turn_evidence_verified=false` i nie daje `communication_observed=true`.

`usage.per_turn` zachowuje do ośmiu wpisów: turn_id, stop_reason, actual/charged,
TTFT/generation i ograniczoną whitelistę skalarnych effective_parameters.
`truncation_count` liczy jawny limit długości (`length` i pokrewne kody), a
nieznane przyczyny pozostają `truncated=null` oraz są osobno zliczane. Przy limicie
32 tokenów obcięcie Qwen/RWKV musi być widoczne w interpretacji jakości, zamiast
zniknąć w sumie kosztów. Nie zmieniamy limitu po wyniku, aby uzyskać sukces.


### Późne potwierdzenie cleanup

`end failed/quiescent=false` pozostaje nieudanym wynikiem. Zwolnienie zasobu może
zostać potwierdzone późniejszym ostatnim trwałym zdarzeniem `run` z tym samym
run_id/status, `quiescent=true` i `cleanup_late=true`. Evaluator zachowuje
pierwotne `end_quiescent=false`, technical_status failed oraz task unscorable;
zapisuje osobno źródło/seq dowodu cleanup. Nie przekształca failed w completed.
Agregaty oddzielnie liczą techniczne błędy i późne potwierdzenia zwolnienia.

CLI może odczytywać ponownie **ten sam export** przez maksymalnie20s (do20
odczytów), bez ponawiania generacji, zmiany statusu lub zwalniania lease.
Trwała quarantine po tym limicie blokuje następną próbę/usuwanie i kończy batch
jawnym acceptance_quiescence_unconfirmed; nie ma nieograniczonego polling loop.


## Wniosek z rzeczywistej macierzy v1

Prompt v1 nie narzucił formatu końcowej odpowiedzi, podczas gdy niezależna rubryka
wymaga krótkiego jednoznacznego wyniku. Qwen 27/27 generacji osiągnął limit 32 tokenów;
RWKV 6/27 także został obcięty. Każdy z 30 wyników ma unscorable/ambiguous_format,
nie incorrect. Kontrakt v1, fakty i reguły parsowania pozostają niezmienione.
Kolejny research to osobny explicit final-answer contract v2 z nowymi promptami,
wersją datasetu/rubryki i budżetem; bez retrospektywnego podnoszenia oceny v1.
