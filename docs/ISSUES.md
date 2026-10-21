# Backlog GitHub

[PR planu #1](https://github.com/mpieniak01/venom-module-cooperation-lab/pull/1), [cel MVP #2](https://github.com/mpieniak01/venom-module-cooperation-lab/issues/2).

Numery poniżej identyfikują zakresy planu; ich stan wdrożenia i scalenia podaje
[RELEASE_ACCEPTANCE](RELEASE_ACCEPTANCE.md). Nie są automatycznym potwierdzeniem
zamknięcia odpowiadających im zgłoszeń GitHub.

| ID | Zadanie | Repo implementacji | Opis PR |
| --- | --- | --- | --- |
| L1 | [#3](https://github.com/mpieniak01/venom-module-cooperation-lab/issues/3) | to repo | [Specyfikacja](prs/L1-module-foundation.md) |
| C0 | [#4](https://github.com/mpieniak01/venom-module-cooperation-lab/issues/4) | mpieniak01/Venom | [Specyfikacja](prs/C0-host-runtime-lease.md) |
| L2 | [#5](https://github.com/mpieniak01/venom-module-cooperation-lab/issues/5) | to repo | [Specyfikacja](prs/L2-model-qualification.md) |
| L3 | [#6](https://github.com/mpieniak01/venom-module-cooperation-lab/issues/6) | to repo | [Specyfikacja](prs/L3-session-runner.md) |
| L4 | [#7](https://github.com/mpieniak01/venom-module-cooperation-lab/issues/7) | to repo | [Specyfikacja](prs/L4-operator-workspace.md) |
| L5 | [#8](https://github.com/mpieniak01/venom-module-cooperation-lab/issues/8) | to repo | [Specyfikacja](prs/L5-experiments-acceptance.md) |

Kolejność: L1 i C0 → L2 → L3 → L4 → L5. L1–L5 i C0 są scalone;
[L5 PR #13](https://github.com/mpieniak01/venom-module-cooperation-lab/pull/13)
scalono jako `4346a66`; lokalne wdrożenie na obu main odebrano w API i DOM.
Kontrole PR oraz niezależny review odebranego kodu PASS. Cleanup C0 po HTTP 400
odebrany; legacy chat śledzi osobny [Venom #554](https://github.com/mpieniak01/Venom/issues/554), a nową metodologię
[research #14](https://github.com/mpieniak01/venom-module-cooperation-lab/issues/14). Trening i dalsza rozbudowa są poza MVP.
