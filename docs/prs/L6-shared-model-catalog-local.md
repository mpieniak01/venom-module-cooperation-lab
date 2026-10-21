# L6 — lokalny PR: wspólny katalog modeli laboratorium

Status: zrealizowane i wdrożone lokalnie na `codex/lab-language-chat-local`, bez GH. Repo: moduł
cooperation-lab; bez zmiany globalnej konfiguracji hosta i bez nowych zależności.

## Cel

Wybór Silnik → Model korzysta ze wspólnych reguł lokalnego katalogu Venoma.
Nie filtrujemy po trainable; modele inference-only również są kandydatami.
Katalog kontenerów/cache nie jest katalogiem modeli. Deduplikujemy aliasy wg digest.

## Zakres

- Read-only bridge do istniejących reguł katalogu hosta. Nie wywoływać pełnego
  GET options z jego auto-heal, przełączenia globalnego modelu lub chmury.
- Ollama: rzeczywiste lokalne tags/show, completion i template, przypięte digest,
  template/runtime; istniejący kontrolny Qwen i RWKV zachowują swoje ID/hash.
- Pozostałe silniki widoczne z opisanym brakiem adaptera/niedostępnością.
- Nowy, zainstalowany model Ollamy można uruchomić bezpośrednio (`can_run`).
  Osobne opcjonalne sprawdzenie wykonuje dwie krótkie generacje w oddzielnych
  kontekstach i zapisuje receipt dopiero po quiescence (`qualified`). Ma journal,
  idempotency i STOP; nie pobiera wag i nie stanowi benchmarku jakości.
- Przypięta tożsamość przed generacją jest ponownie sprawdzana przez adapter.
  Zmiana digestu/runtime/template nie dziedziczy starej kwalifikacji.
- UI: silnik ogranicza modele; wybór i odświeżenie nie aktywują silnika globalnie.
  Historia pokazuje model własnej konfiguracji także po zmianie katalogu.

## Poza zakresem

Adaptery generowania multi_runtime/vLLM/ONNX/chmury, osobne wagi A/B, pobieranie
modeli, trening, kasowanie cache/modeli i naprawa surowego /models w core.

## Odbiór

Pełny make check; testy źródeł katalogu, aliasów, błędów, tożsamości i braku
mutacji globalnego stanu, kwalifikacji/cancel/cleanup/idempotency oraz selektorów.
Browser desktop/mobile bez przypadkowych generacji. Jeden nowy mały model do
rzeczywistego smoke testu, jeżeli runtime jest wolny; nie cała macierz modeli.

## Wynik lokalny — 2026-10-21

- 314 testów Python PASS, coverage 97,54%; 26 frontend PASS, coverage 97,63%.
  Ruff, mypy (23 źródła), TypeScript, lint i kontrakt opcjonalnego modułu PASS.
  Dwie odziedziczone deprecjacje pytest pozostają ostrzeżeniami.
- Rzeczywisty katalog: RWKV, 10 unikalnych modeli Ollamy (12 tagów/aliasów),
  3 checkpointy vLLM, 1 wpis multi_runtime; ONNX offline bez modeli obsługiwanych
  przez bieżący profil. vLLM/multi_runtime/ONNX nie mają adaptera generowania Lab.
- Desktop 1366×900 i mobile 390×844 PASS: filtr silnika, jawne powody blokady,
  brak poziomego overflow, historyczny odbiór blokady START przed sprawdzeniem; zastąpiony poniższą poprawką.
- Z przycisku „Sprawdź model” wykonano rzeczywistą próbę `llama3.2:1b`:
  `233b8511cfbb401ab3291176a7d3ec7a`, completed. A/B po jednej odpowiedzi,
  38 tokenów wejścia i 3 wyjścia na kontekst; generation 10,49 s / 2,12 s,
  TTFT 10,41 s / 2,10 s. Czas obejmuje ładowanie; nie jest to pomiar samych wag.
  Limity: 32 tokeny/turę, 2048 kontekstu, 120 s. `end.quiescent=true`,
  admission available/0, Ollama `/api/ps` puste. Globalny model operatora zachowany.
- Brak nowych pobrań, pakietów, venv, zmian core lub robota. Brak publikacji na GH.
  Surowy eksport i logi są prywatne w katalogu raportów hosta, poza Git modułu.

## Ograniczenia i utrzymanie

Współdzielony katalog używa obecnych prywatnych helperów klasyfikacji hosta
`system_llm`; test kontraktowy i rzeczywisty odczyt wykonano dla core `7401493`.
Zmiana ich sygnatur wymaga sprawdzenia bridge. Nie reużywamy komponentu ChatComposer,
bo zawiera globalne przełączanie modelu i funkcje Academy niezwiązane z Lab.
Katalog jest buforowany przez 30 s; adapter ponownie sprawdza tożsamość przed
pierwszą generacją. Niedostępne odświeżenie blokuje Ollamę i zachowuje błąd.

Nowy przycisk daje wyłącznie techniczną zgodność istniejącego adaptera Ollamy:
dwie niepuste odpowiedzi, izolowane historie, reset i potwierdzony cleanup.
Nie zastępuje pełnego odbioru nowej architektury L2, testu jakości/scenariuszy,
benchmarku VRAM/RAM ani fizycznego testu cancel dla każdej pary wag. Te metryki
nie zostały zmierzone dla całej listy. RWKV i kontrolny Qwen zachowują wcześniejszy
odbiór; Llama ma dodatkowo powyższy lokalny smoke, pozostałe modele mogą rozpoczynać eksperyment bez dodatkowego sprawdzenia.
Metadane nie potwierdzają jakości ani udanego wykonania każdego scenariusza.


## Poprawka odbiorowa: bezpośredni START i formularz

[Zakres i dowody poprawki](L6-operator-recovery-local.md). Warunek dodatkowej
kwalifikacji przed START Ollamy został wycofany. `can_run` opisuje obsługę przez
adapter, `qualified` wynik opcjonalnego sprawdzenia; nie należy ich utożsamiać.
