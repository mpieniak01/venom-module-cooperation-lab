# Cooperation Lab — instalacja, odbiór i wyłączenie

Kanoniczny host developerski: `/home/ubuntu/venom` w Ubuntu-Venom. Codex działa
na Windows 11; przeglądarka/narzędzia Codex mają swój host. Ten moduł ich nie
uruchamia ani nie przenosi do WSL. Wymagane istniejące Full i zgodny core C0.
Nie tworzyć następnej kopii Full/venv ani nie ładować dwóch engine LLM naraz.

## Przygotowanie przez administratora hosta

1. Sprawdzić czystość/HEAD hosta i osobnego repo modułu oraz PID/cwd istniejącego
   API/UI. Zapisać exact SHA core, modułu, adaptera i deployment w raporcie odbioru.
   Sam SHA checkoutu CLI nie potwierdza, co obsługuje uruchomiony proces.
2. Zainstalować sam pakiet modułu w **tym samym istniejącym interpreterze**, który
   uruchamia API, bez doinstalowywania zależności/ML. Przykład kanonicznego hosta:

   ```sh
   /home/ubuntu/venom/.venv/bin/python -m pip install --no-deps --no-build-isolation -e /home/ubuntu/venom/modules/venom-module-cooperation-lab
   /home/ubuntu/venom/.venv/bin/python -I -c "import venom_module_cooperation_lab.adapters.rwkv_worker"
   ```

   Editable jest wariantem developerskim; wydanie może instalować przypięty wheel
   tego samego pakietu. Oba wymagają zgodnych istniejących zależności hosta.
   Sam manifest lub import działający dzięki cwd/sys.path procesu API **nie
   wystarcza**: multiprocessing spawn importuje target w nowym interpreterze.
   Błąd ModuleNotFoundError przed worker_main kończy IPC/worker_protocol_error
   bez inferencji; nie należy maskować go globalnym PYTHONPATH ani luzować C0.
   Rejestrację `module.json` w istniejącym `API_OPTIONAL_MODULES` wykonać osobno,
   bez kopiowania cudzych plików .env. Manifest: cooperation_lab, ABI 1.0.0.
3. Administrator włącza `FEATURE_COOPERATION_LAB=true`,
   `NEXT_PUBLIC_FEATURE_COOPERATION_LAB=true` i `RUNTIME_ADMISSION_ENABLED=true`
   przed startem hosta, pojedynczy wspierany worker API. Nie obchodzić host policy.
4. Sprawdzić jawne modele/specs. Nowy RWKV przygotowuje się oddzielnym jawnym
   provisionerem opisanym w [L2](RWKV_L2.md). Nigdy przy startupie/API. Qwen musi
   już istnieć w Ollama, z właściwym digest/template/version; brak modelu nie
   uruchamia pull. Mały overlay certifi/filelock pozostaje poza pakietami Full.
5. Wykonać formalną kwalifikację C0/adaptera w przydzielonym pojedynczym slocie
   GPU. Kwalifikacja musi mieć tożsamość artefaktu, tokenizer/template/runtime,
   device/precision, load/gen/cancel/reset/quiescence. `qualified=false`/not_ready
   jest poprawne do odbioru, nie wolno wpisywać pozornego PASS ręcznie.
6. Sprawdzić `/cooperation-lab` oraz same-origin `/api/v1/cooperation-lab/health` i
   `/capabilities`. HTTP 200 strony głównej nie potwierdza działania modułu.

## Wdrożenie aktualizacji frontendu modułu

Host nie importuje frontendu modułu bezpośrednio z aktualizowanego repozytorium.
`modules/venom-module-cooperation-lab/web-next` jest źródłem; działający frontend
używa przygotowanej **kopii** pod
`web-next/optional-modules/venom-module-cooperation-lab`. Sam fast-forward lub
cherry-pick modułu nie potwierdza aktualizacji tej kopii ani kodu w przeglądarce.

Po aktualizacji kanonicznych źródeł modułu, **przed kontrolowanym restartem UI**,
uruchomić oficjalny helper Venoma w terminalu projektu Ubuntu-Venom:

```sh
cd /home/ubuntu/venom/web-next
node scripts/prepare-optional-module-node-paths.mjs
diff -qr ../modules/venom-module-cooperation-lab/web-next optional-modules/venom-module-cooperation-lab
```

Sprawdzić wynik helpera dla synchronizacji mirrorów oraz zgodność źródeł i kopii
(`diff` bez różnic). Helper czyta kanoniczny katalog `modules`; commit pozostający
wyłącznie w innym worktree nie trafi przez to do wdrożenia. Kopii nie edytować
jako źródła poprawki — następna synchronizacja ją odtworzy.

Dopiero potem odtworzyć właściwy proces UI zgodnie z profilem hosta i sprawdzić
rzeczywisty DOM/zachowanie poprawionego elementu. Sam aktualny SHA źródeł lub
HTTP 200 nie potwierdza świeżego mirrora. Rozbieżność source/mirror wystąpiła przy
odbiorze L4 i ustąpiła po wykonaniu powyższego helpera.

To etap budowania aplikacji Venom, nie konfiguracja narzędzi Codex. Przeglądarka,
komputer i Node Codex nadal korzystają ze swojego środowiska Windows 11.

## Operator i mała próba

Wybrać qualified model/scenę/tryb, obejrzeć efektywne parametry, uruchomić jeden
run. UI pokazuje osobne A/B, trwały seq, wiadomości, usage i stan połączenia.
STOP jest idempotentny; cancelling trwa do faktycznego końca obliczeń. Reconnect
odtwarza journal, nie wznawia inferencji. Błąd/niepewny cleanup blokuje dalszy start.
Laboratorium nie steruje Riderem i nie zmienia selekcji globalnego modelu.

Jawne planowanie CLI nie wykonuje HTTP ani inferencji:

```sh
python scripts/run_acceptance.py
python scripts/run_acceptance.py --matrix
```

Po formalnej kwalifikacji i uzgodnieniu zasobu, istniejący host:

```sh
python scripts/run_acceptance.py --execute --model rwkv7-g1d-0.4b \
  --turns 2 --tokens 32 --output-dir /absolute/private/lab-acceptance
```

Domyślny limit to dwie próby, timeout do180s na próbę. Pełna macierz wymaga jawnego
`--matrix --max-runs 30`; nie jest obowiązkowym benchmarkiem wydania. Wyniki są
niezależnie oceniane według [EXPERIMENTS](EXPERIMENTS.md). CLI zapisuje nowy lokalny
katalog700/pliki600, klucze retry przed startem i zredagowane wyniki; nie zapisuje
surowych promptów/eksportów. Po awarii użyć zapisanego klucza/run_id do odczytu i
STOP; nie uruchamiać od początku z nowym kluczem w ciemno.

Tryb offline dla własnego exportu (bez sieci/modelu):

```sh
python scripts/run_acceptance.py --evaluate /absolute/private/export.json
```

Raport odbioru musi oddzielać wykonane testy fixture od realnych odpowiedzi,
uwzględniać exact SHA, runtime/admission receipt, metryki i ograniczenia. Ta
implementacja nie deklaruje poprawy jakości ani nauki. Browser smoke i właściwe
CI/review/Snyk/Sonar są oddzielnymi dowodami; blocker/limit nigdy nie jest PASS.

## Dane, eksport i retencja

SQLite jest pod namespacem hosta `resolve_module_data_root`, z bazą i WAL/SHM.
Limity v1: 100 runów, 14dni, 512MiB łącznie, 2MiB/run, 64KiB/zdarzenie,
minimum64MiB wolnego; eksport jednego runu do4MiB. Tylko zakończone rekordy mogą
być usuwane. Brak miejsca daje jawny błąd; nie kasujemy aktywnego runu, modeli,
adapterów ani danych innych modułów. Storage full wymaga osobnego recovery z
zapasem na WAL/checkpoint; nie wykonuj VACUUM przy zapchanym dysku.

Eksport i Delete w UI/API respektują uprawnienia i host mutation guard. CLI
`--delete-after` usuwa wyłącznie rekordy utworzone w tej konkretnej próbie, po
terminalnym journal/quiescence; nie dotyka cudzej historii. Domyślnie niczego nie
usuwa. Wyniki CLI poza bazą nie podlegają retencji hosta — po przeglądzie ręcznie
usunąć wskazany własny katalog receiptów. Nigdy nie archiwizować go w Git, jeśli
zawiera dane prywatne. Publiczny dataset metadata jest wyraźnie syntetyczny.

## OFF, restart i rollback

Najpierw STOP i potwierdzenie quiescence; nie utożsamiać zamknięcia karty/socketu
z końcem GPU. Wyłączenie backend flagi i frontend flagi oraz kontrolowany restart
hosta usuwa moduł z pracy/menu. OFF nie rezerwuje runtime, nie pobiera modeli i
nie uruchamia pollingu/zapisów. Restart przerwane runy oznacza interrupted, bez
auto-resume; historia zostaje do jawnego eksportu/usunięcia. Quarantine wymaga
zaufanego potwierdzenia końca procesu/obliczeń, nie resetu statusu w JSON.

Rollback: zachować dane i przypięte artefakty, wyłączyć moduł, wrócić do ostatniej
sprawdzonej **zgodnej pary** SHA core/module wskazanej w receipt, wykonać kontrolny
restart i smoke core. Nie przywracać starszego C0 przy aktywnym workerze. Nie
kasować modeli ani nie zmieniać globalnego wyboru operatora. Schemat SQLite v1
nie wymaga niszczącego downgrade; przed odmienną migracją osobny backup/plan.

## Stan obecnego odbioru

Formalna kwalifikacja C0/L2 na GPU PASS. Realna macierz 2 modeli × 3 scenariuszy × 5
trybów: 30/30 technical completed, 12/12 komunikacji, 30/30 strict-v1 unscorable;
accuracy pozostaje nieznane. Realny OFF API/danych PASS: route absent, hash bazy
bez zmian, Rider obecny, health 200 i Ollama ps[]. Browser START/RWKV A/B,
reload/replay/SSE przez proxy, STOP/quiescence, stabilny układ desktop/mobile
oraz PL/EN/DE odebrane. Szczegóły: [RELEASE_ACCEPTANCE](RELEASE_ACCEPTANCE.md).

Po STOP zasób available/active_operations=0 i ps[]; nie wykonano następnie zwykłej
inferencji chatu. Crash/retencja/quotas/OOM pozostają testami fixture. L4 PR #12 czeka
na kontrole, L5 na publikację/recenzję/scalenie; finalne SHA/deployment i bramki
wydania potwierdza koordynator. Nie archiwizować całego zadania przed scaleniem
L5; nie poprawiać parsera v1 dla pozornej jakości.
