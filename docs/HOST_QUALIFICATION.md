# L2 — rzeczywista kwalifikacja hosta

Odbiór techniczny 2026-10-21 wykonano na RTX 3060 12 GiB, z Full Python 3.14.8,
C0 `711d70b33ca4b18c3711907e3bb72ee3fdbe7433` i modułem
`becd08b` (identyczne źródła adaptera jak wydanie L2).
API hosta było zatrzymane na czas kwalifikacji; Ollama nie miała załadowanego
modelu. Po próbie przywrócono kanoniczne API/UI i potwierdzono HTTP 200.

| Model | Rzeczywiste wykonanie | Sesje i reset | Cancel oraz cleanup | Czas całej próby |
|---|---|---|---|---:|
| RWKV7 G1d 0.4B | CUDA FP16, rwkv 0.8.32, Torch 2.13.0+cu130, certifi 2026.10.19, filelock 4.2.1 | A/B/A, niezależne fingerprinty tensorów; reset A zachowuje B; brak współdzielonych buforów stanu | anulowanie aktywnego wątku 0,115 s; rzeczywisty koniec procesu; lease zwolniony | 11,42 s |
| Qwen3 4B Q4_K_M | Ollama 0.40.6; wykonanie GPU potwierdzone size_vram, digest i size rzeczywistego runnera | prywatne pełne historie A/B/A; reset A zachowuje B | anulowanie aktywnej odpowiedzi 2,64 s; końcowy done i puste /api/ps; lease zwolniony | 43,84 s |

Każdy model udzielił trzech niepustych odpowiedzi przy limicie 32 nowych tokenów.
C0 blokował równoległy host_chat przez cały okres własności. Po obu próbach
rejestr był available. Zamknięcie HTTP nie było dowodem zakończenia obliczeń.
Model Qwen wykorzystał limit tokenów na rozwlekłą odpowiedź mimo think=false;
32 tokeny nie wystarczają do oceny jakości jego rozumowania. RWKV odpowiedział
poprawnie na proste dodawanie i pytanie o stolicę, lecz kontynuacja nie potwierdziła
przypomnienia prywatnego kodu. Izolację stanu potwierdzono pomiarami, a nie tą
odpowiedzią. Ollama nie udostępnia fingerprintów ukrytego KV; tego nie deklarujemy.

To kwalifikacja adapterów i kontraktu zasobów, nie wynik współpracy modeli.
Wynik badań komunikacji, organizacji i jakości należy do oddzielnego L5.
Prywatne, pełne receipts pozostają pod docs_dev/_reports/cooperation-lab-implementation/L2
w hoście; nie zawierają danych urządzenia ani prywatnych promptów użytkownika.

## Bezpieczeństwo

Końcowy rzeczywisty skan efektywnego union Full + izolowany RWKV objął 35 zależności.
Pozostało pięć wcześniej ujawnionych zgłoszeń Torch (1 High, 4 Medium), zgodnych
z przyjętym audytem Full PR 546: SNYK-PYTHON-TORCH-15746467,
SNYK-PYTHON-TORCH-10332643, SNYK-PYTHON-TORCH-10337825,
SNYK-PYTHON-TORCH-10337826, SNYK-PYTHON-TORCH-10337834.
Wynik ma status FINDINGS, nie zero podatności. Dziewięć nowych zgłoszeń
certifi/filelock usunięto przez mały, przypięty i zweryfikowany overlay komponentu.
Nie zmieniono Full i nie dodano ignorowania Snyk.
