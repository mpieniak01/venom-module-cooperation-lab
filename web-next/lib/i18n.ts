export const messages = {
  pl: {
    title:"Laboratorium współpracy",description:"Dwie sesje, jedne wagi. Organizację pracy proponują modele.",
    notReady:"Model nie został jeszcze zakwalifikowany",disabled:"Moduł wyłączony",unavailable:"Połączenie niedostępne",
    refresh:"Odśwież",limits:"Limity zapisu",runs:"Próby",retention:"Retencja (dni)",disk:"Baza (MiB)",
    start:"Rozpocznij eksperyment",stop:"Zatrzymaj",noRuns:"Brak uruchomionych eksperymentów",loading:"Sprawdzanie gotowości",
    model:"Model",scenario:"Scenariusz",mode:"Wariant",turns:"Maks. tur",tokens:"Tokenów na turę",seed:"Seed",
    settings:"Ustawienia eksperymentu",history:"Historia prób",select:"Wybierz próbę",participants:"Uczestnicy",
    dialog:"Wymiana wiadomości",organization:"Propozycje organizacji",noMessages:"Brak wiadomości",noProposals:"Brak propozycji",
    ready:"Gotowe",connected:"Połączono",connecting:"Łączenie",disconnected:"Połączenie przerwane",reconnect:"Połącz ponownie",
    resync:"Odtwarzanie historii",cancelPending:"Zatrzymywanie obliczeń",details:"Konfiguracja i wynik",usage:"Zużycie",
    export:"Eksportuj JSON",remove:"Usuń próbę",confirmRemove:"Potwierdź usunięcie",cancel:"Anuluj",
    runStatus:"Stan obliczeń",connection:"Połączenie",local:"Prywatny kontekst",shared:"Współdzielone, niezmienne wagi",
    unknown:"Nieznane",error:"Błąd",input:"Wejście",output:"Wyjście",charged:"Naliczony budżet",
    single:"Samodzielnie",self_correction:"Samokorekta",no_contact:"Bez komunikacji",dialog_mode:"Dialog bez ról",
    dialog_encouraged:"Dialog z zachętą do współpracy",created:"Utworzono",queued:"W kolejce",preparing:"Przygotowanie",
    running:"Trwa",completed:"Zakończono",failed:"Niepowodzenie",cancelled:"Anulowano",interrupted:"Przerwano",
    waiting:"Oczekiwanie",newRun:"Nowa próba",claimedComplete:"Deklaracja zakończenia; ocenę zapisuje ewaluator."
  },
  en: {
    title:"Cooperation Lab",description:"Two sessions, one set of weights. Models propose how to organize their work.",
    notReady:"No model has been qualified yet",disabled:"Module disabled",unavailable:"Connection unavailable",
    refresh:"Refresh",limits:"Storage limits",runs:"Runs",retention:"Retention (days)",disk:"Database (MiB)",
    start:"Start experiment",stop:"Stop",noRuns:"No experiments have been started",loading:"Checking readiness",
    model:"Model",scenario:"Scenario",mode:"Condition",turns:"Maximum turns",tokens:"Tokens per turn",seed:"Seed",
    settings:"Experiment settings",history:"Run history",select:"Select run",participants:"Participants",
    dialog:"Message exchange",organization:"Organization proposals",noMessages:"No messages",noProposals:"No proposals",
    ready:"Ready",connected:"Connected",connecting:"Connecting",disconnected:"Disconnected",reconnect:"Reconnect",
    resync:"Replaying history",cancelPending:"Stopping computation",details:"Configuration and result",usage:"Usage",
    export:"Export JSON",remove:"Delete run",confirmRemove:"Confirm deletion",cancel:"Cancel",
    runStatus:"Computation",connection:"Connection",local:"Private context",shared:"Shared immutable weights",
    unknown:"Unknown",error:"Error",input:"Input",output:"Output",charged:"Charged budget",
    single:"Single participant",self_correction:"Self correction",no_contact:"No communication",dialog_mode:"Dialog without roles",
    dialog_encouraged:"Dialog with cooperation encouragement",created:"Created",queued:"Queued",preparing:"Preparing",
    running:"Running",completed:"Completed",failed:"Failed",cancelled:"Cancelled",interrupted:"Interrupted",
    waiting:"Waiting",newRun:"New run",claimedComplete:"Completion claim; evaluation is recorded separately."
  },
  de: {
    title:"Kooperationslabor",description:"Zwei Sitzungen, gemeinsame Gewichte. Die Modelle schlagen ihre Arbeitsorganisation vor.",
    notReady:"Noch kein Modell qualifiziert",disabled:"Modul deaktiviert",unavailable:"Verbindung nicht verfügbar",
    refresh:"Aktualisieren",limits:"Speicherlimits",runs:"Versuche",retention:"Aufbewahrung (Tage)",disk:"Datenbank (MiB)",
    start:"Experiment starten",stop:"Stoppen",noRuns:"Keine gestarteten Experimente",loading:"Bereitschaft wird geprüft",
    model:"Modell",scenario:"Szenario",mode:"Bedingung",turns:"Maximale Runden",tokens:"Token pro Runde",seed:"Seed",
    settings:"Versuchseinstellungen",history:"Versuchsverlauf",select:"Versuch wählen",participants:"Teilnehmer",
    dialog:"Nachrichtenaustausch",organization:"Organisationsvorschläge",noMessages:"Keine Nachrichten",noProposals:"Keine Vorschläge",
    ready:"Bereit",connected:"Verbunden",connecting:"Verbindung wird hergestellt",disconnected:"Verbindung unterbrochen",reconnect:"Neu verbinden",
    resync:"Verlauf wird geladen",cancelPending:"Berechnung wird gestoppt",details:"Konfiguration und Ergebnis",usage:"Verbrauch",
    export:"JSON exportieren",remove:"Versuch löschen",confirmRemove:"Löschen bestätigen",cancel:"Abbrechen",
    runStatus:"Berechnung",connection:"Verbindung",local:"Privater Kontext",shared:"Gemeinsame unveränderliche Gewichte",
    unknown:"Unbekannt",error:"Fehler",input:"Eingabe",output:"Ausgabe",charged:"Berechnetes Budget",
    single:"Einzelner Teilnehmer",self_correction:"Selbstkorrektur",no_contact:"Ohne Kommunikation",dialog_mode:"Dialog ohne Rollen",
    dialog_encouraged:"Dialog mit Kooperationsanregung",created:"Erstellt",queued:"Warteschlange",preparing:"Vorbereitung",
    running:"Läuft",completed:"Abgeschlossen",failed:"Fehlgeschlagen",cancelled:"Abgebrochen",interrupted:"Unterbrochen",
    waiting:"Warten",newRun:"Neuer Versuch",claimedComplete:"Abschlussbehauptung; Bewertung wird separat erfasst."
  }
} as const;
export type Language = keyof typeof messages;
export function texts(language: string) { return messages[language as Language] ?? messages.en; }
export function statusLabel(t: ReturnType<typeof texts>, status: string) {
  if (status === "cancelling") return t.cancelPending;
  return (t as Record<string, string>)[status] ?? t.unknown;
}
export function modeLabel(t: ReturnType<typeof texts>, mode: string) { return statusLabel(t, mode === "dialog" ? "dialog_mode" : mode); }
