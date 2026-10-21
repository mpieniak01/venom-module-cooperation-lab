# Odbiór MVP

Kryteria odbioru zaimplementowanej lokalnie bazy. Pola pozostają nieodhaczone do rzeczywistych receiptów koordynatora, dokładnych SHA i wyników właściwych bramek. Testy fixture nie zastępują GPU/browser/OFF acceptance. Narzędzia: [EXPERIMENTS](EXPERIMENTS.md), [RUNBOOK](RUNBOOK.md).

## Integracja

- [ ] Czysta instalacja pakietu, manifest, ABI, flagi OFF i własna trasa/menu/i18n PL/EN/DE.
- [ ] Brak/OFF/błędny manifest nie blokuje core i nie uruchamia modeli/pollingu/zapisów.
- [ ] Dotychczasowe chat/Council/Inspector/Rider zachowują kontrakty; brak cichej podmiany modelu lub drugiego engine.
- [ ] Nowy model i kontrola mają rzeczywisty receipt, nie wyłącznie metadane API.

## Sesje i komunikacja

- [ ] Dwa ID i osobne historie/stany na tych samych wagach; reset i brak przecieku A/B oraz między runami.
- [ ] Prawdziwa wiadomość/propozycja A→B, odebrana i obsłużona przez B; pełne run/turn/seq/in_reply_to w UI i zapisie.
- [ ] Wariant bez ról i z encouragement; organizacja i faktyczne wykonanie ocenione niezależnie od konsensusu.
- [ ] Jawne checkpoint/efektywne parametry/współdzielenie wag. Nie mylimy sesji z dwiema fizycznymi kopiami modelu.

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

- [ ] Warianty samotnie/samokorekta/no-contact/komunikacja z i bez encouragement na zamrożonych danych i porównywalnym koszcie.
- [ ] Jedna krótka pełna realna sesja nowego modelu na fizycznym GPU; dowód wiadomości i efektu. Brak obowiązku przewagi nad baseline.
- [ ] Browser flow rzeczywistego hosta; działający streaming przez same-origin proxy, stałe sterowanie, czytelny reconnect/STOP, długie treści i responsive.
- [ ] Testy modułu/backend/frontend, host contracts i brak regresji. Exact SHA core/module/adapter oraz rollback/OFF/retencja.

L1 ustala powtarzalne make check i CI: Ruff, mypy, pytest (backend coverage >=90%), frontend TS/lint/unit, host module contracts i browser tests. C0 respektuje istniejące make pr-fast i progi Venoma. Mocki są do regresji, nie zamiast realnego odbioru.

Snyk/Sonar/GitGuardian dla nowego repo skonfigurować w właściwej organizacji mpieniak01. Brak projektu/tokenu/limity planu nie są PASS. Jawny blocker nie daje automatycznej zgody na release ani wyciszenie. Nie zgłaszać zielonych bramek przed ich wykonaniem. Testy nie wymagają hardware Rider i wielogodzinnego ponawiania modeli.
