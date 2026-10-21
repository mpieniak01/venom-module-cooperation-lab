# L2 — adapter i kwalifikacja nowego modelu

Status: SCALONY przez PR #10, merge `95aa0bc`. Formalna kwalifikacja C0/GPU RWKV i Qwen PASS; artefakty/ograniczenia opisują RWKV_L2 i RELEASE_ACCEPTANCE. Repo: venom-module-cooperation-lab; komponent izolowany poza Full.

## Problem i wynik

Wpis katalogu i obecność biblioteki nie potwierdzają zdolności modelu. Potrzebny nowy uczestnik o właściwości badawczej oraz kontrola istniejącego modelu.

## Zakres

Wykonać [plan kwalifikacji](../MODEL_QUALIFICATION.md): jeden konkretny mały checkpoint RWKV-7 po analizie licencji/artefaktu; zmiana kandydata jawnie uzasadniona. ID/revision/hash/tokenizer/template, effective params i receipt. Ograniczony lokalny adapter generate/cancel/status/reset/state; walidacja prekonfigurowanego endpointu i parametrów. Oddzielne stany A/B, bez dwóch kopii niezmiennych wag.

Brak całego research requirements w Full. Jeden izolowany przypięty runtime jeśli konieczny; przegląd wykonywalnego kodu, CUDA/Python i zależności. Specyfika modelu zostaje w module/komponencie. Ogólny host ABI wraca do C0. Kontrolowany limit pobrania i miejsca, bez pobierania podczas startupu/API i bez kasowania modeli/adapterów użytkownika.

## Walidacja

Cold start, 2–3 krótkie odpowiedzi, stan A nie wycieka do B, reset, cancel/quiescence i lease. Load/TTFT/generation-time, peakRAM/VRAM i rzeczywista efektywna precyzja. Failure/unsupported jawne, bez podstawiania mocka lub samej kontroli za nowy model. Fixtures dla malformed output/OOM/budżetu/paramów oraz minimalny realny odbiór. Powrót operatorowi jego zasobu i selekcji.

Poza zakresem: duży benchmark, drugi nowy model, trening i podbijanie pinów aplikacji.

## Kryteria zamknięcia

- [x] Zakres i zależności zgodne z planem; actual SHA hosta/modułu/adaptera zapisane.
- [x] Testy rzeczywiście wykonane, wyniki i skips jawne. Fixtures nie zastępują wymaganej inferencji.
- [x] Brak auto-download, zmiany globalnego modelu, kopii sekretów lub pozornego PASS.
- [x] Review i wymagane bramki, dokumentacja i sprawdzalny rollback.

Kontrakty: [CONTRACTS](../CONTRACTS.md). [Plan](../PLAN.md), [pełny odbiór](../ACCEPTANCE.md).

## Historyczny etap implementacji przed formalnym odbiorem 2026-10-21

- Gotowe przypięte adaptery `rwkv7-g1d-0.4b` i istniejącego `qwen3-4b-control`,
  wspólny frozen kontrakt, pure discovery i rejestr bez dowolnych URL/ścieżek API.
- RWKV: jeden izolowany proces, dwie prywatne historie/stany, cancel/reset,
  synchronize oraz join; bez zmian pinów Full i bez dodatkowego venv.
- Ollama: weryfikacja digest/runtime/template, oddzielne historie, terminal drain
  przy cancel, potwierdzenie unload własnego modelu; brak pull lub zmian selekcji.
- Jawny provisioner sprawdza fizyczny backing volume i hashe, nie działa w API.
- Wstępny realny test CUDA RWKV PASS; rzeczywista kontrola Qwen i formalny receipt
  C0 są nadal pending. ModelSpec pozostaje `qualified=false` do tego odbioru.
- [Dokładne piny, wyniki, ograniczenia i odtworzenie](../RWKV_L2.md).

- Dodano izolowany, przypięty overlay certifi 2026.10.19 / filelock 4.2.1
  (298919 B wheel), bez modyfikacji Full. Integralność i efektywne importy są
  sprawdzane przed Torch. CPU FileLock/TorchJIT PASS; formalny GPU odbiór nowego
  runtime pending. Pięć odziedziczonych FINDINGS Torch pozostaje jawnych.


Aktualny odbiór i granice dowodów: [RELEASE_ACCEPTANCE](../RELEASE_ACCEPTANCE.md).
