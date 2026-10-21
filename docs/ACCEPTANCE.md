# Odbiór MVP

Kryteria odbioru implementacji. Formalne C0/L2 GPU, macierz 30 i OFF API/danych mają rzeczywiste receipty. Browser/layout/cancel, końcowe SHA oraz bramki wydania są pending. Zaznaczenie dotyczy wyłącznie podanego dowodu, nie pozostałych części odbioru. [Wyniki i ograniczenia](RELEASE_ACCEPTANCE.md). Testy fixture nie zastępują GPU/browser/OFF acceptance. Narzędzia: [EXPERIMENTS](EXPERIMENTS.md), [RUNBOOK](RUNBOOK.md).

## Integracja

- [ ] Czysta instalacja pakietu, manifest, ABI, flagi OFF i własna trasa/menu/i18n PL/EN/DE.
- [ ] Brak/OFF/błędny manifest nie blokuje core i nie uruchamia modeli/pollingu/zapisów.
- [ ] Dotychczasowe chat/Council/Inspector/Rider zachowują kontrakty; brak cichej podmiany modelu lub drugiego engine.
- [x] Nowy model i kontrola mają rzeczywisty receipt C0/GPU, z load/generate/cancel/reset/quiescence.
- [x] Realny OFF: trasy API modułu nieobecne, hash bazy niezmieniony, Rider obecny, host zdrowy, Ollama puste; dowód off-acceptance.json. Odbiór menu/ponownego włączenia pozostaje pending.

## Sesje i komunikacja

- [x] Dwa ID i osobne historie/stany; formalny RWKV potwierdził fingerprinty/reset/brak wspólnego storage. Ollama: osobne pełne historie i reset; latent KV nieudostępnione publicznie. Cleanup kończy własny run przed kolejnym.
- [x] Prawdziwa wiadomość A→B odebrana i obsłużona w 12/12 dialogowych runach; ślad run/turn/seq/in_reply_to w journalu.
- [ ] Ten sam rzeczywisty przepływ potwierdzony w UI przeglądarki.
- [x] Wariant bez ról i z encouragement wykonane. Deklaracje organizacji i wykonanie oddzielone od konsensusu; commitment_execution pozostaje unscorable, bez twierdzenia o zrealizowanym podziale pracy.
- [x] Jawne checkpoint/efektywne parametry i jedna kopia niezmiennych wag RWKV; model identities i koszty zachowane w zredagowanym raporcie.

## Odporność i dane

- [ ] Retry startu i dwie karty nie dublują runu/generacji; reconnect odtwarza zdarzenia i wykrywa lukę retencji.
- [ ] Cancel w kolejce/preparing/generacji/między turami; late worker nie zwalnia lease i nie uruchamia następnej tury.
- [ ] Cancelled dopiero po końcu obliczeń; failure/quarantine widoczne. Nie zatrzymujemy cudzej pracy.
- [ ] Crash/restart/disable oznacza interrupted/failed, bez auto-resume; bounded cleanup.
- [ ] Model unavailable, OOM, malformed output, unsupported param i storage full mają jawne stany.
- [ ] Limity tur/tokenów/czasu/kontekstu/kroków/bajtów faktycznie wymuszone.
- [ ] Namespace/policy guards, bezpieczne ID i ścieżki, retencja nie usuwa aktywnej sesji. Budżet obejmuje WAL/SHM/export.
- [ ] Brak modeli, sekretów i prywatnych promptów w Git/globalnych logach; eksport/usuwanie respektują host policy.

## Testy i wydanie

- [x] Pełna macierz 2 × 3 × 5 wariantów na zamrożonym v1, seed 17, maks. 2 tury/32 output. Actual/charged koszty zapisane; privileged baseline dostaje więcej informacji. 30/30 unscorable nie oznacza 0% accuracy.
- [x] Rzeczywiste sesje RWKV i Qwen zakończone 30/30 technicznie;12/12 dialogowych prób potwierdziło wymianę. Efekt jakościowy nieocenialny w strict-v1, bez obowiązku przewagi nad baseline.
- [ ] Browser flow rzeczywistego hosta; działający streaming przez same-origin proxy, stałe sterowanie, czytelny reconnect/STOP, długie treści i responsive.
- [ ] Testy modułu/backend/frontend, host contracts i brak regresji. Exact SHA core/module/adapter oraz rollback/OFF/retencja.

L1 ustala powtarzalne make check i CI: Ruff, mypy, pytest (backend coverage >=90%), frontend TS/lint/unit, host module contracts i browser tests. C0 respektuje istniejące make pr-fast i progi Venoma. Mocki są do regresji, nie zamiast realnego odbioru.

Snyk/Sonar/GitGuardian dla nowego repo skonfigurować w właściwej organizacji mpieniak01. Brak projektu/tokenu/limity planu nie są PASS. Jawny blocker nie daje automatycznej zgody na release ani wyciszenie. Nie zgłaszać zielonych bramek przed ich wykonaniem. Testy nie wymagają hardware Rider i wielogodzinnego ponawiania modeli.


Wyników v1 nie przeliczamy poprawionym po fakcie parserem. Następny research
powinien zamrozić nowy jawny format końcowej odpowiedzi oraz prompt/dataset/rubric
v2, bez zacierania wyników i ograniczeń tej macierzy.
