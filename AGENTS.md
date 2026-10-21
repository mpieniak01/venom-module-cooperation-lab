# Instrukcje dla agentów — Cooperation Lab

- Domyślny język współpracy: polski. Dokumentacja planu jest po polsku.
- To osobne repo opcjonalnego modułu Venoma. Kanoniczny host: /home/ubuntu/venom w Ubuntu-Venom; aplikacja Codex działa na Windows 11.
- Stan bieżący: baza, adaptery, runner i UI gotowe do rzeczywistych eksperymentów. Formalna kwalifikacja GPU C0/L2 PASS; macierz: 30/30 technical completed, 12/12 komunikacji, 30/30 strict-v1 unscorable, accuracy=null. OFF i browser/layout/cancel/SSE/export/Delete PASS. L1–L5, C0 i cleanup follow-up PR #553 scalone; aktualny przypięty host 7401493 zachowuje ABI 1.0.0 z baseline aa2d6124. L5 PR #13 scalony jako 4346a66fd6f2f07629bc2146b2061caa81e1d0f1; lokalne API, ekran i widoczność modułów odebrane na obu main. Kontrole PR PASS; wynik ponowionego main CI jest przypięty w docs/RELEASE_ACCEPTANCE.md. Rzeczywisty ponowny probe legacy chatu nadal HTTP 400 bez treści/done, ale C0 cleanup PASS (busy→available, 0 operacji, ps[]). Legacy adapter to osobny Venom issue #554, nie CHAT PASS ani blocker zakwalifikowanych modeli laboratorium. CodeRabbit rate-limited nie jest pełną recenzją. Pięć odziedziczonych ID Torch pozostaje jawne; patrz docs/RELEASE_ACCEPTANCE.md. Nie przedstawiaj transportu jako dowodu jakości/nauki.
- Zakres i kolejność określa docs/PLAN.md; nie realizuj automatycznie dalszych faz v2. Dataset/prompt/rubric v1 są zamrożone; jawny kontrakt końcowej odpowiedzi v2 wymaga oddzielnego research. Nie zmieniaj parsera v1 retrospektywnie dla poprawienia wyniku.
- Nie kopiuj runtime/Council z core, nie wyłączaj jego polityk i nie zmieniaj globalnego modelu z poziomu sesji modułu.
- Dwie sesje tych samych wag mają oddzielne historie i stany. Ich istnienie nie wymaga dwóch kopii wag w VRAM.
- Brak autostartu eksperymentów, pobrań i dodatkowych silników przy imporcie/startupie modułu.
- Rejestracja produkcyjna i instalacje modeli należą do osobno autoryzowanej realizacji. Dokumentowanie nie uruchamia modeli ani urządzeń.
- Nie zapisuj sekretów, prywatnych promptów, logów urządzeń, modeli ani datasetów w Git. Używaj namespace storage hosta i jawnej retencji.
- Wszelkie LLM wywołania wymagają wspólnego kontraktu zasobów hosta; sam lokalny mutex nie zapewnia izolacji.
- Kod musi przejść make check i kontrakty opcjonalnego modułu. Ruff/mypy/pytest>=90% oraz TS/lint/unit i browser smoke są oddzielnymi dowodami; nie zgłaszaj ich jako PASS przed wykonaniem.
- Dla zmian wyłącznie Markdown: kontrola lokalnych linków i spójności planu; runtime tests/coverage N/A. Implementacja L1 zapewnia osobne bramki kodu; brak skanu lub limit planu nie jest PASS.
- Ten plik nie ogranicza narzędzi przeglądarki/Node/komputera Codex do WSL lub aplikacji Venom.
