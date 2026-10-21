# Przegląd luk planu

Stan 2026-10-21: review specyfikacji i istniejących kontraktów hosta, nie test runtime.

| Ryzyko/luka | Obsługa w planie | Właściciel i dowód |
| --- | --- | --- |
| Dwa uczestniki tylko z nazwy | Osobne historie/stany, jawne współdzielenie niezmiennych wag | L2/L3: nieprzeciekanie A/B i reset |
| Sztywny workflow udaje samoorganizację | Neutralne A/B, encouragement osobno, propozycje z modelu | L5: zobowiązania i faktyczne wykonanie |
| Zwykły model zamiast celu badawczego | Kontrola + obowiązkowy nowy kandydat o wyróżniającej właściwości | L2/L5: realny receipt; failure nie zastępuje mock |
| Lock tylko w module | C0 mapuje wszystkich konsumentów; publiczny admission | C0: współbieżne chat/benchmark/lab/switch |
| Cancel HTTP udaje koniec GPU | Cancelling do końca inferencji; late worker trzyma ownership/quarantine | C0/L2/L3: late completion i prawdziwy adapter |
| Retry/dwie karty generują duplikaty | Idempotency key, max1 run, trwały seq i dedup | L3/L4 |
| Stare wyniki ponownie zapchają dysk | Limit DB/runu, WAL/SHM w budżecie, retencja zakończonych, bounded export | L1/L3/L5 |
| Research requirements psują Full | Wersjonowany protokół i izolowany komponent tylko gdy potrzebny | L2; brak zmiany pinów core |
| Moduł OFF lub brak repo blokuje core | Manifest quarantine, flagi, bounded async lifecycle, brak side effects | L1/host contracts |
| Sekrety/prompty wyciekają lub model wskazuje URL | Dane lokalne, guard/policy, endpoint IDs z hosta, brak raw danych w Git | L1/L2/L3 |
| SSE buforowane przez proxy | Realny same-origin smoke, catch-up i jawny resync | L4; generyczny fix hosta gdy konieczny |
| Konsensus uznany za poprawność | Ground truth/rubryka, kontrole no-contact i self-correction | L5 |
| Brak wersji/rollbacku i auto-resume po restarcie | Receipt i schema, exact SHA i tagi, restart interrupted | Wszystkie PR/L5 |
| Lokalny mutex udaje ochronę wielu procesów | C0 jawnie określa wspieraną topologię, pozostałym odmawia startu | C0 |
| Trening przypadkiem wchodzi do MVP | Jawnie osobny późniejszy zakres po wykazaniu braku kompetencji | PLAN |

## Jawne decyzje wejściowe

1. C0: pełna lista konsumentów, sposób admission/quiescence i rzeczywista topologia. Nie ma jeszcze potwierdzenia, że obecny benchmark guard wystarczy.
2. L1: zamrożone limity retencji/schema/host ABI, projekty skanerów i reguły review nowego repo. Obecnie żaden nowy projekt Sonar/Snyk ani code CI nie jest skonfigurowany.
3. L2: exact checkpoint/revision/hash/licencja, adapter i efektywny Python/CUDA, budżet dysku/VRAM i sposób anulowania. Żadnych pobrań w zadaniu planowania.
4. L5: scenariusze/encouragement/rubryka zamrożone przed pomiarami, bez zmiany po niekorzystnym wyniku.

Luki mają właścicieli i testy. Nie obiecujemy braku wszelkich ryzyk ani tego, że badania wykażą przewagę współpracy. Powyższe bramki nie mogą zostać cicho pominięte podczas implementacji.

## Wynik przeglądu dokumentacji

Sprawdzono kompletność sześciu zakresów i acykliczność zależności. Uzupełniono wykrytą brakującą jawną sekcję wyłączeń L5; ponowna kontrola przeszła. Lokalne linki sprawdzone. To własny przegląd planu, nie niezależna recenzja kodu. Testy runtime/coverage N/A; brak implementacji i instalacji modeli.
