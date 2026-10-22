# Huginn / HRM-Text / CTM — zgodność stosu, 2026-10-22

Research i odczyt środowiska; bez pobrania wag, instalacji lub inferencji.
Host: RTX 3060 12 GiB, WSL około 11 GiB RAM + 4 GiB swap. Jeden silnik naraz.
Full i istniejący komponent CUDA mają Torch 2.13.0, Transformers 5.17.0,
Accelerate 1.15.0. Import HrmTextConfig i HrmTextForCausalLM w komponencie CUDA
PASS. To potwierdzenie importu, nie działania konkretnego checkpointu.

| Kandydat | Artefakt | Stan lokalny |
|---|---|---|
| tomg-group-umd/huginn-0125 | rev bb6621b65e90b6a4b9b29ef88dc83866d450470c; 4 safetensors, 15645609096 B | Torch/Transformers są; brak adaptera i kwalifikacji własnego kodu Raven |
| sapientinc/HRM-Text-1B | rev 22097cbcecdd1301afe30a19a3ee61b96a9863e5; 1 safetensors, 2365606568 B | Natywna klasa rzeczywiście importuje się; brak adaptera laboratoryjnego |
| SakanaAI/continuous-thought-machines | Checkpointy per zadanie | Nie jest tekstowym modelem chat; osobny runner zadań |

## Huginn

Oficjalny punkt startu to huginn-0125. Checkpointy pośrednie opisują etapy treningu,
nie potwierdzony katalog mniejszych rozmiarów. Używa własnego kodu i
HuginnDynamicCache, a nie stanu RNN RWKV. Kod/config odwołuje się do Transformers
4.44.2; zgodność z naszym 5.17 wymaga próby. Nie obniżać Full globalnie.

Autor zaleca BF16. Szacunek samych wag po konwersji z FP32: około 7–8 GB,
nie całkowity VRAM. KV cache i dwie historie mogą wyczerpać 12 GiB. Num_steps
steruje wewnętrznymi iteracjami; udokumentowano także adaptacyjne zatrzymanie,
kompresję cache i warmstart. Pierwszy test: krótki kontekst, mały limit wyjścia,
8/16 kroków, pomiar obu cache i cleanup. Własny szablon/tokeny stop obowiązkowe.
Źródło: https://huggingface.co/tomg-group-umd/huginn-0125
Kod: https://github.com/seal-rg/recurrent-pretraining

## HRM-Text

Oficjalny 1B ma BF16 i 4096 kontekstu. Wymaga Transformers >=5.9; lokalny 5.17
zawiera klasę i ścieżkę SDPA. Nie trzeba instalować całego repo treningowego
z FlashAttention3/Hydra/vLLM dla pierwszej inferencji natywnym Transformers.

To checkpoint pre-alignment, nie gotowy asystent. PrefixLM wymaga
`token_type_ids=1` na prefiksie. Warunki direct oraz synth,cot muszą być jawne;
nie używać szablonu Gemmy/RWKV. Recurrence H/L to odmienny mechanizm niż
prywatny stan RNN RWKV. Około 2,37 GB wag sugeruje wykonalność na GPU, ale
powtarzane warstwy zwiększają koszt i cache. Zachować domyślne H=2/L=3.
Źródło: https://huggingface.co/sapientinc/HRM-Text-1B

## CTM

Oficjalne zadania obejmują obrazy, labirynty, sortowanie, parity, QAMNIST i RL.
Nie ma tu gotowego odpowiednika tekstowego rozmówcy laboratorium. Dobry pierwszy
zakres: checkpoint labiryntów oraz wizualizacja kroków/synchronizacji, bez treningu.
Autorzy podają środowisko Python 3.12, podczas gdy nasz profil ma 3.14.
W komponencie CUDA brakuje m.in. matplotlib, seaborn, opencv, imageio, sklearn,
umap, gymnasium, minigrid, datasets i autoclip. Pełna lista upstream obejmuje
również narzędzia treningu/analizy — nie instalować wszystkiego automatycznie.
Minimalne importy i checkpoint należy dobrać do jednego zadania.
Źródło: https://github.com/SakanaAI/continuous-thought-machines

## Kolejność

1. HRM-Text: najmniejsza luka stosu; oddzielny adapter PrefixLM/admission/cancel.
2. Huginn: ciekawy eksperyment regulacji compute, większe ryzyko RAM/VRAM/API.
3. CTM: osobny typ zadania i widoku; nie dodawać do listy modeli czatowych.

Dla każdego: przypięta rewizja, audyt kodu modelu, brak autostartu/pobierania,
prywatne konteksty A/B tam, gdzie mają sens, pomiar zasobów i potwierdzony cleanup.
Nie wykonano kwalifikacji runtime ani oceny jakości tych trzech kandydatów.
