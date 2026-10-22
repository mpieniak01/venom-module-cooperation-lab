# RWKV-7 G1k 2,9B — lokalny wariant laboratorium

Dodany obok zachowanego G1d 0,4B. ID: `rwkv7-g1k-2.9b`.
Źródło: https://huggingface.co/BlinkDL/rwkv7-g1
Revision: `2a17e911155a5be23a4ed2792e978c77038f14e2`.
Plik: `rwkv7-g1k-2.9b-20260930-ctx25600.pth`, 5896273469 bajtów.
SHA256: `d8f8ecd4af8d706f867ac8a74284f35c0e3b9f863e7b09bb4d4031480c8b28b2`.

Instalacja jawna, poza startupem, w istniejącym katalogu modeli pod
`COOPERATION_LAB_RWKV_MODEL_ROOT/<revision>/<artifact>`.
Brak nowych zależności, venv, kopii runtime lub zmiany wag 0,4B.
Wspólny runtime RWKV 0.8.32 / Torch 2.13 CUDA FP16; jeden silnik naraz,
jedne wagi i oddzielne konteksty A/B. Hash sprawdzany dla wybranego modelu.
Kontekst treningowy checkpointu 25600 nie zmienia limitu laboratorium 2048.

Model widoczny w selektorze Silnik → RWKV / local_component. Gotowość wymaga
receiptu kwalifikacji przypiętego do tożsamości, nie samej obecności na liście.
Kwalifikacja przez POST /api/v1/cooperation-lab/qualifications wykonuje dwie
krótkie generacje, reset i cleanup przez wspólne admission. Nie zmienia globalnego
modelu operatora. Zmiana digestu unieważnia wcześniejszą kwalifikację.

## Odbiór lokalny 2026-10-22

- Rozmiar i pełny SHA256 pliku zgodne z upstream LFS.
- Run `cdf6d3ffba8344d7a9b4da6cf10b486f`: completed, quiescent=true.
- CUDA FP16; load wag 9,05 s. Dwie odpowiedzi po 9 tokenów, EOS.
- Generacja A 4,17 s (TTFT 3,74 s, pierwsza/JIT); B 0,60 s (TTFT 0,33 s).
- Po cleanup admission dostępne; pamięć GPU wróciła do około 1,6 GiB systemowo.
- To odbiór techniczny, nie benchmark jakości współpracy ani języka polskiego.
- make check: 329 Python PASS, coverage 97,60%, frontend/TS/lint oraz kontrakt hosta PASS.

Licencja Apache-2.0. Model bazowy; poprawne ładowanie nie gwarantuje poprawnych
ruchów w grze, formatu JSON lub współpracy. Usunięcie tej opcji nie wymaga kasowania
historii. Wagi nie są częścią Git.
