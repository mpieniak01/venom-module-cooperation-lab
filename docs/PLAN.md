# Plan: laboratorium współpracy modeli

Status: IMPLEMENTACJA L1–L5, 2026-10-21. Formalna kwalifikacja GPU C0/L2 PASS;
rzeczywista macierz L5: 30/30 technicznie completed, 12/12 komunikacji w trybach
dialogowych, 30/30 strict-v1 unscorable (accuracy nieznane). Realny OFF API/dane
PASS. Browser/layout/cancel, końcowy deployment oraz właściwe bramki wydania
pozostają pending. Dowody: [RELEASE_ACCEPTANCE](RELEASE_ACCEPTANCE.md).

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

C0 jest scalonym publicznym kontraktem admission/lease hosta (aa2d6124), z kwalifikowanym pojedynczym workerem. Realna próba potwierdziła blokadę host_chat podczas lease modułu oraz zwolnienie dopiero po quiescence. Moduł korzysta z tego kontraktu; jego lokalny mutex nie zastępuje ochrony hosta.

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
