# HRM-Text i Huginn — lokalne wdrożenie badawcze

Stan 2026-10-22: oba modele zainstalowane i dostępne w `/cooperation-lab`.
To wdrożenie lokalne na istniejącej gałęzi `codex/rwkv7-g1k-2.9b`, bez publikacji
tej zmiany na GitHub. Nie zmieniono globalnego silnika ani modelu operatora.

## Użycie

W ustawieniach eksperymentu wybierz silnik **RWKV / HRM / Huginn**, następnie
`sapientinc/HRM-Text-1B` albo `tomg-group-umd/huginn-0125`.
Modele są zakwalifikowane technicznie. Wybierz scenariusz i rozpocznij eksperyment.
Na początek: angielski, kółko i krzyżyk / gra aby wygrać, 32 tokeny na turę.
Wybór modelu sam nie ładuje wag. STOP anuluje własną próbę, a zakończenie zwalnia
proces i jego GPU. Nie są uruchamiane dwa silniki jednocześnie.

## Przypięte artefakty i istniejący stos

| Model | Rewizja upstream | Wagi na dysku | Runtime |
|---|---|---:|---|
| HRM-Text-1B | `22097cbcecdd1301afe30a19a3ee61b96a9863e5` | 2,37 GB | BF16 CUDA, natywna klasa `hrm_text` |
| Huginn-0125 | `bb6621b65e90b6a4b9b29ef88dc83866d450470c` | 15,65 GB | BF16 CUDA, przypięta klasa Raven |

Jedna kopia w `models/research/<model>/<revision>` hosta Venom. Wagi, tokenizery
i prywatne eksporty nie należą do Git. Manifest `adapters/hf_artifacts.json`
sprawdza rozmiary i skróty wszystkich plików przed załadowaniem (SHA256 wag,
Git blob SHA1 pozostałych plików). Działanie offline; kod Huginn ograniczony do
sprawdzonej rewizji, z tymczasowym cache usuwanym po zakończeniu procesu.
Nie instalowano nowego venv ani bibliotek: Python 3.14.8, Torch 2.13.0+cu130,
Transformers 5.17.0. Worker odrzuca inną wersję runtime zamiast używać starej
kwalifikacji. Zmiana szablonu również zmienia tożsamość kwalifikacji.

## Adaptacja do zadań

- HRM: PrefixLM, `token_type_ids=1` dla wejściowego prefiksu i `0` dla nowych
  tokenów; potem własny cache w obrębie odpowiedzi. Zadania strukturalne używają
  warunku `direct` i dwóch krótkich przykładów. Pozostałe używają `synth,cot`.
- Huginn: własny szablon rozmowy, poprawne znaczniki końca wypowiedzi; **8 kroków
  rekursji**. Cache wyłączony w tej pierwszej integracji, pełne przeliczenie
  krótkiego kontekstu przy kolejnych tokenach. Nie jest to stan stałej wielkości
  RWKV. Klasa z Transformers 4.44 dostaje lokalną mapę wiązania wag wymaganą przez
  Transformers 5 (`lm_head.weight` → `transformer.wte.weight`), bez modyfikacji
  upstream plików i bez podmiany pakietów hosta.
- Oddzielne konteksty A/B są odtwarzane z historii danej sesji, bez przenoszenia
  cache pomiędzy uczestnikami. Wspólne wagi nie oznaczają wspólnej pamięci rozmowy.
- W grze autorytatywna plansza trafia do każdej tury. Dekoder ogranicza odpowiedź
  do aktualnie wolnych współrzędnych. Model wybiera ruch; host nie stosuje minimax
  ani nie poprawia strategii. Surowa odpowiedź pozostaje w eksporcie.
- Kontekst do 2048 tokenów, limity czasu/tokenów i host admission pozostają aktywne.
  Za mało wolnego VRAM daje jawny błąd (progi wstępne: HRM 4 GiB, Huginn 9 GiB).

## Rzeczywisty odbiór RTX 3060 12 GiB

| Próba | HRM | Huginn |
|---|---|---|
| Kwalifikacja dwóch kontekstów | `b5459edeb95d4d81b4e1fc146465c1cc`, completed | `ac44640a78e84ba3a72bdd42344873f3`, completed |
| Czas ładowania raportowany przez worker | 5,63 s | 32,83 s |
| Szczyt alokacji Torch przy ładowaniu | 2,20 GiB | 6,65 GiB |
| Gra konkurencyjna | `b911daaef1134b98b84c0124cc90a79d`: 7 ruchów, wygrywa A | `cbb225081dc34c7d8cb59ea3f58e1f8d`: 8 ruchów, wygrywa B |
| Poprawność obsługi gry | wszystkie ruchy legalne; zakończenie i cleanup | wszystkie ruchy legalne; zakończenie i cleanup |

To pojedyncze próby integracyjne, nie benchmark jakości. Czas ładowania nie
obejmuje wcześniejszego hashowania plików; pierwszy start Huginn może być
znacznie dłuższy. Alokacja Torch nie obejmuje całego GPU/systemu; po zakończeniu
zostało około 1160 MiB bazowego użycia GPU i runtime zgłosił 0 aktywnych operacji.
Przeglądarka potwierdziła oba modele „Gotowy”, możliwość ich wyboru i aktywny START.

HRM nie jest dostrojonym modelem rozmownym: w teście powitania odpowiadał
„Thank you.” / „You are B.”. Kwalifikacja oznacza działanie techniczne, nie
spełnienie celu rozmowy. Pierwszy tryb `synth,cot` rozwlekał odpowiedź, co
uzasadniło osobny profil `direct`. Huginn w obu kontekstach zakończył krótkie
powitanie własnym znacznikiem końca tury. Nie potwierdzamy jakości polskiego,
strategii gry ani współpracy na podstawie tych kilku odpowiedzi. Wymagają
osobnej macierzy eksperymentów; nie trenowano modeli.

## Kontrole

Pełna kontrola modułu: `make check HOST=/home/ubuntu/venom` obejmuje Ruff,
mypy, Python/coverage >=90%, frontend TS/lint/testy i kontrakt modułu hosta.
Testy adaptera obejmują prefiks/causal HRM, rekursję Huginn, zgodność wiązania wag,
integralność artefaktów, dozwolone pola, deadline/cancel i izolację kontekstów.
Pierwszy końcowy przebieg równolegle z ładowaniem Huginn przekroczył deadline
trzech istniejących testów cleanup; powtórzenie na wolnym runtime: **371 Python
PASS, 96,09% coverage, 28 frontend PASS, Ruff/mypy/TS/lint/kontrakt hosta PASS**.

## Źródła

- [HRM-Text-1B — karta i warunki prefiksu](https://huggingface.co/sapientinc/HRM-Text-1B)
- [Huginn-0125 — karta modelu](https://huggingface.co/tomg-group-umd/huginn-0125)
- [Recurrent pretraining — kod autorów](https://github.com/seal-rg/recurrent-pretraining)
- [Wcześniejsza analiza HRM/Huginn/CTM](HUGINN_HRM_CTM_FEASIBILITY.md)


## Porządkowanie historii — 2026-10-22

Na polecenie operatora usunięto wszystkie pozostałe 94 próby przez API modułu.
Kwalifikacje modeli i ustawienia pozostały zachowane. Przycisk **Usuń próbę**
usuwa teraz wybraną zakończoną próbę po jednym kliknięciu, bez potwierdzenia.
Podczas żądania jest zablokowany; aktywnej próby nadal nie można usunąć.
