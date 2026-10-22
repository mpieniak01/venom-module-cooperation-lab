# Venom Cooperation Lab

Opcjonalne laboratorium współpracy i samoorganizacji sesji modeli AI w Venomie.

**Stan: gotowe miejsce do rzeczywistych eksperymentów.** Kwalifikacja GPU C0/L2, macierz 30 prób, OFF i browser/SSE/STOP/layout/i18n/export/Delete wykonane. Macierz: 30/30 technicznie completed, 12/12 komunikacji, strict-v1 unscorable i accuracy=null. L1–L5, C0 i [cleanup follow-up Venom #553](https://github.com/mpieniak01/Venom/pull/553) scalone. [L5 PR #13](https://github.com/mpieniak01/venom-module-cooperation-lab/pull/13) scalono jako `4346a66`; lokalne wdrożenie na core `7401493` i module main potwierdzono w API oraz DOM. Kontrole PR i niezależny review odebranego kodu PASS. Cleanup C0 po rzeczywistym HTTP 400 PASS; brak treści legacy chatu to [osobne ograniczenie #554](https://github.com/mpieniak01/Venom/issues/554), bez twierdzenia o CHAT PASS. [Wyniki i ograniczenia](docs/RELEASE_ACCEPTANCE.md).

- [Plan i kolejność PR](docs/PLAN.md)
- [Zadania GitHub i PR planu](docs/ISSUES.md)
- [Kontrakty](docs/CONTRACTS.md)
- [Kwalifikacja modeli](docs/MODEL_QUALIFICATION.md)
- [Serie gier i pamięć poprzednich partii](docs/GAME_SERIES.md)
- [HRM-Text i Huginn: wdrożenie lokalne, użycie i ograniczenia](docs/HF_RESEARCH_MODELS.md)
- [Odbiór](docs/ACCEPTANCE.md)
- [Wyniki odbioru i jawne ograniczenia](docs/RELEASE_ACCEPTANCE.md)
- [Przegląd luk](docs/GAP_REVIEW.md)
- [Źródła](docs/SOURCES.md)

Core zapewnia kontrakty hosta. Własny ekran nie zastępuje Council, Academy, Inspector ani THE HIVE. Wyłączenie modułu ma zwalniać jego zasoby i nie blokować core. MVP nie obejmuje treningu i płatnej infrastruktury.

C0 oraz L1–L5 są ID etapów implementacji; status kodu, odbioru i scalenia opisują osobne dowody. Implementacja lokalna nie oznacza automatycznie ukończonego wydania. Repo na razie prywatne; licencję ustalić przed publicznym wydaniem kodu.

## Fundament L1

Opcjonalny pakiet i niezależny ekran pozostają domyślnie wyłączone. Implementację, testy i ograniczenia opisuje [FOUNDATION](docs/FOUNDATION.md). `make check HOST=/home/ubuntu/venom` korzysta z istniejącego stosu hosta, bez pobierania modeli.

## Rozszerzone laboratorium (L6)

Formularz laboratorium pokazuje
rzeczywiste modele katalogu Venoma, również modele bez funkcji treningu.
Wybierz **Silnik**, potem **Model** i od razu **Rozpocznij eksperyment**.
Zainstalowane modele Ollamy z szablonem completion nie wymagają dodatkowego testu.
**Sprawdź model (opcjonalnie)** to odrębna diagnostyka dwóch krótkich odpowiedzi;
anulowanie jej nie blokuje zwykłego START. Działa wspólny STOP i historia. Sam wybór modelu
lub odświeżenie nie uruchamia obliczeń ani nie przełącza globalnego chatu.

Silniki bez adaptera Lab pozostają widoczne z powodem blokady. Nie pobieramy modeli.
Szczegółowy [zakres lokalnego PR i dowody](docs/prs/L6-shared-model-catalog-local.md).
Pełny [zakres wydania L6, dowody i ograniczenia](docs/RELEASE_L6.md).
Opis historycznego wydania powyżej dotyczy scalonych L1–L5.
