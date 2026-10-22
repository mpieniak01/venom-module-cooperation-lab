# Plan: laboratorium współpracy modeli

Status: MIEJSCE DO EKSPERYMENTÓW GOTOWE TECHNICZNIE, 2026-10-21. GPU C0/L2,
macierz 30, browser/SSE/STOP/layout/i18n i OFF API/danych PASS. Macierz: 30/30
technical completed, 12/12 komunikacji, 30/30 strict-v1 unscorable (accuracy=null).
L1–L5, C0 i cleanup follow-up PR #553 scalone. [L5 PR #13](https://github.com/mpieniak01/venom-module-cooperation-lab/pull/13)
scalono jako `4346a66`; lokalne wdrożenie na obu main odebrano w API i DOM.
Kontrole PR i niezależny review odebranego kodu PASS. Ponowny rzeczywisty HTTP 400 ma
cleanup C0 PASS. Brak treści legacy chatu to osobny [Venom #554](https://github.com/mpieniak01/Venom/issues/554),
nie CHAT PASS ani blocker zakwalifikowanych modeli. [Dowody](RELEASE_ACCEPTANCE.md).

## Cel odbioru

Operator otwiera nowy opcjonalny ekran Venoma, wybiera zakwalifikowany model i scenariusz, uruchamia dwie odrębne sesje tych samych wag, widzi rzeczywistą wymianę wiadomości i powstający podział pracy, może zatrzymać eksperyment oraz wrócić do jego zapisu. Jedna kopia niezmiennych wag wystarcza, ale konteksty i stany A/B są osobne.

Odbiór wymaga istniejącego modelu kontrolnego i przynajmniej jednego nowego kandydata o wyróżniającej właściwości. Mock, ozdobny graf lub jedna wspólna historia z dwiema nazwami nie zamykają zakresu. Badamy współpracę; nie wymagamy, aby wynik eksperymentu był pozytywny.

## Decyzje

- Prywatne repo mpieniak01/venom-module-cooperation-lab. Moduł cooperation_lab, ekran /cooperation-lab, API /api/v1/cooperation-lab.
- Własne UI/i18n PL/EN/DE, scenariusze i wyniki. Reużycie MAF i publicznych kontraktów hosta; bez kopiowania Council lub instalacji nowej orkiestracji.
- Dwa uczestniki, tury kolejno, jeden aktywny eksperyment i jeden silnik LLM. Neutralne ID; główny wariant nie przydziela sztywnych ról.
- Model może proponować organizację; host kontroluje transport, fairness, uprawnienia i budżet.
- Tekstowe, weryfikowalne zadania, bez dowolnego exec i urządzeń. Dane lokalne, namespacowane i objęte retencją.

## PR i kolejność

| ID | Repo implementacji | Wynik | Zależności |
| --- | --- | --- | --- |
| [L1](prs/L1-module-foundation.md) | cooperation-lab | Integracja modułu, zapis i bramki | Plan |
| [C0](prs/C0-host-runtime-lease.md) | Venom core | Publiczny kontrakt zasobów LLM | Plan, równolegle z L1 |
| [L2](prs/L2-model-qualification.md) | cooperation-lab i izolowany komponent | Adapter i kwalifikacja kontroli + nowego modelu | L1; C0 przed realną inferencją |
| [L3](prs/L3-session-runner.md) | cooperation-lab | Dwie sesje, transport i runner | L1, C0, L2 |
| [L4](prs/L4-operator-workspace.md) | cooperation-lab | Widoczne i sterowalne prawdziwe flow | L3 |
| [L5](prs/L5-experiments-acceptance.md) | cooperation-lab | Scenariusze i pełny odbiór MVP | L1–L4 i C0 |

Aktualne wydania: L1 PR #9 (`d4797d7`), Venom C0 PR #552 (`aa2d6124`), L2 PR #10
(`95aa0bc`), L3 PR #11 (`b4623ff`) i [L4 PR #12](https://github.com/mpieniak01/venom-module-cooperation-lab/pull/12)
(`1021bb3`) są scalone. Końcowy kod L4 `6fb7613`: CI/contracts, Sonar, Snyk,
GitGuardian i niezależny review PASS. [L5 PR #13](https://github.com/mpieniak01/venom-module-cooperation-lab/pull/13)
scalono jako `4346a66`. Odebrana rewizja ma CI/contracts/Snyk/Sonar/GitGuardian
i niezależny review PASS; wdrożone API i ekran potwierdzono na obu main.
C0 cleanup follow-up [Venom #553](https://github.com/mpieniak01/Venom/pull/553) scalono jako `7401493`;
ten host jest obecnie przypięty w konfiguracji zgodności i CI modułu.
Pełne rewizje i linki: [RELEASE_ACCEPTANCE](RELEASE_ACCEPTANCE.md).

C0 baseline `aa2d6124` pozostaje minimum ABI 1.0.0. Aktualny przypięty host
z cleanup follow-up: `7401493f73db98dcdf2cb39503fca57eb2cbe421`, z kwalifikowanym
pojedynczym workerem. Historyczne SHA kwalifikacji GPU/macierz pozostają bez zmian. Realna próba potwierdziła blokadę host_chat podczas lease modułu oraz zwolnienie dopiero po quiescence. Moduł korzysta z tego kontraktu; jego lokalny mutex nie zastępuje ochrony hosta.

L/C to ID planu, nie numery GH. Scalenie poszczególnych etapów i końcowe SHA wydania są osobnym dowodem; implementacja lokalna nie oznacza automatycznie scalonego wydania. Powiązane dokumenty: [kontrakty](CONTRACTS.md), [kwalifikacja](MODEL_QUALIFICATION.md), [odbiór](ACCEPTANCE.md), [luki](GAP_REVIEW.md), [źródła](SOURCES.md).

## Granice MVP

Poza zakresem: trening SFT/LoRA/RL, nauka na wszystkich rozmowach, Vast/płatne API, klaster Hive, robot/wideo, automatyczne mnożenie agentów, CTM/Dreamer jako rozmówcy i komunikacja latent-state. Heterogeniczna para i więcej uczestników są kolejnym krokiem.

Laboratorium nie podmienia globalnego modelu chatu. Zajętość runtime jest jawna; przerwanie dotyczy tylko własnego wykonania. Liczymy pamięć cache wszystkich sesji i istniejącego modelu wizji.

## Realizacja i wydania

Każdy PR od świeżego main swojego repo. Lokalne testy i przegląd przed publikacją; potem review/CI i merge według zależności. Bez wielopiętrowych gałęzi o niejasnej bazie. Możliwy podział prac na C0 oraz L1; L3/UI można przygotowywać równolegle po zamrożeniu API. Kwalifikacja GPU tylko jednego modelu naraz. Realizacja została osobno autoryzowana przez właściciela; ten dokument sam nie uruchamia modeli.

L1 pokazuje prawdziwe not_ready; L4 daje interaktywny flow. Dopiero L5 kończy MVP na rzeczywistym hoście i nowym modelu. Wersje core/module/adapter oraz dane kwalifikacji są przypięte. Moduł OFF nie rezerwuje zasobów ani nie generuje pollingu; brak modułu nie blokuje core. Restart przerywa run bez auto-resume. Wyłączenie/anulowanie zwalnia wyłącznie własny zasób po potwierdzeniu końca obliczeń. Dane zostają do świadomego eksportu/usunięcia. Rollback przez zgodne tagi i OFF, bez zmian pinów aplikacji.


## Następny research po zamrożonym v1

Macierz v1 jest zakończona i zachowana bez zmian reguł oceny. Wszystkie 30 wyników
są unscorable z powodu formatu, nie trzydzieści odpowiedzi uznanych za błędne.
Prompt nie wymagał końcowego formatu rubryki, a Qwen osiągał limit 32 tokenów.
Kolejny zakres powinien określić jawny final-answer contract v2: nowy prompt,
wersję datasetu/rubryki, budżet i porównania. Nie poprawiać parsera v1 po obejrzeniu
odpowiedzi ani nie przepisywać historycznych wyników na pozorną poprawę jakości.


## Granica końcowego odbioru

Lokalny browser potwierdził start, wiadomości A/B, reload/replay, STOP/quiescence,
stałe sterowanie, desktop/mobile, PL/EN/DE, odtworzenie historii Qwen→RWKV
(model/2 tury/32 tokeny), pobranie eksportu własnej anulowanej próby i usunięcie
z potwierdzeniem 404. Pełny make check: 252 Python PASS, coverage 97%
(1993 statements / 55 miss), mypy 20 źródeł, 15 testów frontendowych PASS / 96,02%,
TS/lint i host contracts PASS. L5 PR #13 jest scalony; lokalne wdrożenie
na core `7401493` i module `4346a66` odebrano w API i DOM. Ponowny rzeczywisty probe
legacy chatu nadal zwrócił HTTP 400 w 0,032 s, bez treści/done. C0 cleanup PASS:
busy 1→available/0 w 0,002 s, ps[] przed/po, konfiguracja i wybór `gemma2:2b`
bez zmian. Legacy adapter śledzi osobny [Venom #554](https://github.com/mpieniak01/Venom/issues/554);
nie jest to CHAT PASS ani blocker zakwalifikowanych modeli laboratorium.
Pierwsze utracone body nie jest retrospektywnie diagnozowane.
Crash/retencja/quotas/OOM pozostają dowodami fixture.


## Następny zakres L7 — plan, 2026-10-22

[Specyfikacja jednego PR: ewaluacja gier, strategii i pamięci](prs/L7-game-evaluation.md).
Repo: cooperation-lab; TTT/Nim/Memory/Sokoban, referencje, replay/native,
fresh/carry, jawne dekodowanie i compute budget, raport i bezpieczne wznowienie.
Stan **implementacja lokalna / weryfikacja**, bez numeru PR GitHub. Plan
uwzględnia powtarzalne błędy z prób operatora; nie zmienia historycznych wyników.
Cały zaległy kod jest już na `codex/rwkv7-g1k-2.9b` (9 commitów ponad zdalnym
main po fetch); na tej gałęzi kontynuujemy. [Decyzja reuse](prs/L7-reuse-decision.md):
lokalny TTT + adaptacja wybranych fragmentów TextArena, bez całej biblioteki.
