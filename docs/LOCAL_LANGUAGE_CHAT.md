# Lokalna zmiana: język rozmowy i czat

Stan: gałąź `codex/lab-language-chat-local`, bez publikacji GH/PR.

W ustawieniach eksperymentu wybierz „Język rozmowy modeli”: Polski albo Angielski.
Wybór jest niezależny od języka panelu, zostaje zamrożony w konfiguracji próby
oraz objęty config_hash. Dotyczy systemowych instrukcji, treści scenariusza,
prywatnych informacji, kontynuacji i otoczki przekazywanych wiadomości.
To prośba do modelu o dany język, nie gwarancja jego kompetencji językowych.
Klucze i wartości protokołu JSON pozostają angielskie.

Nazwy trzech scenariuszy panelu są przetłumaczone. Czat rozróżnia A i B po stronie
oraz kolorze dymka; pokazuje nadawcę → odbiorcę, rodzaj wiadomości, odnośnik do
odpowiedzi i czas trwałego wpisu (data, sekundy, milisekundy, lokalna strefa).
Tooltip czasu podaje ISO UTC. Status przekazania pochodzi z delivered_to;
wariant bez komunikacji nie udaje dostarczenia wiadomości drugiemu modelowi.
Treść jest zwykłym tekstem, bez wykonywania HTML.

Historyczne scenariusze, prompty i config_hash benchmarku v1 nie zmieniają się.
Klient API bez communication_language nadal tworzy dokładny legacy v1.
Jawny wybór pl/en tworzy schema_version=2 oraz osobny profil scenariusza
`1-dialogue-pl-1` / `1-dialogue-en-1`. To wersja profilu językowego, nie nowa
rubryka oceny: zamrożony ewaluator v1 nie ocenia tych wariantów jako v1.
Nie przeliczamy historycznych wyników ani nie twierdzimy poprawy jakości.

Historia przywraca zapisany język; stare angielskie próby pokazują Angielski.
Zmiana selektora dotyczy kolejnej próby i nie tłumaczy historycznych wypowiedzi.

## Lokalny odbiór — 2026-10-21

`make check HOST=/home/ubuntu/venom`: 266 Python PASS, coverage 97,27%;
18 frontend PASS, coverage 95,98%; mypy/Ruff/TS/lint i kontrakty hosta PASS.
Dwie istniejące deprecjacje narzędzi pozostają ostrzeżeniami. Zgodność legacy v1
sprawdzona przez dokładny hash; testy języka sprawdzają realne wejścia adaptera
na fixture CPU, bez twierdzenia o językowej jakości odpowiedzi modelu.

Browser na działającym hoście: selektory PL/EN, polskie nazwy trzech scenariuszy,
odtworzenie starej angielskiej próby, dwa rzeczywiste archiwalne wpisy A/B,
czas z milisekundami i ISO, bezpieczna prezentacja stanu przekazania PASS.
Desktop 1366×900 i załadowany mobile 390×844: brak poziomego overflow
(scrollWidth 382), kontrolki mobile x28/y340/326×136. Natychmiastowy pomiar
po resize przed ustaleniem układu hosta nie stanowił PASS; potwierdzenie mobilne
dotyczy ponownej nawigacji przy szerokości390. 0 pageerror; ostrzeżenia wykresów
hosta pozostają. Nie klikano START ani nie powtarzano inferencji.

Wdrożono lokalne API i kopię frontendu modułu; aktywnych prób nie było.
UI działa jako istniejąca venom-rider-ui-release.service, API jako
venom-module-disable-start.service (api-only). Pierwszy restart łączony wykrył
istniejący listener UI, dlatego zachowano sprawny frontend i uruchomiono tylko API.
Bez zmiany modeli, flag pozostałych modułów, globalnego wyboru LLM i robota.
