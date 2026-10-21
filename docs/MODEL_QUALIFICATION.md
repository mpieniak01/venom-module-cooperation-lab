# Kwalifikacja modeli

Istniejący Qwen/Gemma jest kontrolą infrastruktury. Odbiór MVP wymaga także jednej nowej architektury o właściwości badawczej.

## Kolejność

1. Mały RWKV-7, rodzina BlinkDL/rwkv7-g1: badanie oddzielnego stanu A/B i utrzymywania ustaleń. W L2 wybrać JEDEN checkpoint ok.0.4–1.5B po analizie konkretnej karty, prompt template, licencji i rozmiaru; przed pobraniem zapisać revision, plik, hash i limit bajtów. Nie pobierać całego repo wag.
2. Huginn-0125 jest kolejną opcją, nie obowiązkowym drugim pobraniem. Wymaga przypięcia i przeglądu custom code/cache oraz efektywnego num_steps; brak zmiany globalnego trust_remote_code. Warmstart tokenów nie oznacza trwałej pamięci sesji.
3. Qwen3.5-2B jest praktycznym kandydatem użytkowym; HRM-Text pre-alignment/PrefixLM ma osobne wymagania i brak chat-readiness nie rozstrzyga wartości architektury. CTM/TTT/Dreamer poza pierwszym MVP.

## Minimalny eksperyment kwalifikacyjny

- Sprawdzić rzeczywisty magazyn, pakiety i budżet dysku/RAM/GPU, uwzględniając wizję i oba konteksty. Odczyt /api/tags nie jest odbiorem modelu.
- Zamrozić checkpoint/tokenizer/template/licencję, adapter, Python/CUDA i zależności; sprawdzić kod wykonywalny i zależności. Skan nie jest powodem kopiowania sekretów.
- Jeden silnik i checkpoint naraz; rezerwacja zasobu C0 oraz jawny powrót do wcześniejszego ustawienia operatora. Brak auto-download/auto-load na startupie.
- Jeden cold start, 2–3 krótkie odpowiedzi, dwa niezależne konteksty, test nieprzeciekania, cancel/quiescence i reset. Bez dużego benchmarku lub treningu.
- Receipt: exact ID/hash, efektywne parametry, load/TTFT/generation-time, tokeny, peakRAM/VRAM, stan cleanup i wynik kwalifikacji. Warm/cold osobno, nieznane metryki jawne.
- Failure/unsupported ma konkretne uzasadnienie. Nie zastępować wymaganej nowej architektury mockiem lub kontrolą dla zielonej tabelki. Zmiana kandydata wymaga jawnej decyzji, nie wielogodzinnego losowania pinów.

Nie dodawać research requirements do Full. Reużyć istniejący silnik; jeśli architektura wymaga komponentu, mieć jedno izolowane przypięte środowisko na ten runtime, nie venv na każde wagi. Moduł korzysta z ograniczonego protokołu generate/cancel/status/reset/state. Artefakty, receipt, komenda rollback/cleanup są częścią L2. Nie usuwać istniejących modeli użytkownika ani oryginalnych adapterów.

Źródła: [RWKV](https://github.com/BlinkDL/RWKV-LM), [G1](https://huggingface.co/BlinkDL/rwkv7-g1), [Huginn](https://huggingface.co/tomg-group-umd/huginn-0125), [HRM-Text](https://huggingface.co/sapientinc/HRM-Text-1B), [Qwen3.5-2B](https://huggingface.co/Qwen/Qwen3.5-2B).
