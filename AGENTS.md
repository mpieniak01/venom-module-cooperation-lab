# Instrukcje dla agentów — Cooperation Lab

- Domyślny język współpracy: polski. Dokumentacja planu jest po polsku.
- To osobne repo opcjonalnego modułu Venoma. Kanoniczny host: /home/ubuntu/venom w Ubuntu-Venom; aplikacja Codex działa na Windows 11.
- Stan bieżący: baza modułu, adaptery, runner i narzędzia eksperymentów są zaimplementowane lokalnie. Formalna kwalifikacja wspólnego hosta i realny odbiór pozostają pending do receiptów. Nie przedstawiaj specyfikacji, fixture ani mocków jako dowodu rzeczywistej współpracy modeli.
- Zakres i kolejność określa docs/PLAN.md; nie realizuj automatycznie dalszych faz v2.
- Nie kopiuj runtime/Council z core, nie wyłączaj jego polityk i nie zmieniaj globalnego modelu z poziomu sesji modułu.
- Dwie sesje tych samych wag mają oddzielne historie i stany. Ich istnienie nie wymaga dwóch kopii wag w VRAM.
- Brak autostartu eksperymentów, pobrań i dodatkowych silników przy imporcie/startupie modułu.
- Rejestracja produkcyjna i instalacje modeli należą do osobno autoryzowanej realizacji. Dokumentowanie nie uruchamia modeli ani urządzeń.
- Nie zapisuj sekretów, prywatnych promptów, logów urządzeń, modeli ani datasetów w Git. Używaj namespace storage hosta i jawnej retencji.
- Wszelkie LLM wywołania wymagają wspólnego kontraktu zasobów hosta; sam lokalny mutex nie zapewnia izolacji.
- Kod musi przejść make check i kontrakty opcjonalnego modułu. Ruff/mypy/pytest>=90% oraz TS/lint/unit i browser smoke są oddzielnymi dowodami; nie zgłaszaj ich jako PASS przed wykonaniem.
- Dla zmian wyłącznie Markdown: kontrola lokalnych linków i spójności planu; runtime tests/coverage N/A. Implementacja L1 zapewnia osobne bramki kodu; brak skanu lub limit planu nie jest PASS.
- Ten plik nie ogranicza narzędzi przeglądarki/Node/komputera Codex do WSL lub aplikacji Venom.
