# Kontrakty laboratorium v1

Specyfikacja do implementacji. API nie istnieje jeszcze.

## Host

Manifest: cooperation_lab, module_api_version i min_core_version zgodne z zakwalifikowanym hostem; bazą planu jest module ABI1.6.0 na Venom main af81e322, nie numer wersji aplikacji. Backend FEATURE_COOPERATION_LAB, frontend NEXT_PUBLIC_FEATURE_COOPERATION_LAB, enabled_by_default=false. Async bounded lifecycle i własne i18n. Błędy manifestu kwarantannują moduł.

Wszystkie mutacje respektują host environment policy, odczyty/eksport/usuwanie jego politykę dostępu. Actor i owner/runtime pochodzą z hosta, nie od modelu lub niezaufanego JSON. Endpoint wybierany przez prekonfigurowane ID; brak dowolnych URL/redirectów z przeglądarki lub LLM. Zdalne API poza MVP. Brak własnego systemu kont.

## Dane

SQLite w resolve_module_data_root, np. data/modules/<scope>/cooperation_lab. state_files: lab.sqlite3, lab.sqlite3-wal, lab.sqlite3-shm. Core mutation guard przed utworzeniem/mutacją. W jednej bazie config, model qualification, runs i events; jawne transakcyjne migracje. Wagi poza bazą, w zarządzanym magazynie modeli, bez pobrań przez startup/web request.

Proponowane limity do zamrożenia w L1: 100 runów, 14 dni retencji, 512MiB bazy wraz z WAL/SHM, max2MiB/run oraz ograniczony rozmiar zdarzenia. Sprawdzać także wolne miejsce. Cleanup usuwa tylko zakończone runy, nigdy aktywny. Storage full ma jawny wynik, nie ciche braki logów. Eksport jednego runu ma limit i nie tworzy drugiej trwałej kopii. Bez wielkich blobów/sekretów w Git i bez pełnych promptów w logach core. VACUUM wymaga własnego budżetu wolnego miejsca.

## Model i niezależność

ModelSpec: ID i revision/digest, artefakt/kwantyzacja, tokenizer/template hash, runtime/version, schema capabilities/parametrów i receipt kwalifikacji. Stan available/loading/ready/unsupported/failed potwierdza adapter. Unknown/estymowany usage jest jawny, nie zerowy.

Participant: run_id, participant_id A/B, immutable model reference, private history/state handle i prompt encouragement. Wagi współdzielone tylko gdy niezmienne. Mutowalny KV/state/fast weights/optimizer odseparowany per uczestnik; reset także między runami. Brak obsługi specyficznego stanu daje unsupported, nie wspólną historię ukrytą pod dwoma ID.

## Wiadomości i organizacja

Envelope: schema_version, run_id, message_id, sender, recipient A/B/all, in_reply_to, sequence, turn_id, timestamp, kind. Rodzaje: message/proposal/accept/ask/evidence/complete. Runner nadaje tożsamość nadawcy; treść nie pozwala się podszyć ani podnieść limitów. Model proponuje plan/rolę, host waliduje schemat i adresata, bez ustalania semantycznego podziału pracy. Fair scheduler z zapisanymi parametrami. Complete to deklaracja, evaluator orzeka wynik.

Bez tworzenia nowych agentów, exec/shell i urządzeń. Stan i latent representations nie są bezpośrednio przekazywane partnerowi w MVP.

## Runner/API

RunConfig jest immutable: model/scenario version, participant_count=2, prompts, seed/sampling, tryb i budżet. Start z idempotency_key, max1 aktywny run/request generacji. Retry/dwie karty nie tworzą nowej pracy.

State machine: created → queued → preparing → running → completed lub failed; cancel → cancelling → cancelled. Restart → interrupted. Żaden stan nie uruchamia sam wznowienia. Kolejka zużywa deadline; nie odnawiamy czasu po każdej fazie. Konflikt zasobu runtime_busy.

API /api/v1/cooperation-lab: POST /runs; GET /runs i /runs/{id}; POST /runs/{id}/cancel; GET /runs/{id}/events?after=<seq>; GET /runs/{id}/events/stream; GET /runs/{id}/export; DELETE /runs/{id}. GET niczego nie uruchamia. Ograniczone paginacja, kursory, rozmiary i bezpieczne ID. Kody błędów przetłumaczone, bez sekretów/ścieżek w odpowiedzi.

SSE: typed run/turn/message/organization/usage/error/end i trwały seq. Najpierw smoke rzeczywistego same-origin proxy: brak buforowania, obsługa przerwania. Reconnect Last-Event-ID, catch-up po seq i dedup. Gdy retencja usunęła okno: snapshot/resync, nie cicha luka. Jeden kanał aktywny, bez jednoczesnego pollingu. Stan połączenia różny od stanu obliczeń.

Proponowany preset: max8 tur łącznie, do256 output tokenów/turę, do2048 tokenów kontekstu/uczestnika, wall budget360s oraz limit całej generacji. L3 zamraża total-input/output i limity kroków konkretnego modelu; liczyć powtarzane wejścia i wewnętrzne kroki. Ustawienia muszą być widoczne i efektywnie wymuszone, także gdy runtime nie raportuje usage.

## Anulowanie i zasób

Cancel idempotentnie blokuje kolejną turę. Cancelling trwa do potwierdzenia rzeczywistego końca inferencji. Zamknięcie socketu nie dowodzi końca GPU. Lease zwalniany po potwierdzonym quiescence; late worker oznacza busy/quarantine i kontrolowane recovery. Brak ślepego release po TTL przy aktywnym workerze. Nie zatrzymujemy cudzej pracy ani całego serwera. Shutdown ma bounded cleanup i jawny wynik niezakończonych obliczeń. C0 definiuje spójność również względem pozostałych konsumentów hosta i nieobsługiwanej topologii wielu workerów.
