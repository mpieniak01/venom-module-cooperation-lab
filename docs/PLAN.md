# Plan: laboratorium współpracy modeli

Status: PLAN DO REALIZACJI, 2026-10-21. Repo utworzone za zgodą właściciela. Ten PR zawiera dokumentację, nie działający moduł ani wyniki inferencji.

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

C0 jest małym ogólnym PR hosta. Obecny RuntimeExclusiveGuard jest blokadą benchmarków; nie potwierdzono objęcia wszystkich konsumentów LLM. Jeżeli pełny audyt i testy C0 wykażą istniejący publiczny mechanizm spełniający kontrakt, udokumentować reużycie zamiast dodawać drugą blokadę. Do tego czasu lokalny mutex modułu nie wystarcza.

L/C to ID planu, nie wymyślone numery GH. Właściwe numery PR powstaną przy kodzie. Powiązane dokumenty: [kontrakty](CONTRACTS.md), [kwalifikacja](MODEL_QUALIFICATION.md), [odbiór](ACCEPTANCE.md), [luki](GAP_REVIEW.md), [źródła](SOURCES.md).

## Granice MVP

Poza zakresem: trening SFT/LoRA/RL, nauka na wszystkich rozmowach, Vast/płatne API, klaster Hive, robot/wideo, automatyczne mnożenie agentów, CTM/Dreamer jako rozmówcy i komunikacja latent-state. Heterogeniczna para i więcej uczestników są kolejnym krokiem.

Laboratorium nie podmienia globalnego modelu chatu. Zajętość runtime jest jawna; przerwanie dotyczy tylko własnego wykonania. Liczymy pamięć cache wszystkich sesji i istniejącego modelu wizji.

## Realizacja i wydania

Każdy PR od świeżego main swojego repo. Lokalne testy i przegląd przed publikacją; potem review/CI i merge według zależności. Bez wielopiętrowych gałęzi o niejasnej bazie. Możliwy podział prac na C0 oraz L1; L3/UI można przygotowywać równolegle po zamrożeniu API. Kwalifikacja GPU tylko jednego modelu naraz. Ten plan nie uruchamia implementacji/workerów.

L1 pokazuje prawdziwe not_ready; L4 daje interaktywny flow. Dopiero L5 kończy MVP na rzeczywistym hoście i nowym modelu. Wersje core/module/adapter oraz dane kwalifikacji są przypięte. Moduł OFF nie rezerwuje zasobów ani nie generuje pollingu; brak modułu nie blokuje core. Restart przerywa run bez auto-resume. Wyłączenie/anulowanie zwalnia wyłącznie własny zasób po potwierdzeniu końca obliczeń. Dane zostają do świadomego eksportu/usunięcia. Rollback przez zgodne tagi i OFF, bez zmian pinów aplikacji.
