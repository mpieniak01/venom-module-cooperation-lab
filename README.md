# Venom Cooperation Lab

Opcjonalne laboratorium współpracy i samoorganizacji sesji modeli AI w Venomie.

**Stan: planowanie.** Nie ma jeszcze działającego modułu, modeli ani wyników benchmarków. Pierwszy cel: zakwalifikować nowy model o interesujących właściwościach i zapewnić operatorowi widoczną, rzeczywistą wymianę między dwoma niezależnymi sesjami tych samych wag.

- [Plan i kolejność PR](docs/PLAN.md)
- [Zadania GitHub i PR planu](docs/ISSUES.md)
- [Kontrakty](docs/CONTRACTS.md)
- [Kwalifikacja modeli](docs/MODEL_QUALIFICATION.md)
- [Odbiór](docs/ACCEPTANCE.md)
- [Przegląd luk](docs/GAP_REVIEW.md)
- [Źródła](docs/SOURCES.md)

Core zapewnia kontrakty hosta. Własny ekran nie zastępuje Council, Academy, Inspector ani THE HIVE. Wyłączenie modułu ma zwalniać jego zasoby i nie blokować core. MVP nie obejmuje treningu i płatnej infrastruktury.

C0 oraz L1–L5 są ID planowanych implementacyjnych PR; numery GH powstaną przy kodzie. Nie tworzymy pustych PR udających realizację. Repo na razie prywatne; licencję ustalić przed publicznym wydaniem kodu.

## Fundament L1

Opcjonalny pakiet i niezależny ekran pozostają domyślnie wyłączone. Implementację, testy i ograniczenia opisuje [FOUNDATION](docs/FOUNDATION.md). `make check HOST=/home/ubuntu/venom` korzysta z istniejącego stosu hosta, bez pobierania modeli.
