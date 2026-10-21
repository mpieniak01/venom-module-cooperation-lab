# Odbiór MVP

Lokalny odbiór techniczny GPU, macierzy 30, browser/SSE/STOP i OFF jest wykonany.
Wydanie pozostaje otwarte do kontroli i scalenia L4/L5 oraz potwierdzenia końcowych
SHA. [RELEASE_ACCEPTANCE](RELEASE_ACCEPTANCE.md) podaje rzeczywiste wyniki,
[EXPERIMENTS](EXPERIMENTS.md) metodologię, a [RUNBOOK](RUNBOOK.md) uruchomienie/OFF.
Zaznaczenia opisują dowód i jego granicę; fixture nie staje się testem GPU.

## Integracja i sesje — rzeczywiste dowody

- [x] Pakiet, manifest/ABI i włączona trasa działają w lokalnym hoście; kontrakty hosta PASS.
- [x] Nowy RWKV i kontrola Qwen mają rzeczywiste receipty C0/GPU, z load/generate/cancel/reset/quiescence.
- [x] Dwa ID i odrębne historie/stany. RWKV: fingerprinty, reset i brak wspólnego storage. Ollama: oddzielne pełne historie/reset; latent KV nie jest publicznie dostępne.
- [x] Realna macierz 2 × 3 × 5: 30/30 technicznie completed, 12/12 dialogowych prób z dostarczeniem i późniejszą odpowiedzią; zapis run/turn/seq/in_reply_to.
- [x] Wariant bez ról i z encouragement wykonane; deklaracje podziału pracy oddzielone od dowodu wykonania. Commitment execution nadal unscorable.
- [x] Jawne tożsamości modeli i actual/charged koszty. Strict-v1: 30/30 nieocenialne z powodu formatu; accuracy=null, nie 0%.
- [x] OFF API/danych: trasy modułu nieobecne, hash bazy niezmieniony, Rider obecny, host HTTP 200, Ollama puste. Menu OFF nie ma osobnego dowodu DOM.

## Browser/SSE/STOP — rzeczywiste dowody

- [x] START uruchomił próbę RWKV; w panelu widoczne rzeczywiste wiadomości A/B.
- [x] Reload zachował tę samą próbę i odtworzył wiadomości 1→4 bez nowego START.
- [x] Same-origin SSE przez 3300: HTTP 200/text/event-stream, replay kursor 2→seq 17.
- [x] STOP: cancelled/quiescent=true; lease available, active_operations=0, Ollama ps[].
- [x] Kontrolki mają identyczny prostokąt przed i podczas pracy; desktop 1366×900 i mobile 390×844 bez poziomego overflow.
- [x] PL/EN/DE sprawdzone w rzeczywistym DOM; przywrócono PL. Konsola: 0 błędów; ostrzeżenia wykresów hosta nie były zerowe.
- [x] Odtworzenie historii Qwen→RWKV obejmuje identyfikator modelu z kropkami i poprawne ustawienia formularza.

## Odporność i dane — zakres testów fixture

- [x] Idempotency/retry/dwie karty i reconnect/gap mają testy fixture; realny reload/replay sprawdzono wyżej.
- [x] Cancel faz przygotowania/generacji, ignorujący anulowanie thread, pojedynczy close i late cleanup sprawdzone fixture. Realny STOP i cleanup GPU odebrane oddzielnie.
- [x] Crash/interrupted i brak auto-resume sprawdzone fixture; nie wymuszano crash realnego workera GPU.
- [x] Retencja, namespace/policy guards, limity runów/tokenów/czasu/kontekstu/kroków/bajtów/WAL/SHM/exportu i storage-full mają testy fixture.
- [x] Unavailable/OOM/malformed/unsupported mają testy fixture; bez zapychania rzeczywistego dysku i wywoływania GPU OOM.
- [x] Surowe prywatne dane i modele pozostają poza Git; publiczny raport ma wyłącznie zredagowane agregaty syntetyczne.

## Wydanie i jawne pozostałe granice

- [x] Ostatni pełny lokalny make check: 252 Python PASS, coverage ok. 97%; 13 React PASS, line coverage 95.28%; mypy/TS/lint i host contracts PASS.
- [x] L1 PR #9, Venom C0 PR #552, L2 PR #10 i L3 PR #11 scalone; rewizje zapisane w RELEASE_ACCEPTANCE.
- [ ] L4 PR #12: kontrole i scalenie; obecny HEAD `971720b`.
- [ ] L5: publikacja, recenzja, kontrole i scalenie, następnie końcowe SHA/deployment.
- [ ] Inferencja zwykłego chatu po laboratorium nie była wykonana. Wolny lease nie potwierdza odpowiedzi modelu; ograniczenie pozostaje jawne.

Snyk/Sonar/GitGuardian i review oceniamy dla właściwych SHA, bez ogłaszania braku
skanu lub limitu jako PASS. Pięć odziedziczonych ID Torch pozostaje jawnie opisane;
nie dodajemy ignore dla wygładzenia bramki. Końcowy status wydania zatwierdza
koordynator po scaleniach, nie sam raport lokalny.

Wyniki v1 pozostają zamrożone. Następny research wymaga jawnego kontraktu
końcowej odpowiedzi i nowej wersji prompt/dataset/rubric v2; bez retrospektywnej
zmiany parsera lub historycznego wyniku na pozorny sukces.
