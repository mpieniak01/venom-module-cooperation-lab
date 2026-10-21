# Operator w rozmowie i głuchy telefon — lokalny zakres

Status: lokalna gałąź `codex/lab-language-chat-local`, bez publikacji GH.

## Obsługa

W ustawieniach wybierz wariant **Rozmowa z operatorem** albo **Głuchy telefon**.
Scenariusz przełącza się na rozmowę operatora: nie dodajemy prywatnych zadań
z benchmarku. Wybierz język PL/EN i rozpocznij próbę. Po przygotowaniu modelu
wpisz wiadomość pod czatem i wyślij. Kolejny wpis można przygotować podczas
odpowiedzi; wysyłka jest dostępna po zakończeniu odpowiedzi obu modeli.

- Rozmowa: operator przekazuje ten sam wpis do prywatnych kontekstów A i B.
  Oba modele odpowiadają kolejno, bez równoległego ładowania wag.
- Głuchy telefon: oryginał trafia wyłącznie do A; host przekazuje odpowiedź A
  do B, a odpowiedź B do operatora. Kontekst B nigdy nie otrzymuje oryginału
  ani poprzednich oryginałów. Pełny czat dla człowieka pokazuje każdy etap.
- STOP działa również podczas oczekiwania na wpis. Nie ma automatycznego
  wznawiania po przeładowaniu backendu: przerwana sesja pozostaje przerwana.
- Maksymalnie 2000 znaków na wpis. Jeden wpis zużywa dwie tury generowania;
  parzysty limit 2–8 tur oznacza 1–4 wpisy. Dotychczasowy limit 360 sekund
  obejmuje przygotowanie, oczekiwanie i generowanie; kolejne wpisy go nie
  przedłużają. Obowiązują także dotychczasowe limity kontekstu, tokenów i dysku.

## Kontrakt i historia

`POST /api/v1/cooperation-lab/runs/{id}/messages`, body `{content: string}`,
obowiązkowy `Idempotency-Key`. Nadawcą zawsze jest operator — klient nie może
podać nadawcy, odbiorcy, modelu ani endpointu silnika. Ten sam klucz i treść
nie tworzą następnej wiadomości ani generacji; inna treść z tym samym kluczem
jest konfliktem. Wysyłka w trakcie odpowiedzi lub po zakończeniu jest odrzucana.

Wpis jest utrwalany jako zdarzenie `message` przed potwierdzeniem API.
`operator` w SSE sygnalizuje oczekiwanie/generowanie; replay po ponownym otwarciu
odtwarza ten stan z dziennika. Wiadomości operatora mają czas, nadawcę, trasę
przekazania i własny kolor. Eksport i usuwanie obejmują całą rozmowę. Błąd sieci
zachowuje wpis i klucz ponowienia w bieżącym kliencie. Nie przechowujemy treści
formularza w localStorage.

Nowe tryby mają konfigurację v3 i osobne schedulery `operator-rounds-v1` /
`operator-relay-v1`, z trzema uczestnikami (dwa konteksty modeli i człowiek).
Zamrożone prompty, hashe i ewaluacja benchmarku v1 pozostają bez zmian.
Rozmowy interaktywne nie są wynikiem macierzy benchmarkowej v1.

## Weryfikacja

Testy CPU używają ograniczonego adaptera testowego, bez kwalifikowania jakości:
przekazanie do obu kontekstów, izolacja oryginału od B w głuchym telefonie,
dwie rundy, trwały replay/eksport, retry/idempotencja, odrzucenie nadawcy klienta,
STOP, termin sesji, końcowe zwolnienie zasobu i niezmienność dawnych trybów.
Test React sprawdza formularz, zachowanie wpisu po błędzie transportu, ponowienie
z tym samym kluczem, wiadomości A/B i dostępność STOP.

Wykonano również dwie rzeczywiste próby z przeglądarki, po 2 tury / 64 tokeny,
z już zakwalifikowanym RWKV 0.4B (łącznie 4 generacje). Obie próby completed,
trzy zapisane wiadomości w każdej, prawidłowe trasy Operator→A/B i Operator→A→B,
końcowe zwolnienie zasobu. Model w tej małej próbie głównie powtarzał wpis;
nie przedstawiamy tego jako dowodu jakości opowiadania lub współpracy.
Na desktopie pole wpisu pozostaje pod wewnętrznie przewijanym czatem.

Końcowy odbiór: 298 testów Python PASS (pokrycie 97,43%), 22 testy frontendowe
PASS, Ruff/mypy/TypeScript/lint/kontrakty PASS. Dwa istniejące ostrzeżenia
pytest pozostają bez zmian. Browser 1366×900 i 390×844: odtworzone trzy
wiadomości po reload, dostępny formularz (na telefonie po przewinięciu części
roboczej), stabilna grupa START/STOP, bez błędów konsoli podczas odbioru układu.
Końcowy host runtime: available, active_operations=0.
