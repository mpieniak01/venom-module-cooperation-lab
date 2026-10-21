# Venom Cooperation Lab

Opcjonalne laboratorium współpracy i samoorganizacji sesji modeli AI w Venomie.

**Stan: implementacja i odbiór.** Kwalifikacja GPU C0/L2, rzeczywista macierz 30 prób i OFF API/danych wykonane. Wszystkie próby zakończone technicznie; jakość strict-v1 jest nieocenialna, bez twierdzenia o zerowej trafności lub nauce. Rzeczywisty browser/SSE/STOP, stały układ, responsive i i18n odebrane. L1–L4 i C0 scalone; [L5 PR #13 do main](https://github.com/mpieniak01/venom-module-cooperation-lab/pull/13) jest otwarty do recenzji i kontroli. Próba zwykłego chatu po laboratorium zwróciła HTTP 400 przed pierwszą treścią; poprawka cleanup transportu i ponowny odbiór pozostają wymagane. Końcowy deployment nie jest zakończony. [Wyniki i ograniczenia](docs/RELEASE_ACCEPTANCE.md).

- [Plan i kolejność PR](docs/PLAN.md)
- [Zadania GitHub i PR planu](docs/ISSUES.md)
- [Kontrakty](docs/CONTRACTS.md)
- [Kwalifikacja modeli](docs/MODEL_QUALIFICATION.md)
- [Odbiór](docs/ACCEPTANCE.md)
- [Wyniki odbioru i jawne ograniczenia](docs/RELEASE_ACCEPTANCE.md)
- [Przegląd luk](docs/GAP_REVIEW.md)
- [Źródła](docs/SOURCES.md)

Core zapewnia kontrakty hosta. Własny ekran nie zastępuje Council, Academy, Inspector ani THE HIVE. Wyłączenie modułu ma zwalniać jego zasoby i nie blokować core. MVP nie obejmuje treningu i płatnej infrastruktury.

C0 oraz L1–L5 są ID etapów implementacji; status kodu, odbioru i scalenia opisują osobne dowody. Implementacja lokalna nie oznacza automatycznie ukończonego wydania. Repo na razie prywatne; licencję ustalić przed publicznym wydaniem kodu.

## Fundament L1

Opcjonalny pakiet i niezależny ekran pozostają domyślnie wyłączone. Implementację, testy i ograniczenia opisuje [FOUNDATION](docs/FOUNDATION.md). `make check HOST=/home/ubuntu/venom` korzysta z istniejącego stosu hosta, bez pobierania modeli.
