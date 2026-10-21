# Odbiór MVP

Lokalny odbiór techniczny GPU, macierzy 30, browser/SSE/STOP i OFF jest wykonany.
L1–L4 i C0 są scalone; wydanie pozostaje otwarte do kontroli/scalenia
[L5 PR #13](https://github.com/mpieniak01/venom-module-cooperation-lab/pull/13),
świeżego CI finalnego commita i potwierdzenia deploymentu. Cleanup C0 po
ponownym rzeczywistym HTTP 400 odebrany; brak treści legacy chatu pozostaje
osobnym [Venom #554](https://github.com/mpieniak01/Venom/issues/554). [RELEASE_ACCEPTANCE](RELEASE_ACCEPTANCE.md) podaje rzeczywiste wyniki,
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
- [x] Kontrolki mają identyczny prostokąt przed i podczas pracy; ponowny smoke finalnego refaktoru L4 na rewizji `382dd65` potwierdził desktop 1366×900 i mobile 390×844 bez poziomego overflow oraz oba mobilne START/STOP widoczne.
- [x] PL/EN/DE sprawdzone w rzeczywistym DOM; przywrócono PL. Podstawowy i ponowny finalny smoke: 0 błędów konsoli; ostrzeżenia wykresów hosta nie były zerowe. Dodatkowa weryfikacja Delete miała 1 oczekiwany błąd konsoli HTTP 404.
- [x] Rzeczywiste odtworzenie historii Qwen→RWKV obejmuje identyfikator modelu z kropkami oraz limity 2 tury / 32 tokeny.
- [x] Pobranie eksportu własnej anulowanej próby i usunięcie z potwierdzeniem HTTP 404 sprawdzone w przeglądarce.

## Odporność i dane — zakres testów fixture

- [x] Idempotency/retry/dwie karty i reconnect/gap mają testy fixture; realny reload/replay sprawdzono wyżej.
- [x] Cancel faz przygotowania/generacji, ignorujący anulowanie thread, pojedynczy close i late cleanup sprawdzone fixture. Realny STOP i cleanup GPU odebrane oddzielnie.
- [x] Crash/interrupted i brak auto-resume sprawdzone fixture; nie wymuszano crash realnego workera GPU.
- [x] Retencja, namespace/policy guards, limity runów/tokenów/czasu/kontekstu/kroków/bajtów/WAL/SHM/exportu i storage-full mają testy fixture.
- [x] Unavailable/OOM/malformed/unsupported mają testy fixture; bez zapychania rzeczywistego dysku i wywoływania GPU OOM.
- [x] Surowe prywatne dane i modele pozostają poza Git; publiczny raport ma wyłącznie zredagowane agregaty syntetyczne.

## Wydanie i jawne pozostałe granice

- [x] Ostatni pełny lokalny make check: 252 Python PASS, coverage 97% (1993 statements / 55 miss); mypy 20 źródeł; 15 testów frontendowych PASS, line coverage 96,02%; TS/lint i host contracts PASS.
- [x] L1 PR #9, Venom C0 PR #552, L2 PR #10, L3 PR #11 i L4 PR #12 scalone; rewizje zapisane w RELEASE_ACCEPTANCE.
- [x] Końcowy kod L4 `6fb7613`: CI/contracts, Sonar, Snyk, GitGuardian i niezależny review PASS.
- [x] L5 opublikowany jako [PR #13 do main](https://github.com/mpieniak01/venom-module-cooperation-lab/pull/13).
- [x] L5 PR #13: CI/contracts, Snyk, Sonar i GitGuardian PASS dla odebranej rewizji; niezależny review PASS. CodeRabbit rate-limited nie jest pełną recenzją.
- [x] C0 cleanup follow-up [Venom #553](https://github.com/mpieniak01/Venom/pull/553) scalony jako `7401493`; zgodność i CI modułu przypięte do tego hosta, ABI 1.0.0 bez zmian.
- [x] Rzeczywisty ponowny probe legacy HTTP 400: C0 CLEANUP PASS — busy 1→available/0 w 0,002 s, ps[] przed/po, konfiguracja bez zmian. Recovery miało fizyczny dowód końca workera, force=false.
- [x] Brak treści/done legacy chatu jawny: HTTP 400 w 0,032 s, nie CHAT PASS. Osobny [Venom #554](https://github.com/mpieniak01/Venom/issues/554), bez blokowania zakwalifikowanych modeli. Pierwsze utracone body nie jest retrospektywnie diagnozowane.
- [ ] Scalenie [PR #13](https://github.com/mpieniak01/venom-module-cooperation-lab/pull/13) po świeżym CI finalnego commita i deployment. Bieżący wynik w zakładce Checks tego PR, bez kołowego wskazywania własnego SHA dokumentacji.

Snyk/Sonar/GitGuardian i review oceniamy dla właściwych SHA, bez ogłaszania braku
skanu lub limitu jako PASS. Pięć odziedziczonych ID Torch pozostaje jawnie opisane;
nie dodajemy ignore dla wygładzenia bramki. Końcowy status wydania zatwierdza
koordynator po scaleniach, nie sam raport lokalny.

Wyniki v1 pozostają zamrożone. Następny research wymaga jawnego kontraktu
końcowej odpowiedzi i nowej wersji prompt/dataset/rubric v2; bez retrospektywnej
zmiany parsera lub historycznego wyniku na pozorny sukces.
