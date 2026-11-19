# real-fast-filmlab

**Version 26.11.3** · [English](README.en.md)

> Wandelt Kamera-RAW-Scans von Filmnegativen (Farbe und Schwarzweiß) automatisch in DNG-, TIFF- und JPEG-Positive um.

[![CI](https://github.com/jcmx9/real-fast-filmlab/actions/workflows/ci.yml/badge.svg)](https://github.com/jcmx9/real-fast-filmlab/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

## Update

Auf die neueste Version bringen: denselben Befehl wie bei der Installation ausführen. macOS und Linux (Terminal):

```bash
curl -LsSf https://raw.githubusercontent.com/jcmx9/real-fast-filmlab/main/install.sh | sh
```

Windows (PowerShell):

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/jcmx9/real-fast-filmlab/main/install.ps1 | iex"
```

Einstellungen, Ordner und Bilder bleiben erhalten; die Schalter in der Konfiguration bleiben, wie sie sind (ein Update ohne Option schaltet nichts um, siehe [Installer-Optionen](#installer-optionen)). Die Konfiguration bekommt nur Schlüssel dazu, die ihr fehlen. Das Programm aktualisiert sich nie selbst; mit `update_check = true` weist es auf eine neue Version hin (siehe [Hinweis auf neue Versionen](#hinweis-auf-neue-versionen)). Manuell mit uv: siehe [Für Fortgeschrittene](#für-fortgeschrittene-manuell-mit-uv).

Während das Programm ersetzt wird, ist der Hintergrunddienst angehalten; danach läuft er wieder, auch wenn das Update scheitert oder abgebrochen wird (dann mit der bisherigen Version). Wandelt das Programm gerade außerhalb des Dienstes um (zum Beispiel über „Negative entwickeln“ oder `rffilmlab` im Terminal), bricht das Update mit dem Hinweis „Gerade läuft eine Verarbeitung (zum Beispiel „Negative entwickeln“). Sie wird nicht unterbrochen – bitte warten, bis sie fertig ist, und das Update dann erneut starten.“ ab und ändert nichts.

## Grundsätze

- **Vollautomatisch.** RAW-Dateien in einen Ordner legen, fertige Bilder bekommen. Keine Bedienoberfläche, und für den täglichen Gebrauch sind keine Einstellungen nötig; die Konfiguration wird einmal geschrieben (drei Ordner, bei Bedarf die Ausrichtung).
- **Nachvollziehbar und transparent.** Jede Entscheidung folgt festen, dokumentierten Regeln und Schwellwerten; alle sind unten beschrieben, mit den Namen der Konstanten im Code. Jede Ausgabedatei trägt eine Zeile, wie sie verarbeitet wurde (Farbe/SW, Filmbasis, Rollen-Fallback, Zuschnitt).
- **Deterministisch.** Dieselben RAW-Dateien im selben Lauf, dieselbe Konfiguration und dieselbe Programmversion ergeben auf demselben Betriebssystem bitgleiche DNG-, TIFF- und JPEG-Dateien (geprüft an echten Dateien, inklusive EXIF-Übernahme). Der Installer installiert zu jeder Programmversion genau die Bibliotheksversionen aus `constraints.txt` (aus `uv.lock` erzeugt, z. B. LibRaw 0.22 über rawpy). Hinweis: Innerhalb eines Laufs beeinflussen sich Bilder desselben Films gegenseitig (Rollen-Kontext); das Ergebnis eines Bildes hängt also auch davon ab, welche Bilder mit ihm zusammen verarbeitet wurden.
- **Weiß- und Schwarzpunkt je Bild.** Jedes Bild wird auf seinen eigenen Weißpunkt (99,5-%-Perzentil der Dichte im inneren Fenster) und Schwarzpunkt (0,5-%-Perzentil der Luminanz dort) normiert. Das ist eine bewusste Normierung, die nur das Programm leisten kann, weil es jedes Bild misst: Helles und dunkles Detail eines Bildes reichen damit über den ganzen Tonumfang. Ein absichtlich dunkles oder kontrastarmes Motiv (Nacht, Nebel) wird dadurch ebenfalls auf den vollen Umfang gespreizt. Die Bilder eines Films teilen sich Weiß- und Schwarzpunkt nicht. Darüber hinaus gibt es keine Belichtungskorrektur.
- **Keine KI.** Keine neuronalen Netze, keine trainierten Modelle, kein maschinelles Lernen, keine Cloud. Nur klassische Bildverarbeitung (Logarithmen, Perzentile, Morphologie, Konturen, Drehung) mit festen Zahlen.
- **Sicher für die Originale.** RAW-Dateien werden nur gelesen und danach ins Archiv verschoben. Vorhandene Ausgaben werden nie überschrieben. Jede Datei wird zuerst als temporäre Datei geschrieben und erst umbenannt, wenn sie vollständig ist; das gilt auch für das Verschieben ins Archiv auf ein anderes Laufwerk. Ist ein Ordner nicht erreichbar, voll oder nicht beschreibbar, bleiben die RAW-Dateien unverändert in `Negative/`.

## Voraussetzungen

- macOS, Windows 10/11 oder Linux und eine Internetverbindung für die Installation. Keine Administratorrechte nötig.
- Alles Weitere richtet der Installer ein (siehe unten). Nur für die manuelle Installation: [uv](https://docs.astral.sh/uv/) (installiert selbst ein passendes Python ≥ 3.12), git und [exiftool](https://exiftool.org/) (empfohlen, übernimmt die Kameradaten): `brew install exiftool` (macOS), `winget install OliverBetz.ExifTool` (Windows) oder der Paketmanager der Distribution (Linux). Ohne exiftool funktioniert alles, die Ausgaben enthalten dann nur keine Kameradaten.
- Nur Linux: Perl für exiftool (meist vorhanden) und für Mitteilungen `notify-send` (z. B. Paket `libnotify-bin` unter Debian/Ubuntu)

## Installation

Ein Befehl richtet alles ein. macOS und Linux (Terminal):

```bash
curl -LsSf https://raw.githubusercontent.com/jcmx9/real-fast-filmlab/main/install.sh | sh
```

Windows (PowerShell):

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/jcmx9/real-fast-filmlab/main/install.ps1 | iex"
```

**Update:** denselben Befehl noch einmal ausführen (siehe [Update](#update)).

Der Installer

1. richtet [uv](https://docs.astral.sh/uv/) ein, falls es fehlt (uv bringt sein eigenes Python mit),
2. installiert real-fast-filmlab in der zum Installer gehörenden Version, mit den dafür festgelegten Bibliotheksversionen (`constraints.txt` dieser Version),
3. legt im Bilder-Ordner des Benutzers (macOS und Linux `~/Pictures`, Windows „Bilder“) die Ordner `rffilmlab/Negative`, `Fotos` und `Archiv` an und schreibt die vollständige Konfiguration: jeden Schlüssel mit seinem Wert und einem kurzen Kommentar, alle Schalter auf `true`. Gibt es schon eine Konfiguration, gelten ihre Ordner und Werte; sie bekommt nur fehlende Schlüssel dazu, jeweils mit dem Wert, der bisher galt (ein fehlendes `service` mit dem aktuellen Zustand: Dienst eingerichtet – `true`, sonst `false`). Als Option angegebene Schalter werden auf `false` gesetzt (siehe [Installer-Optionen](#installer-optionen)),
4. richtet den Hintergrunddienst nach dem Schalter `service` ein: `true` richtet ihn ein und startet ihn, `false` entfernt einen vorhandenen,
5. legt die Verknüpfungen „Negative“ und „Fotos“ auf den Schreibtisch (gleichnamige eigene Verknüpfungen bleiben unberührt),
6. legt das Programm „Negative entwickeln“ an: macOS im Ordner „Programme“ des Benutzers (`~/Applications`), Windows im Startmenü, Linux im Anwendungsmenü (`~/.local/share/applications`); ein gleichnamiges eigenes Programm bleibt unberührt,
7. richtet zuletzt exiftool ein, falls es fehlt (macOS mit Homebrew über `brew`, sonst das offizielle Paket von exiftool.org mit geprüfter Prüfsumme im Programmdatenordner; unter Linux nur, wenn Perl vorhanden ist). Das dauert meist höchstens etwa eine Minute. Ist der Server nicht erreichbar, gibt der Installer nach etwa 20 Sekunden auf (Verbindungsaufbau höchstens 10 Sekunden, eine Wiederholung; eine abgelehnte Verbindung sofort). Mit curl dauert ein Download einschließlich einer Wiederholung höchstens etwa 2 Minuten, das exiftool-Paket höchstens etwa 10 Minuten; scheitert es, wird es einmal vom Spiegelserver geladen (wieder höchstens etwa 10 Minuten). Unter Windows bricht ein Download ab, wenn der Server 30 Sekunden lang nicht antwortet (keine Wiederholung); das exiftool-Paket hat höchstens 10 Minuten und wird bei einem Fehler einmal vom Spiegelserver geladen. Ohne curl, mit wget, gibt es keine Gesamtgrenze: Ein Download bricht ab, sobald 10 Sekunden lang keine Daten kommen, und wird einmal wiederholt. Die Installation über Homebrew hat keine Zeitgrenze. Klappt es nicht, erscheint ein Hinweis, und alles andere ist trotzdem eingerichtet,
8. zeigt Version, Dienststatus und wo die Ordner liegen. Ließen sich die Einstellungen nicht einrichten oder der Dienst nicht starten, steht dort statt „Fertig!“ eine Zeile „Nicht fertig: …“ mit dem, was fehlt, und der Installer endet mit einem Fehler (Exit-Code 1); das Programm selbst ist dann installiert. Wird `rffilmlab` danach im Terminal nicht gefunden, ein neues Terminalfenster öffnen.

Ein Update hält nur den Hintergrunddienst an und startet ihn danach wieder; läuft gerade eine Verarbeitung über „Negative entwickeln“, wird sie nicht unterbrochen, sondern das Update bricht mit einem Hinweis ab, ändert nichts und kann danach wiederholt werden.

Danach genügt es, Scans in den Ordner „Negative“ zu legen; die Bilder erscheinen automatisch in „Fotos“. Wer nicht warten will, startet „Negative entwickeln“.

### Installer-Optionen

Jede Option setzt einen Schalter in der Konfiguration auf `false`:

| macOS, Linux | Windows | Schalter | Wirkung |
|--------------|---------|----------|---------|
| `--ohne-dng` | `-OhneDng` | `dng = false` | keine DNG-Dateien |
| `--ohne-tiff` | `-OhneTiff` | `tiff = false` | keine TIFF-Dateien |
| `--ohne-kontaktabzug` | `-OhneKontaktabzug` | `contact_sheet = false` | kein Kontaktabzug nach einem Lauf |
| `--ohne-dienst` | `-OhneDienst` | `service = false` | kein Hintergrunddienst (ein vorhandener wird entfernt); die Verarbeitung startet dann nur über „Negative entwickeln“ |

Genau so gilt es:

- Ein Lauf des Installers ändert nur die Schalter, die als Option angegeben sind. Alle anderen behalten den Wert, der in der Konfiguration steht – auch bei einem Update ohne Option.
- Eine Option schaltet nur aus. Eingeschaltet wird ein Schalter, indem man in der Konfigurationsdatei `false` durch `true` ersetzt (Ort siehe [Konfiguration](#ort-der-konfigurationsdatei)). Bei `service` richtet der nächste Lauf (Programm „Negative entwickeln“, `rffilmlab run` oder der Installer) den Dienst dann wieder ein.
- Optionen lassen sich kombinieren. JPEG wird immer geschrieben.

Beispiel ohne Dienst und ohne TIFF, macOS und Linux:

```bash
curl -LsSf https://raw.githubusercontent.com/jcmx9/real-fast-filmlab/main/install.sh | sh -s -- --ohne-dienst --ohne-tiff
```

Windows (PowerShell):

```powershell
powershell -ExecutionPolicy ByPass -c "& ([scriptblock]::Create((irm https://raw.githubusercontent.com/jcmx9/real-fast-filmlab/main/install.ps1))) -OhneDienst -OhneTiff"
```

### Für Fortgeschrittene: manuell mit uv

uv installieren (einmalig), macOS und Linux:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Windows (PowerShell):

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

real-fast-filmlab installieren (braucht git):

```bash
uv tool install git+https://github.com/jcmx9/real-fast-filmlab.git
```

Ohne `--constraints` löst uv dabei die jeweils neuesten passenden Bibliotheken auf; dieselben Versionen wie der Installer ergibt `--constraints constraints.txt` mit der Datei aus dem Repository.

Update auf die neueste Version (die Konfiguration bleibt erhalten; `config init` danach ergänzt fehlende Schlüssel):

```bash
uv tool install --force git+https://github.com/jcmx9/real-fast-filmlab.git
```

Ordner und vollständige Konfiguration anlegen (eine vorhandene bekommt nur fehlende Schlüssel; `--off SCHALTER` setzt einen Schalter auf `false`) und den Dienst starten:

```bash
rffilmlab config init --negative ~/Pictures/rffilmlab/Negative --photos ~/Pictures/rffilmlab/Fotos --archive ~/Pictures/rffilmlab/Archiv
```

```bash
rffilmlab service install
```

## Deinstallation

macOS und Linux:

```bash
curl -LsSf https://raw.githubusercontent.com/jcmx9/real-fast-filmlab/main/install.sh | sh -s -- --uninstall
```

Windows (PowerShell):

```powershell
powershell -ExecutionPolicy ByPass -c "& ([scriptblock]::Create((irm https://raw.githubusercontent.com/jcmx9/real-fast-filmlab/main/install.ps1))) -Uninstall"
```

Entfernt werden der Hintergrunddienst, das Programm, „Negative entwickeln“ und die vom Installer angelegten Verknüpfungen auf dem Schreibtisch (nur, wenn sie noch auf die Ordner zeigen); exiftool und uv nur, wenn der Installer sie selbst eingerichtet hat (vermerkt in der Datei `installer-state` im Programmdatenordner). Das von uv verwaltete Python und der Tool-Ordner von uv werden nur entfernt, wenn der Installer uv selbst eingerichtet hat und `uv tool list` erfolgreich meldet, dass keine anderen uv-Tools mehr installiert sind. **Die Ordner, die Bilder, die Konfiguration und die Log-Dateien werden nie gelöscht.** Hat der Installer uv eingerichtet, wird außerdem der Download-Zwischenspeicher von uv geleert. Manuell: `rffilmlab service uninstall`, dann `uv tool uninstall real-fast-filmlab`.

## Ordner und täglicher Gebrauch

Das Programm arbeitet mit drei Ordnern, die einmal in der Konfiguration festgelegt werden (die Namen sind frei wählbar; hier: `Negative`, `Fotos`, `Archiv`):

| Ordner | Schlüssel | Zweck |
|--------|-----------|-------|
| `Negative/` | `negative_dir` | Eingang: hier RAW-Dateien hineinlegen |
| `Fotos/` | `photos_dir` | Ergebnisse: `<name>.dng`, `<name>.tif`, `<name>.jpg` |
| `Archiv/` | `archive_dir` | Originale nach erfolgreicher Verarbeitung |

Täglicher Gebrauch:

1. Die RAW-Dateien eines Films nach `Negative/` kopieren – am besten den ganzen Film auf einmal, weil Bilder desselben Films aufeinander abgestimmt werden.
2. Verarbeitung starten (Programm „Negative entwickeln“, `rffilmlab run` oder gar nichts, wenn der Hintergrunddienst läuft).
3. Die Bilder erscheinen in `Fotos/`, die Originale wandern nach `Archiv/`.
4. Ist eine Datei selbst fehlerhaft (unlesbares oder beschädigtes RAW, Analyse gescheitert), wandert sie nach `Negative/_Fehler/`; daneben liegt eine `.txt`-Datei mit dem Grund in einfachen Worten. Liegt der Grund woanders (Speicher voll, keine Berechtigung, Laufwerk getrennt, zu wenig Arbeitsspeicher), bleibt die Datei in `Negative/`, und eine Meldung nennt den Grund.
5. Um ein Bild neu zu erzeugen (z. B. nach einer Änderung der Konfiguration), das RAW aus `Archiv/` zurück nach `Negative/` schieben. Vorhandene Ergebnisse bleiben erhalten; die neuen heißen `<name>_2` usw.

### Programm „Negative entwickeln“

So findet man es: unter macOS im Ordner „Programme“ des eigenen Benutzerordners (im Finder: Gehe zu › Benutzerordner › Programme), außerdem über Launchpad oder Spotlight („Negative entwickeln“ eintippen); unter Windows im Startmenü, unter Linux im Anwendungsmenü.

Ein Klick verarbeitet den Ordner `Negative/` einmal. Zu Beginn erscheint kurz der Hinweis „Negative werden entwickelt …“ (verschwindet von selbst), danach meldet ein kleines Fenster mit „OK“ das Ergebnis:

| Meldung | Bedeutung |
|---------|-----------|
| „12 Fotos fertig.“ | Alles umgewandelt |
| „12 Fotos fertig, 1 Fehler – Details in Negative/_Fehler.“ | Eine Datei ging nicht; der Grund steht in `Negative/_Fehler/` |
| „Keine neuen Negative gefunden.“ | `Negative/` enthielt keine RAW-Dateien |
| „Wird gerade im Hintergrund verarbeitet.“ | Der Dienst (oder ein anderer Lauf) arbeitet gerade; die Dateien werden von ihm erledigt |
| „Die Negative konnten nicht entwickelt werden.“ | Mit dem Grund darunter, z. B. „Ordner nicht erreichbar: … – ist das Laufwerk angeschlossen?“, „Kein Speicherplatz mehr frei. Verarbeitung angehalten: …“ oder eine fehlerhafte Konfiguration |

Darunter stehen nur bei Bedarf weitere Zeilen: je ein Problem der [Selbstprüfung](#selbstprüfung) (z. B. „Wenig Speicherplatz frei: 1,5 GB …“) und, wenn es eine neue Version gibt, „Neue Version X verfügbar – siehe Update-Abschnitt auf der Projektseite.“ Dann hat das Fenster einen zweiten Knopf „Projektseite öffnen“, der den Abschnitt [Update](#update) dieser Seite im Browser öffnet (Windows: Knöpfe „Ja“/„Nein“ auf die Frage „Projektseite öffnen?“; Linux ohne zenity und kdialog: die Adresse steht in der Meldung).

Die Verarbeitung kann bei einem ganzen Film einige Minuten dauern; die Ergebnismeldung erscheint erst danach. Ein zweites Programm oder einen zweiten Knopf für die Prüfung gibt es nicht. Das Programm führt `rffilmlab -Q run --summary` aus (der Pfad zu `rffilmlab` und unter macOS und Linux der `PATH` werden bei der Installation eingetragen). Umsetzung: macOS `~/Applications/Negative entwickeln.app` mit einem Shell-Skript und AppleScript-Dialog; Windows `Negative entwickeln.lnk` im Startmenü, das `negative-entwickeln.vbs` im Programmdatenordner mit `wscript.exe` startet; Linux `negative-entwickeln.desktop`, das `negative-entwickeln.sh` im Programmdatenordner startet und das Ergebnis mit zenity, kdialog oder notify-send zeigt (je nachdem, was vorhanden ist; den Hinweis zu Beginn nur mit notify-send).

### Ohne Terminal: Doppelklick-Starter

`scripts/rffilmlab.command` (macOS) und `scripts/rffilmlab.bat` (Windows) verarbeiten den Ordner `Negative/` einmal und lassen das Fenster offen, bis die Eingabetaste (macOS) bzw. eine beliebige Taste (Windows) gedrückt wird; nach einem Fehler steht dort „Es gab ein Problem – siehe oben.“ Die Datei aus dem Repository z. B. auf den Schreibtisch kopieren. Ein Start, während der Hintergrunddienst arbeitet, ist unschädlich: Eine Sperre auf `Negative/` verhindert doppelte Verarbeitung, und der Starter meldet „Der Dienst verarbeitet gerade – bitte später erneut versuchen.“

### Hintergrunddienst

Der Dienst beobachtet `Negative/`, wartet, bis das Kopieren abgeschlossen ist, und verarbeitet die Dateien dann selbstständig. Er startet bei jeder Anmeldung. Am Ende jedes Laufs zeigt eine Desktop-Mitteilung „N Fotos fertig, M Fehler“, bei Fehlern mit dem Ort der Gründe („… – Details in Negative/_Fehler“), bei Problemen mit einem Ordner mit dem Grund. Ist ein Ordner nicht erreichbar (z. B. externes Laufwerk getrennt), meldet der Dienst das einmal (Log und Mitteilung) und versucht es still weiter, bis der Ordner wieder da ist. Scheitert ein Lauf aus einem unvorhergesehenen Grund, meldet er auch das einmal („Unerwarteter Fehler bei der automatischen Verarbeitung – die Negative bleiben liegen, der nächste Versuch folgt von selbst. Bleibt es dabei, hilft das Protokoll weiter.“), schreibt die Einzelheiten ins Log und versucht es weiter. Hat ein voller Datenträger einen Lauf angehalten, startet der Dienst keinen neuen Lauf, bis auf dem Laufwerk von `Fotos/` mindestens 1 GB mehr frei ist als beim Anhalten oder 10 Minuten vergangen sind (neue Dateien in `Negative/` warten so lange). Danach versucht er die übrigen Negative automatisch erneut; die Mitteilung sagt das dazu („Sobald wieder Platz frei ist, geht es von selbst weiter.“). Vor jedem Lauf prüft er sich still selbst ([Selbstprüfung](#selbstprüfung)); jedes Problem erscheint als eine Mitteilung, und erst wieder, wenn es sich geändert hat oder verschwunden und zurückgekehrt ist. Eine neue Version meldet er einmal mit „Neue Version X verfügbar – siehe Update-Abschnitt auf der Projektseite“. Es läuft immer nur ein Dienst je Benutzer; ein zweiter Start endet sofort. Wird der Dienst vom System beendet (Abmeldung, Update unter macOS und Linux), bringt er die Dateien in Arbeit noch zu Ende und beginnt keine weitere; dafür lässt ihm das System bis zu 5 Minuten (`ExitTimeOut` bei launchd, `TimeoutStopSec` bei systemd).

**Der Dienst folgt dem Schalter `service`.** Jeder Lauf („Negative entwickeln“, `rffilmlab run`) und jeder Lauf des Installers gleicht ihn ab: `service = true` und kein Dienst eingerichtet – einrichten und starten; `service = false` und ein Dienst eingerichtet – entfernen. Ist er schon so, wie der Schalter sagt, wird nichts angefasst. Das gilt nur für Läufe mit der normalen Konfigurationsdatei (der Dienst benutzt immer diese); ein Lauf mit `--config ANDERE.toml` ändert und prüft den Dienst nicht. Der Dienst selbst liest die Konfiguration vor jedem seiner Läufe neu: Geänderte Schalter gelten ab seinem nächsten Lauf; geänderte Ordner erst nach einem Neustart des Dienstes (z. B. nach der nächsten Anmeldung), was er einmal meldet („Die geänderten Ordner gelten erst nach einem Neustart des Dienstes – bis dahin arbeitet er mit den bisherigen Ordnern weiter.“); ist die Datei fehlerhaft, arbeitet er mit den zuletzt gültigen Einstellungen weiter und meldet das einmal; ist sie schon beim Start des Dienstes fehlerhaft, meldet er das einmal („Konfiguration fehlerhaft – die automatische Verarbeitung wartet auf die Korrektur: …“) und beginnt, sobald die Datei korrigiert ist. Unter Windows endet ein laufender Dienst nach `service = false` nach seinem aktuellen Lauf. Die Befehle unten wirken sofort; beim nächsten Lauf gilt aber wieder der Schalter. Dauerhaft ausschalten: `service = false` setzen oder mit `--ohne-dienst` installieren.

```bash
rffilmlab service install
```

```bash
rffilmlab service status
```

```bash
rffilmlab service uninstall
```

Umsetzung: macOS LaunchAgent `~/Library/LaunchAgents/io.github.jcmx9.rffilmlab.plist` (nach einem Absturz neu gestartet), Windows `rffilmlab.vbs` im Autostart-Ordner (keine Administratorrechte nötig), Linux systemd-User-Unit `~/.config/systemd/user/rffilmlab.service` (`Restart=on-failure`). Der Dienst führt `rffilmlab -Q watch` aus; der `PATH` zum Zeitpunkt der Installation wird übernommen, damit exiftool gefunden wird.

### Selbstprüfung

Vor jedem Lauf („Negative entwickeln“, `rffilmlab run`) und vor jedem Lauf des Dienstes prüft das Programm still:

| Prüfung | Meldung nur bei einem Problem |
|---------|-------------------------------|
| Die drei Ordner sind erreichbar und beschreibbar | „Ordner nicht erreichbar – ist das Laufwerk angeschlossen? (…)“ oder „Keine Berechtigung für den Ordner: …“; ein Lauf startet dann nicht (der Dienst meldet Ordnerprobleme selbst, siehe oben) |
| Freier Speicher auf dem Laufwerk von `Negative/` und `Fotos/` mindestens 2 GiB (etwa 2,1 GB; die Meldung nennt GB wie Finder und Explorer) | „Wenig Speicherplatz frei: 1,5 GB auf dem Laufwerk mit dem Ordner „Fotos“.“ |
| exiftool wird gefunden | „exiftool wurde nicht gefunden – die Fotos bekommen keine Kameradaten.“ |
| Die Flat-Field-Referenz (`flatfield`, falls gesetzt) ist brauchbar | „Die Flat-Field-Referenz „leer.arw“ ist übersteuert – bitte die Leeraufnahme kürzer belichten, bis nichts mehr überstrahlt. Die Bilder werden ohne sie entwickelt.“ (ebenso: „ist nicht lesbar …“, „ist keine lesbare RAW-Datei“, „zeigt kein Licht“) |
| Neue Dateien in `Negative/_Fehler/` seit der letzten Prüfung | „1 neue Datei in Negative/_Fehler – der Grund steht jeweils in der .txt-Datei daneben.“ |
| Der Hintergrunddienst entspricht dem Schalter `service` | „Der Hintergrunddienst ist nicht eingerichtet, obwohl „service = true“ eingestellt ist.“ (oder umgekehrt) |

Ist alles in Ordnung, erscheint nichts. Probleme stehen bei „Negative entwickeln“ als zusätzliche Zeilen im Ergebnisfenster, bei `rffilmlab run` in der Konsole, beim Dienst als je eine Mitteilung (nicht bei jedem Lauf wiederholt, solange sich nichts ändert), und immer im Log. Welche Dateien in `_Fehler/` schon gemeldet sind, merkt sich das Programm einmal für alle Läufe und den Dienst gemeinsam (Datei `selfcheck.json` im Programmdatenordner): Eine Datei wird nur einmal gemeldet – im Ergebnis des Laufs, der sie dorthin gelegt hat, oder von der nächsten Selbstprüfung –, nicht noch einmal vom Dienst oder von „Negative entwickeln“. Lässt sich `_Fehler/` nicht lesen, bleibt dieser Vermerk unverändert.

### Hinweis auf neue Versionen

Mit `update_check = true` fragt das Programm höchstens einmal in 7 Tagen (vor einem Lauf oder einem Lauf des Dienstes) bei GitHub nach der neuesten Version. Gesendet wird genau eine HTTPS-Anfrage an `https://api.github.com/repos/jcmx9/real-fast-filmlab/releases/latest` (mit der Kennung `real-fast-filmlab/<Version>`), sonst nichts – keine Dateinamen, Bilder oder Einstellungen. Wie bei jeder Webseite sieht GitHub dabei die IP-Adresse. Wartezeit höchstens 5 Sekunden; ohne Internet oder bei einem Fehler passiert nichts (der nächste Versuch nach 7 Tagen). Ist die Version auf GitHub neuer als die installierte, meldet es das einmal je neuer Version:

- „Negative entwickeln“: eine Zeile im Ergebnisfenster und der Knopf „Projektseite öffnen“, der den Abschnitt [Update](#update) im Browser öffnet,
- Dienst: eine Mitteilung „Neue Version X verfügbar – siehe Update-Abschnitt auf der Projektseite“,
- `rffilmlab run`: eine Zeile mit der Adresse.

Das Programm aktualisiert sich nie selbst; das Update startet man mit dem Befehl unter [Update](#update). `update_check = false` schaltet die Anfrage ganz ab. Eine Version gilt erst als gemeldet, wenn der Hinweis angezeigt wurde: Ein stiller Lauf (`-Q` ohne `--summary`) und ein Dienst mit `notify = false` verbrauchen ihn nicht. Der Zeitpunkt der letzten Anfrage und die gemeldeten Versionen stehen in `update-check.json` im Programmdatenordner.

## Konfiguration

### Ort der Konfigurationsdatei

| System | Pfad |
|--------|------|
| macOS | `~/Library/Application Support/real-fast-filmlab/config.toml` |
| Linux | `~/.config/real-fast-filmlab/config.toml` |
| Windows | `%LOCALAPPDATA%\real-fast-filmlab\config.toml` |

Eine andere Datei lässt sich mit `--config PATH` angeben. Fehlt die Datei oder ist ein Ordner nicht gesetzt, nennt das Programm den fehlenden Schlüssel und den erwarteten Pfad der Datei. Unbekannte Schlüssel sind ein Fehler (Schutz vor Tippfehlern), ebenso Werte der falschen Art: Schalter sind `true` oder `false` (nicht `"no"` oder `1`), Zahlen stehen ohne Anführungszeichen und sind endlich (kein `inf`), Ordner und Dateien sind vollständige Pfade (ab `/` oder `~`, unter Windows ab `C:\`), weil der Hintergrunddienst keinen eigenen Ordner hat, von dem aus er zählen könnte. Die Meldung nennt den Schlüssel und was erlaubt ist.

### Beispiel

`rffilmlab config init` (und damit der Installer) schreibt jeden Schlüssel mit seinem Wert und einem kurzen Kommentar, gruppiert wie unten; wer etwas ändern will, ersetzt nur einen Wert, z. B. `true` durch `false`. Ein Ausschnitt:

```toml
# Ordner
negative_dir = "~/Film/Negative"  # Eingang: hier RAW-Dateien hineinlegen
photos_dir = "~/Film/Fotos"        # fertige Bilder
archive_dir = "~/Film/Archiv"      # Originale nach der Verarbeitung

# Ausgaben (JPEG wird immer geschrieben)
dng = true                  # DNG schreiben
tiff = true                 # TIFF schreiben
contact_sheet = true        # nach jedem Lauf ein Kontaktabzug in „Fotos“

# Bildwirkung
contrast = 0.3              # Kontrast, 0 = keiner, üblich 0.2 bis 0.5
saturation = 1.15           # Farbsättigung, 1 = unverändert, üblich 1.1 bis 1.3

# Ausrichtung
rotate = 0                  # 0, 90, 180 oder 270 (im Uhrzeigersinn)
mirror = false              # true: von der Schichtseite fotografiert

# Dienst und Betrieb
service = true              # Hintergrunddienst: neue Negative automatisch umwandeln
update_check = true         # höchstens einmal pro Woche nach neuer Version sehen
```

Eine Konfiguration, der Schlüssel fehlen, ergänzt `rffilmlab config init` (auch bei jedem Lauf des Installers) am Ende der Datei um diese Schlüssel, jeweils mit dem Wert, der bisher galt (Standardwert oder aus anderen Schlüsseln abgeleitet, z. B. `holder_min` aus `holder_delta`; ein fehlendes `service` mit dem aktuellen Zustand des Dienstes, damit ein Update einen entfernten Dienst nicht zurückbringt); vorhandene Zeilen und Werte bleiben unverändert. Eine fehlerhafte Konfiguration wird nicht angefasst.

`~` steht für den Benutzerordner. Die drei Ordner müssen verschieden sein. Ein fehlender Ordner wird bei der Verarbeitung nur angelegt, wenn der Ordner darüber existiert; sonst (z. B. Laufwerk nicht angeschlossen) meldet das Programm „Ordner nicht erreichbar“, statt die Ordner auf der Systemfestplatte anzulegen. `rffilmlab config init` legt die Ordner samt fehlender übergeordneter Ordner an.

### Alle Schlüssel

Jeder Schlüssel ist optional, außer den drei Ordnern (ein fehlender gilt mit seinem Standardwert). Die Schalter `dng`, `tiff`, `contact_sheet`, `service` und `update_check` stehen in einer neuen Konfiguration alle auf `true`. Typen: `path` = Text in Anführungszeichen, `bool` = `true`/`false`, `int`/`float` = Zahl.

#### Ordner

| Schlüssel | Typ | Standard | Erlaubt | Wirkung |
|-----------|-----|----------|---------|---------|
| `negative_dir` | path | – (Pflicht) | vorhandener Ordner oder einer, dessen übergeordneter Ordner existiert | Eingang für RAW-Dateien; nur Dateien direkt darin werden verarbeitet |
| `photos_dir` | path | – (Pflicht) | verschieden von den anderen beiden | Ausgabeordner für DNG, TIFF, JPEG |
| `archive_dir` | path | – (Pflicht) | verschieden von den anderen beiden | Originale werden nach Erfolg hierher verschoben |

#### Ausgaben

| Schlüssel | Typ | Standard | Erlaubt | Wirkung |
|-----------|-----|----------|---------|---------|
| `dng` | bool | `true` | `true`, `false` | DNG schreiben |
| `tiff` | bool | `true` | `true`, `false` | TIFF schreiben (JPEG wird immer geschrieben) |
| `contact_sheet` | bool | `true` | `true`, `false` | Nach einem Lauf mit neuen Bildern einen [Kontaktabzug](#kontaktabzug) in `Fotos/` schreiben |
| `dng_finder_preview` | bool | `false` | `true`, `false` | `false`: float16-DNG mit Deflate (kleiner), unbegrenzt: behält Werte über dem Weißpunkt und unter dem Schwarzpunkt. `true`: unkomprimiertes uint16-DNG, das Finder und Quick Look unter macOS anzeigen (größer), auf 0–1 begrenzt. Beide enthalten die Korrektur (Abschnitt 5) |
| `jpeg_quality` | int | `95` | 1–100 | JPEG-Qualität |
| `jpeg_sharpen` | bool | `false` | `true`, `false` | `true`: das JPEG leicht nachschärfen (Schritt 4.14); TIFF und DNG bleiben ungeschärft |

#### Bildwirkung

| Schlüssel | Typ | Standard | Erlaubt | Wirkung |
|-----------|-----|----------|---------|---------|
| `contrast` | float | `0.30` | 0–0,8 | Grundkontrast jedes Bildes (Abschnitt 5): Steigung der Mitteltöne 1 + Wert; `0` = kein Grundkontrast |
| `saturation` | float | `1.15` | 1–1,6 | Grundsättigung jedes Farbbildes (Abschnitt 5); `1` = unverändert |
| `flatfield` | path | leer | RAW-Datei | Leer: aus. Gesetzt: ein RAW des leeren Halters (ohne Film) auf demselben Licht; der Helligkeitsabfall von Lampe und Objektiv wird damit aus jedem Scan herausgerechnet (Schritt 2.1). Die Referenz gilt für genau einen Aufbau: dasselbe Objektiv, dieselbe Blende, derselbe Abbildungsmaßstab (Abstand) und dieselbe Schärfe-Einstellung wie bei den Scans, die Kamera gleich herum; für einen anderen Aufbau (anderes Format, anderer Halter) eine eigene Aufnahme. Belichtung: so kurz, dass nichts übersteuert (das Licht ohne Film ist viel heller als durch den Film), also nicht die Belichtung der Scans übernehmen. Die Aufnahme darf den schwarzen Rahmen eines Halters um das Lichtfenster zeigen. Sie gehört nicht in den Ordner `Negative/` |

#### Ausrichtung

| Schlüssel | Typ | Standard | Erlaubt | Wirkung |
|-----------|-----|----------|---------|---------|
| `rotate` | int | `0` | `0`, `90`, `180`, `270` | Im Uhrzeigersinn drehen (je Scan-Aufbau, gilt für alle Dateien). Ausgangslage ist das Bild, wie der Sensor es aufgenommen hat; die Lage-Markierung der Kamera wird nicht ausgewertet (Schritt 2.1) |
| `mirror` | bool | `false` | `true`, `false` | Horizontal spiegeln, vor dem Drehen (Film von der Schichtseite fotografiert) |

#### Korrektur

Alle drei Ausgaben enthalten dieselbe Korrektur (Abschnitt 5); im Bereich 0–1 ergibt das DNG dieselben Werte wie das TIFF (SW genau, Farbe außer bei Pixeln mit einem Kamerakanal außerhalb von 0–1). Das float16-DNG behält zusätzlich die Werte außerhalb von 0–1, unbegrenzt (Schritt 4.12). Das DNG trägt ein Profil mit linearer Gradationskurve und ohne automatischen Schwarzabzug, damit Lightroom und Camera Raw es wie das TIFF zeigen statt mit ihrer eigenen Standardkurve.

#### Dienst und Betrieb

| Schlüssel | Typ | Standard | Erlaubt | Wirkung |
|-----------|-----|----------|---------|---------|
| `service` | bool | `true` | `true`, `false` | Hintergrunddienst: `true` = eingerichtet, `false` = nicht eingerichtet; jeder Lauf und der Installer gleichen ihn ab |
| `update_check` | bool | `true` | `true`, `false` | Höchstens einmal in 7 Tagen nach einer neuen Version sehen ([Hinweis auf neue Versionen](#hinweis-auf-neue-versionen)) |
| `notify` | bool | `true` | `true`, `false` | Desktop-Mitteilung mit dem Ergebnis jedes Laufs (nicht bei „Negative entwickeln“, das sein eigenes Fenster zeigt); beim Dienst auch Probleme der Selbstprüfung und eine neue Version |
| `parallel_jobs` | int | `0` | ≥ 0 | Gleichzeitig verarbeitete Dateien; `0` = automatisch: min(CPU-Kerne, ⌊halber Arbeitsspeicher / 4 GiB⌋, Anzahl Dateien), mindestens 1. Der Kommentar in der Datei nennt den automatischen Wert des Rechners, auf dem `config init` sie geschrieben hat |
| `settle_seconds` | float | `5.0` | > 0 | So lange müssen die Dateien unverändert sein, bevor ein Lauf startet (ein einzelner Lauf wartet nur, wenn noch kopiert wird); im Watch-Modus auch die Wartezeit vor einem neuen Versuch (begrenzt auf 5–60 s) |
| `exiftool_path` | path | leer | Pfad zum Programm | Gesetzt: nur dieses Programm (gibt es die Datei nicht, ohne exiftool). Leer: `exiftool` im `PATH`, sonst die Kopie des Installers im Programmdatenordner |

Die Ausgabemenge wird nur auf der Kommandozeile gewählt (`-Q`, `-v`, `-vv`); ein Schlüssel `verbosity` in der Datei wird ignoriert.

#### Experten-Schwellen

Nur nötig, wenn die Erkennung bei ungewöhnlichem Material scheitert. Namen wie im Code (`AnalyzerSettings`, `RollSettings`); die Schritte sind unter [Verarbeitung Schritt für Schritt](#verarbeitung-schritt-für-schritt) erklärt.

Ein Update lässt geänderte Werte stehen. `rffilmlab config init --negative … --photos … --archive … --expert-reset` setzt alle Experten-Schwellen auf ihren Standard zurück; alle anderen Schlüssel bleiben unverändert.

| Schlüssel | Typ | Standard | Erlaubt | Wirkung |
|-----------|-----|----------|---------|---------|
| `measure_inset` | float | `0.10` | 0–0,25 | Inneres Messfenster: Anteil von Höhe/Breite des Zuschnitts, der je Seite ausgelassen wird (0,10 = innere 80 %) |
| `holder_delta` | float | `1.8` | > 0 | Filmmaske: Dichte über der klarsten Basis, bis zu der ein Pixel als Film zählt |
| `holder_min` | float | `1.0` | ≥ 0,3 | Durchscheinender Halter: Mindestdichte über der klarsten Basis, ab der ein Randstreifen als Halter gelten kann (Schritt 4). Wirksam ist max(0,3; min(`holder_min`; `holder_delta`)): Wer `holder_delta` senkt, muss `holder_min` nicht mitändern |
| `gap_delta` | float | `0.10` | > 0 | Strenges Basis-Pixel (Steg zwischen Bildern): Dichtegrenze über der Basis |
| `gap_std` | float | `0.03` | > 0 | Strenges Basis-Pixel: Grenze der lokalen Standardabweichung |
| `loose_delta` | float | `0.15` | > 0 | Lockeres Basis-Pixel (Randbeschnitt): Dichtegrenze über der Basis |
| `loose_std` | float | `0.08` | > 0 | Lockeres Basis-Pixel: Grenze der lokalen Standardabweichung |
| `aspect_tol` | float | `0.08` | > 0 und < 1 | Auf ein Filmformat einrasten, wenn das Seitenverhältnis um weniger als diesen Anteil abweicht |
| `min_skew_deg` | float | `0.2` | 0–45 | Kleinster Schräglagenwinkel, der korrigiert wird (Grad) |
| `max_skew_deg` | float | `5.0` | 0–45 | Größter Schräglagenwinkel, der korrigiert wird (Grad) |
| `dmin_percentile` | float | `0.2` | 0–100 | Perzentil (in %) der Dichte über die Filmmaske, das als Filmbasis gilt |
| `white_percentile` | float | `99.5` | > 0 und ≤ 100 | Perzentil (in %) der Dichte im inneren Fenster, das als Weißpunkt gilt |
| `edge_white` | float | `0.10` | 0–0,5 | Weißpunkt: So viel Dichte dürfen helle Bildteile nahe am Bildrand ihn höchstens anheben (Schritt 2.15); `0` = nur das innere Fenster zählt |
| `bw_threshold` | float | `0.03` | > 0 | Farbe/SW-Entscheidung: Grenze für die Kanalabweichung (99,9-%-Perzentil) |
| `gamma_color` | float | `0.6` | > 0 | Gradation von Farbfilm bei der Umrechnung in lineares Licht |
| `gamma_bw` | float | `0.65` | > 0 | Gradation von Schwarzweißfilm |
| `hue_tol` | float | `0.06` | > 0 | Rollen-Gruppierung: größter Abstand des Farbtons der Filmbasis |
| `highkey_delta` | float | `0.10` | ≥ 0 | High-Key-Fallback: Mindestanhebung der Filmbasis in jedem Kanal |
| `uniform_ratio` | float | `2.0` | ≥ 1 | High-Key-Fallback: größte Anhebung höchstens so viel mal die kleinste |
| `crossover_limit` | float | `0.10` | 0–0,5 | Farbübergangs-Korrektur: So weit darf ein Bild höchstens vom Wert seiner Rolle abweichen; `0` schaltet die Korrektur ab (Schritt 3.5) |
| `crossover_roll_limit` | float | `0.30` | 0–0,5 | Farbübergangs-Korrektur: Der Wert der Rolle ist höchstens so weit von 1 entfernt (Schritt 3.5) |
| `white_limit` | float | `0.10` | 0–0,5 | Farbe des Weißpunkts: So weit darf ein Bild höchstens von der Rolle abweichen (Schritt 3.6); `0` = jedes Bild behält seinen eigenen Weißpunkt |

### Feste Werte (nicht konfigurierbar)

| Konstante | Wert | Modul | Bedeutung |
|-----------|------|-------|-----------|
| `PREVIEW_EDGE` | 1000 | `core/analyzer.py` | Analyse-Vorschau: Schrittweite n = max(1, ⌊lange Kante / 1000⌋) |
| `EDGE_BAND_FRACTION` | 0.6 | `core/analyzer.py` | Randbeschnitt: Spalte/Zeile entfernen, solange > 60 % lockere Basis-Pixel |
| `GAP_FRACTION` | 0.9 | `core/analyzer.py` | Steg: Spalte/Zeile mit > 90 % strengen Basis-Pixeln |
| `EDGE_FACTOR` | 2.5 | `core/analyzer.py` | Verankerte Kante: Kantenwert ≥ 2,5 × typischer Kantenwert |
| `EDGE_WINDOW` | 0.06 | `core/analyzer.py` | Suchfenster um ein Ende: ±6 % der Achsenlänge |
| `EDGE_BAND` | 0.04 | `core/analyzer.py` | Schräglage: Band je Kante, 4 % der längeren Seite des groben Rechtecks nach innen und außen |
| `COARSE_STEP`, `FINE_STEP` | 0.25°, 0.02° | `core/analyzer.py` | Schräglage: Schrittweite der groben und der feinen Suche |
| `MIN_GAIN` | 0.01 | `core/analyzer.py` | Schräglage: weniger als 1 % Gewinn gegenüber 0° = keine Kante, Umriss der Filmmaske gilt |
| `HOLDER_P10` | 0.8 | `core/analyzer.py` | Durchscheinender Halter: 10-%-Perzentil ≥ 0,8 × `holder_min` |
| `HOLDER_STEP` | 0.005 | `core/analyzer.py` | Durchscheinender Halter: basisartige Linie innerhalb max(2, 0,5 % der langen Kante) |
| `STRIP_FRAME_SHARE`, `STRIP_AREA_SLACK` | 0.005, 0.03 | `core/analyzer.py` | Durchscheinender Halter: Ein sicheres Bildfeld wird neu bestimmt, wenn mehr als 0,5 % seiner Fläche Halterstreifen sind; das neue darf darüber hinaus höchstens 3 % kleiner sein |
| `BORDER_MARGIN` | 0.02 | `core/analyzer.py` | Blankes Licht: Rand von 2 % der langen Kante je Seite für die erste Basis-Schätzung ausgelassen |
| `BARE_GAP` | 0.2 | `core/analyzer.py` | Blankes Licht: mehr als 0,2 unter der ersten Basis-Schätzung |
| `RIM_COVERAGE` | 0.8 | `core/analyzer.py` | Blankes Licht: klare Pixel entlang von mindestens 80 % jeder der vier Bildseiten sind der Filmrand eines Bildes, kein Licht |
| `PATCH_DECILE`, `PATCH_BIN`, `PATCH_VALLEY` | 10 %, 0.02, 0.1 | `core/analyzer.py` | Blankes Licht in Flecken: klarste 10 % der Pixel, Dichte-Raster 0,02, Tal = Zellen mit höchstens 10 % der höchsten Zelle darunter |
| `PATCH_MIN_COUNT`, `PATCH_AREA_RATIO`, `PATCH_SPAN`, `PATCH_MIN_PIXELS` | 4, 4, 0.25, 9 | `core/analyzer.py` | Blankes Licht in Flecken: mindestens 4 Flecken, größter höchstens 4 × so groß wie der kleinste, keiner länger als 25 % der langen Kante, kleinere als 9 Pixel zählen nicht |
| `BW_PERCENTILE` | 99.9 | `core/analyzer.py` | Farbe/SW: Perzentil der Block-Abweichung |
| `HOLDER_MIN_FLOOR` | 0.3 | `config.py` | Untergrenze von `holder_min` |
| `ASPECTS` | 1:1 = 1,00, 6x7 = 1,24, 6x4.5 = 1,35, 3:2 = 1,50 | `core/analyzer.py` | Filmformate zum Einrasten |
| `crop_rect(inset)` | 0.01 | `core/geometry.py` | Zuschnitt je Seite um 1 % seiner längeren Seite nach innen gezogen |
| `MEASURE_INSET` | 0.10 | `core/geometry.py` | Standardwert von `measure_inset` |
| `EDGE_INSET` | 0.03 | `core/geometry.py` | Weißpunkt: Fenster für helle Bildteile am Rand, je Seite 3 % kleiner als der Zuschnitt |
| `PICTURE_INTERPOLATION` | Lanczos (8 × 8) | `core/geometry.py` | Entzerren des Bildes in voller Auflösung |
| `MAX_BALANCE_GAIN` | 16 | `fileio/raw_loader.py` | größte Anhebung eines Kanals für das Demosaicing |
| `EDGE_TOLERANCE`, `FIT_EDGE_FACTOR` | 2 px, 2.5 | `core/geometry.py` | Bildgröße der Rolle: Eine Kante darf 2 Vorschau-Pixel neben der erwarteten Stelle liegen; klare Kante = 2,5 × typischer Kantenwert |
| `MIN_SPREAD` | 0.05 | `core/converter.py` | Kleinster Dichteumfang je Kanal |
| `black_point(percentile)` | 0.5 | `core/converter.py` | Schwarzpunkt: 0,5-%-Perzentil der Luminanz |
| `EPS` | 1/65535 | `core/converter.py` | Kleinster Wert vor dem Logarithmus |
| `BASE_CONTRAST`, `BASE_SATURATION` | 0.30, 1.15 | `core/look.py` | Standardwerte von `contrast` und `saturation` |
| `MAX_TOTAL_CONTRAST`, `MAX_TOTAL_SATURATION` | 0.8, 1.6 | `core/look.py` | Obergrenzen für Grundwert plus Zugabe |
| `COLOR_STRENGTH`, `BW_STRENGTH` | 1.0, 0.5 | `core/look.py` | Stärke der Zugabe für Farbe und SW |
| `SPREAD_TARGET`, `MAX_CONTRAST` | 0.70, 0.35 | `core/look.py` | Kontrast-Zugabe (Gruppe) |
| `CHROMA_TARGET`, `SAT_GAIN`, `MAX_SATURATION`, `CHROMA_FULL` | 0.10, 1.5, 1.15, 0.5 | `core/look.py` | Sättigungs-Zugabe und Chroma-Gewichtung |
| `SAMPLE_STEP` | 4 | `core/look.py` | Look-Statistik auf jedem 4. Pixel |
| `MID_BAND`, `MIN_MID_PIXELS` | 0.05, 200 | `core/crossover.py` | Farbübergang: Mittelgrau-Pixel mit \|x_G − 0,5\| < 0,05; weniger als 200 im inneren Fenster: keine Messung |
| `MID_CLIP` | 0.05–0.95 | `core/crossover.py` | Farbübergang: Mittelwerte vor dem Logarithmus auf diesen Bereich begrenzt |
| `ROLL_MIN_FRAMES`, `ROLL_AGREEMENT` | 3, 0.8 | `core/crossover.py` | Farbübergang je Rolle: mindestens 3 gemessene Farbbilder, davon ≥ 80 % je Kanal R und B auf derselben Seite |
| `ROLL_LIMIT` | 0.30 | `core/crossover.py` | Standardwert von `crossover_roll_limit` |
| `ROLL_MIN_FRAMES`, `SIZE_TOLERANCE` | 3, 0.03 | `core/rolls.py` | Rollenwerte für Weißpunkt-Farbe und Bildgröße: mindestens 3 Bilder; Bildgrößen innerhalb von 3 % gelten als gleich |
| `BASE_TOO_DARK`, `BASE_CLIPPED` | 0.125, 0.98 | `core/rolls.py` | Hinweis zur Scan-Belichtung: Filmbasis unter einem Achtel bzw. an der Grenze des Sensorbereichs |
| `KEYSTONE_TOLERANCE` | 0.4° | `core/rolls.py` | Hinweis, wenn gegenüberliegende Bildkanten im Median des Laufs um mehr abweichen |
| `MAP_EDGE`, `BLUR_FRACTION`, `CENTRE_FRACTION` | 256 px, 0.05, 0.1 | `fileio/flatfield.py` | Flat-Field: Größe der Abfall-Karte, Weichzeichnung (5 % ihrer langen Kante), Mittelbereich als „volles Licht“ |
| `MIN_GAIN`, `MAX_GAIN`, `ASPECT_TOLERANCE` | 0.2, 1.5, 0.02 | `fileio/flatfield.py` | Flat-Field: Grenzen des Abfalls; Referenz und Scan müssen dasselbe Seitenverhältnis haben (± 2 %) |
| `LIT_FRACTION`, `LIT_MARGIN`, `MIN_WEIGHT` | 0.25, 2 px, 0.001 | `fileio/flatfield.py` | Flat-Field: beleuchtet ist, was im hellsten Kanal über 25 % des Spitzenwerts der Referenz liegt; 2 Karten-Pixel am Rand dieser Fläche (weiche Fensterkante) zählen nicht; wo weniger als 0,1 % des Weichzeichner-Kerns beleuchtet ist, gilt der Wert des nächsten Pixels mit Messwert |
| `CLIP_LEVEL`, `CLIP_SHARE`, `DARK_LEVEL` | 0.98, 0.01, 0.01 | `fileio/flatfield.py` | Flat-Field: Referenz übersteuert, wenn mehr als 1 % der beleuchteten Fläche 98 % des Sensorbereichs erreicht; ohne Licht, wenn ihr Spitzenwert unter 1 % liegt |
| `SHARPEN_SIGMA`, `SHARPEN_AMOUNT` | 1.0 px, 0.5 | `service/render.py` | JPEG-Schärfung (`jpeg_sharpen`) |
| `SAMPLE_MAX_PIXELS` | 87 381 | `core/crossover.py` | Dichte-Stichprobe des inneren Fensters je Bild (höchstens 1 MiB) |
| `PREVIEW_LONG_EDGE` | 1024 | `service/render.py` | Lange Kante der im DNG eingebetteten Vorschau |
| `MEMORY_PER_WORKER` | 4 GiB | `system.py` | Arbeitsspeicher-Budget je parallelem Job |
| `STALE_TEMP_SECONDS` | 3600 | `service/batch.py` | Liegengebliebene temporäre Dateien älter als 1 h werden gelöscht |
| `NAME_ATTEMPTS` | 5 | `service/batch.py` | Ausgaben: so viele Namen werden versucht, wenn ein Name inzwischen vergeben wurde |
| `STALE_TEMP_PATTERNS` | `.*.tmp.*`, `*_exiftool_tmp` | `service/batch.py` | Namensmuster dieser temporären Dateien |
| `TIMEOUT_SECONDS` | 300 | `fileio/exiftool.py` | Längste Laufzeit eines exiftool-Aufrufs |
| `RESCAN_SECONDS` | 60 | `service/watcher.py` | Watch-Modus: Ordner mindestens einmal pro Minute neu prüfen |
| `COPY_WAIT_SECONDS` | 600 | `service/settle.py` | Ruhephase: So lange hält eine Datei, die noch kopiert wird, die übrigen zurück |
| `STOP_TIMEOUT_SECONDS` | 300 | `service/daemon.py` | Dienst: Zeit, die das System dem Dienst zum Beenden lässt (macOS, Linux) |
| `MIN_BACKOFF`, `MAX_BACKOFF` | 5 s, 60 s | `service/watcher.py` | Watch-Modus: Grenzen der Wartezeit vor einem neuen Versuch |
| `DISK_FULL_PAUSE` | 600 s | `service/watcher.py` | Watch-Modus: längste Pause nach einem vollen Datenträger, solange nicht genug Platz frei wird |
| `DISK_FULL_RESUME_BYTES` | 1 GiB | `service/watcher.py` | Watch-Modus: so viel mehr freier Platz als beim Anhalten beendet die Pause vorzeitig |
| `FINDER_BUSY_DAY` | 24.01.1984 (±12 h) | `service/settle.py` | macOS: Erstellungsdatum, mit dem der Finder eine Datei während des Kopierens markiert |
| `LOW_SPACE_BYTES` | 2 GiB | `service/selfcheck.py` | Selbstprüfung: darunter Warnung „Wenig Speicherplatz frei“ |
| `CHECK_INTERVAL_SECONDS` | 7 Tage | `service/update.py` | Höchstens eine Anfrage nach neuer Version in diesem Abstand |
| `TIMEOUT_SECONDS` | 5 s | `service/update.py` | Längste Wartezeit auf die Antwort von GitHub |
| `COLUMNS`, `THUMB_SIZE`, `LABEL_HEIGHT` | 6, 320 × 240 px, 28 px | `service/contact_sheet.py` | Kontaktabzug: Spalten, Feld je Vorschaubild, Platz für den Dateinamen |
| `NOTE_HEIGHT`, `NOTE_FRAME` | 20 px, 3 px | `service/contact_sheet.py` | Kontaktabzug: Zeile für den Prüfhinweis, Rahmenbreite um ein markiertes Bild |
| `SHEET_MAX_PICTURES` | 300 | `service/contact_sheet.py` | Kontaktabzug: höchstens so viele Bilder je Datei, darüber „Teil 1“, „Teil 2“ … |
| `GAP`, `MARGIN`, `FONT_SIZE`, `QUALITY` | 16 px, 24 px, 14 px, 85 | `service/contact_sheet.py` | Kontaktabzug: Abstand, Rand, Schriftgröße (Standardschrift von Pillow), JPEG-Qualität |

## Verarbeitung Schritt für Schritt

### Überblick

Jeder Lauf verarbeitet alle Dateien in zwei Durchgängen: **Durchgang 1** analysiert jede Datei auf einer kleinen Vorschau, danach vergleicht der **Rollen-Kontext** die Dateien miteinander, und **Durchgang 2** entwickelt jede Datei in voller Auflösung und schreibt die Ausgaben. Drei Bereiche des Scans werden unterschieden, und sie werden in dieser Reihenfolge bestimmt:

1. **Filmmaske** – der ganze Filmstreifen im Bild (Bildfelder, Stege zwischen den Bildern, Filmrand), ohne den Halter. Hier wird die Filmbasis `d_min` gemessen.
2. **Zuschnitt** – das erkannte Bildfeld, zuerst und vollständig bestimmt (Entzerrung, Ränder, Stege, Format-Einrasten, 1 % nach innen). TIFF und JPEG werden darauf beschnitten; das DNG trägt ihn als zurücksetzbare Zuschnitt-Einstellung. Hier wird Farbe/SW gemessen.
3. **Inneres Fenster** – der Zuschnitt ohne `measure_inset` (10 %) seiner Höhe/Breite je Seite (innere 80 % × 80 %), immer relativ zum *endgültigen* Zuschnitt gelegt. Weißpunkt, Schwarzpunkt, Farbübergang und alle Look-Statistiken werden hier gemessen, damit ein Streifen Filmrand oder Halter am Rand sie nicht verschieben kann. Weiß- und Schwarzpunkt gelten nur für dieses eine Bild (Normierung je Bild, siehe Grundsätze).

### 1. Auslöser und Lauf-Start

1. **Auslöser.** `rffilmlab run` (oder `rffilmlab` ohne Befehl, das Programm „Negative entwickeln“ oder ein Doppelklick-Starter) verarbeitet den Ordner einmal. Im Watch-Modus (`rffilmlab watch`, Hintergrunddienst) weckt ein Dateisystem-Ereignis oder spätestens eine Neuprüfung alle 60 s das Programm; beim Start bereits wartende Dateien werden verarbeitet.
2. **Ruhephase.** Im Watch-Modus: Alle 0,5 s werden Größe und Änderungszeit (`mtime_ns`) aller Kandidaten gelesen; eine Datei, die sich noch nicht zum Lesen öffnen lässt (Windows während des Kopierens) oder die der Finder unter macOS noch kopiert (Erstellungsdatum 24.01.1984, `FINDER_BUSY_DAY`), gilt als „wird kopiert“. Der Lauf startet, sobald sich Größen und Zeiten `settle_seconds` (5 s) lang nicht geändert haben und keine Datei mehr kopiert wird: Die Bilder eines Films gehören in einen Lauf, damit der Rollen-Kontext alle vergleichen kann. Endet ein Kopiervorgang 10 Minuten lang nicht (eine Datei, die dauerhaft gesperrt ist), läuft der Rest ohne diese Datei. Fehlgeschlagene Dateien, die in `Negative/` geblieben sind, werden übersprungen, bis sich Größe oder Zeit ändern (ein Lauf über „Negative entwickeln“ oder `rffilmlab run` versucht sie erneut). Ein einzelner Lauf nimmt Dateien, die seit `settle_seconds` unverändert und nicht als „wird kopiert“ erkennbar sind, sofort; wurde eine Datei später geändert oder wird eine noch kopiert, wartet er dieselbe Ruhephase ab, also auch auf das Ende des Kopierens (höchstens 10 Minuten; danach lässt er Dateien aus, die immer noch kopiert werden).
3. **Ordner.** Alle drei Ordner müssen gesetzt und verschieden sein (verglichen wird der Ordner selbst, nicht die Schreibweise: eine Verknüpfung auf einen Ordner oder eine andere Groß-/Kleinschreibung auf einem Dateisystem, das sie nicht unterscheidet, ist derselbe Ordner). Ein fehlender Ordner wird nur angelegt, wenn der Ordner darüber existiert. Ist ein Ordner nicht erreichbar oder nicht beschreibbar (auch beim Anlegen der Sperrdatei oder beim Lesen von `Negative/`), endet der Lauf mit einer klaren Meldung, z. B. `Error: Ordner nicht erreichbar – ist das Laufwerk angeschlossen? (<Pfad>)`, `Keine Berechtigung für den Ordner: …`, `Der Ordner ist schreibgeschützt: …` oder `Kein Speicherplatz mehr frei: …` (Exit-Code 1). Der Watch-Modus meldet das einmal in Log und Mitteilung, versucht es alle min(60, max(5, `settle_seconds`)) s still erneut (ist `Negative/` selbst nicht lesbar, spätestens bei der Neuprüfung alle 60 s) und meldet erst eine Änderung wieder.
4. **Sperre.** Exklusive, nicht blockierende Sperre auf `Negative/.rffilmlab.lock`. Hält ein anderer Lauf sie, endet dieser Lauf sofort, ohne etwas anzufassen („Der Dienst verarbeitet gerade – bitte später erneut versuchen.“, Exit-Code 0); der Watch-Modus versucht es nach min(60, max(5, `settle_seconds`)) s erneut. Dateisysteme ohne Sperr-Unterstützung (manche Netzlaufwerke): Die Sperre liegt dann in den Programmdaten dieses Rechners (`locks/<Kennung des Ordners>.lock`) und schützt weiter vor einem zweiten Lauf auf demselben Rechner; lässt sich auch sie nicht anlegen: Warnung, Lauf ohne Sperre.
5. **Aufräumen.** Temporäre Dateien abgebrochener Läufe in `Fotos/` und `Archiv/` (`.<name>.tmp.*` und `<name>_exiftool_tmp` eines abgebrochenen exiftool), die älter als 1 h sind, werden gelöscht.
6. **Eingabeliste.** Dateien direkt in `Negative/` (keine Unterordner, `_Fehler/` wird also ignoriert), deren Endung ein bekanntes RAW-Format ist (Groß-/Kleinschreibung egal), ohne Namen, die mit `.` beginnen (versteckte Dateien, macOS-`._`-AppleDouble-Dateien). Nach Namen sortiert.
7. **exiftool und Parallelität.** exiftool wird gesucht: Ist `exiftool_path` gesetzt, nur dort; sonst im `PATH`, dann die Kopie des Installers im Programmdatenordner (fehlt es: eine Warnung). Anzahl paralleler Jobs: siehe `parallel_jobs`. Parallele Jobs sind Threads; sie ändern das Ergebnis nicht.

### 2. Durchgang 1: Analyse jeder Datei

Auf einer Vorschau des RAW in halber Auflösung. Eine Datei, die hier scheitert, wandert sofort nach `_Fehler/`; nur bei zu wenig Arbeitsspeicher oder einem Fehler des Dateisystems bleibt sie in `Negative/` (Schritt 4.18).

1. **Laden.** LibRaw (über rawpy) dekodiert das RAW in halber Auflösung mit 16 bit, linear (Gamma 1), ohne Weißabgleich (alle Multiplikatoren 1), ohne automatische Helligkeit, im eigenen RGB-Farbraum der Kamera; das Demosaicing ist der LibRaw-Standard. Das Bild wird so dekodiert, wie der Sensor es aufgenommen hat (`user_flip = 0`): Die Lage-Markierung der Kamera ist zufällig, wenn die Kamera senkrecht nach unten auf den Film blickt, deshalb bestimmen allein `rotate` und `mirror` die Lage; alle Ausgaben tragen `Orientation = 1`. Die Werte behalten den Maßstab des Sensors (`adjust_maximum_thr = 0`; LibRaw würde eine Datei sonst auf ihr eigenes hellstes Pixel umrechnen, was die Dichten von Bild zu Bild verschiebt) und werden durch 65535 geteilt (0–1). Die Farbmatrix der Kamera (XYZ → Kamera) wird mitgelesen; fehlt sie, gilt die Einheitsmatrix. Aus den Aufnahmedaten wird die *Scan-Belichtung* gelesen: log10(Belichtungszeit · ISO / Blende²); ohne Zeit oder ISO gilt sie als unbekannt, eine fehlende Blende (manuelles Objektiv) zählt als 1. *Flat-Field:* Ist `flatfield` gesetzt, wird die Referenz einmal in halber Auflösung dekodiert, auf eine Karte mit 256 Pixeln langer Kante verkleinert, weichgezeichnet (Sigma 5 % der langen Kante; Staub auf der Referenz hinterlässt so keine Spuren) und je Kanal auf den Mittelwert ihres mittleren Zehntels normiert (Abfall, begrenzt auf 0,2–1,5). Weichgezeichnet wird nur über die beleuchtete Fläche (hellster Kanal über 25 % des Spitzenwerts, ohne 2 Pixel an ihrem Rand): Zeigt die Referenz das Lichtfenster eines Halters in einem schwarzen Rahmen, läuft der Rahmen so nicht in die Karte; außerhalb der beleuchteten Fläche setzt die Karte den Wert an deren Rand fort. Jeder Scan wird je Kanal durch die auf seine Größe gebrachte Karte geteilt. Eine Referenz, die den Abfall nicht zeigen kann, wird nicht benutzt, und die Scans werden ohne sie entwickelt: nicht lesbar, ohne Licht (Spitzenwert unter 1 % des Sensorbereichs) oder übersteuert (mehr als 1 % der beleuchteten Fläche bei 98 % des Sensorbereichs – übersteuertes Licht ist überall gleich hell, wie stark der Abfall auch ist). Das meldet die [Selbstprüfung](#selbstprüfung). Hat die Referenz ein anderes Seitenverhältnis als ein Scan (± 2 %), wird dieser ohne sie entwickelt; das steht als Hinweis im Ergebnis des Laufs (Schritt 3.8).
2. **Vorschau.** Jedes n-te Pixel in beiden Richtungen, n = max(1, ⌊lange Kante / 1000⌋); die lange Kante der Vorschau hat also 1000–1999 Pixel.
3. **Dichte.** Je Kanal D = −log10(max(T, 1/65535)), T = linearer Wert. Auf einem Negativ hat die Filmbasis die geringste Dichte, die hellsten Stellen der Szene die höchste. Für die Erkennung wird das Kanalmittel `lum` verwendet.
4. **Filmmaske** (Bereich 1). Referenz `d_ref` = 0,5-%-Perzentil von `lum` (die klarste Filmbasis), gemessen ohne *blankes Licht*: Pixel, die mehr als 0,2 unter dem 0,5-%-Perzentil des Bildinneren (ohne 2 % der langen Kante Rand je Seite) liegen, sind ein Lichtstreifen am Bildrand (kein Film) und zählen weder für `d_ref` noch für die Filmmaske noch für `d_min`. Das gilt nur, solange der Teil des Streifens im Bildinneren unter 0,5 % der Pixel des Bildinneren liegt; darüber stellt der Streifen selbst das Perzentil, und das Ergebnis entspricht dem Verhalten ohne Behandlung von blankem Licht. *Filmrand rundum:* Füllt ein Bild den Scan, liegt sein klarer Filmrand ebenfalls in diesem Rand, und ist kein Schatten im Bild so klar wie die Filmbasis, sähe er aus wie blankes Licht. Licht neben dem Film oder durch einen Spalt im Halter liegt aber an einer Seite oder an zwei gegenüberliegenden, Perforation zeigt sich in Flecken; nur der Rand eines Bildes läuft an allen vier Seiten entlang. Bedecken die klaren Pixel innerhalb des Randes an jeder der vier Bildseiten mindestens 80 % ihrer Länge, gilt deshalb nichts als blankes Licht. Pixel mit `lum < d_ref + holder_delta` (1,8) sind Film, dichtere Pixel sind Halter. Danach morphologisches Öffnen und Schließen mit einem quadratischen Kern von max(3, lange Kante / 100) Pixeln (ungerade), und nur der größte zusammenhängende Bereich bleibt. Gibt es keinen, gilt das ganze Bild als Film. *Durchscheinender Halter:* Es werden Randstreifen gesucht, die weniger dicht als `holder_delta`, aber deutlich dichter als die Basis sind. Je Bildseite zählen die Spalten (links/rechts) bzw. Zeilen (oben/unten) vom Bildrand nach innen, deren Dichte über `d_ref` über die ganze Seitenlänge einen Median ≥ `holder_min` (1,0) und ein 10-%-Perzentil ≥ 0,8 × `holder_min` hat (gleichmäßig dicht auf ≥ 90 % der Seite). Ein solcher Streifen gilt nur dann als Halter, wenn innerhalb von max(2, 0,5 % der langen Kante) Linien danach eine basisartige Linie folgt (Median ≤ `d_ref` + `loose_delta`, der Filmrand); der Streifen reicht bis zu dieser Linie. Ein heller Motivbereich am Rand (Himmel) hat keine solche Linie danach und bleibt Film. Die Streifen werden aus der Filmmaske genommen, die Schritte 6–11 laufen erneut, und das Ergebnis gilt nur, wenn es sicher ist; sonst bleibt alles wie mit der festen Schwelle. Das geschieht, wenn die Erkennung mit der festen Schwelle nicht sicher ist (Schritt 11) oder wenn ihr Bildfeld in einen solchen Streifen hineinreicht (mehr als 0,5 % seiner Fläche); ob der erste Durchlauf zufällig sicher war, entscheidet also nicht darüber, ob ein durchscheinender Halter im Zuschnitt bleibt. Ein zuvor sicheres Bildfeld darf dabei nur verlieren, was die Streifen von ihm einnahmen (Fläche ≥ (1 − Streifenanteil)² × 0,97 der bisherigen); schneidet ein breiter „Streifen“ tiefer hinein, ist er Bild und kein Halter, und das erste Ergebnis bleibt. Bei dichten Filmhaltern liegen die Streifen außerhalb der Filmmaske und damit außerhalb jedes Bildfelds; eine sichere Erkennung bleibt dann unverändert. *Blankes Licht in Flecken* (z. B. sichtbare Perforation) wird erkannt, aber nicht korrigiert: Unter den klarsten 10 % der Pixel des Bildinneren liegt eine zweite Häufung, mindestens 0,2 klarer als der Rest (dazwischen ein Tal aus Dichte-Zellen von 0,02 mit höchstens 10 % der höchsten Zelle darunter), verteilt auf mindestens 4 Flecken ähnlicher Größe (größter höchstens 4 × der kleinste, ab 9 Pixeln), von denen keiner länger als 25 % der langen Kante ist. Dann nennt der Grund des Zuschnitts `patches of bare light inside the film (perforation?): the film base may be measured on them`: Die Filmbasis kann auf diesen Flecken gemessen sein, und das Bild behält dann die Farbe der Filmmaske.
5. **Schräglage** (an den Außenkanten des Bildfelds). Zuerst laufen die Schritte 6–11 ohne Drehung und liefern ein grobes Bildfeld-Rechteck: die Kanten des gefundenen Segments *vor* dem Format-Einrasten und Kürzen (Schritte 9–10), bei unsicherer Erkennung das umschließende Rechteck der Filmmaske. So hängt der Winkel nicht davon ab, welches Ende gekürzt wird. Kantenbild = Betrag des Gradienten von `lum`, nur auf Film-Pixeln (Filmmaske, um max(3, lange Kante / 100) Pixel geschrumpft, ungerade; die Kante Film/Halter zählt nicht) und nur in vier Bändern um die Außenkanten dieses Rechtecks: je Kante 4 % seiner längeren Seite nach innen und nach außen. Das Bildinnere zählt nicht, Linien im Motiv beeinflussen den Winkel also nicht. Die Band-Pixel werden probeweise um θ gedreht (gegen den Uhrzeigersinn, um die Bildmitte, wie beim Entzerren); Gütemaß = Summe der quadrierten Zeilenprofile des oberen und unteren Bands plus Summe der quadrierten Spaltenprofile des linken und rechten Bands (Profilschritt 1 Pixel, lineare Verteilung auf die zwei Nachbarzellen nach einem festen Zufallsversatz von ±0,5 Pixel je Pixel, damit 0° nicht durch das Pixelraster bevorzugt wird). θ läuft von −`max_skew_deg` bis +`max_skew_deg` (5°) in Schritten von 0,25°, dann in Schritten von 0,02° im Bereich ±0,25° um das beste Grobergebnis (13 Schritte je Seite); bei Gleichstand gewinnt der kleinere |θ|, bei ±θ der negative. Liegt das beste Gütemaß weniger als 1 % über dem bei θ = 0 (keine nennenswerte Kante), liefert stattdessen `cv2.minAreaRect` um den Umriss der Filmmaske den Winkel, normiert auf −45° bis +45°. Nur wenn `min_skew_deg` (0,2°) ≤ |Winkel| ≤ `max_skew_deg` (5°), werden Vorschau und Maske um die Mitte um diesen Winkel gedreht und die Schritte 6–11 laufen erneut auf dem gedrehten Bild; sonst ist der Winkel 0 und das Ergebnis des ersten Laufs gilt. War der erste Lauf sicher, der zweite (gedrehte) aber nicht, gilt ebenfalls das ungedrehte Ergebnis des ersten Laufs (Winkel 0). *Parallelität der Kanten:* Liefern die Kanten einen Winkel, wird jedes der vier Bänder zusätzlich allein über die groben Winkel bewertet (Scheitel per Parabel verfeinert; ein Band ohne klare Kante zählt nicht) und der Unterschied oben − unten sowie links − rechts festgehalten. Ein einzelnes Bild ist dabei unzuverlässig; ausgewertet wird nur der Median über den ganzen Lauf (Schritt 3.8).
6. **Basis-Pixel.** Lokale Standardabweichung von `lum` in einem Fenster von max(3, lange Kante / 100) Pixeln (ungerade: `max(3, Kante // 100) | 1`), nur über Film-Pixel (der Halter kann sie an der Filmkante nicht anheben). *Strenges* Basis-Pixel: `lum < d_ref + gap_delta` (0,10) und Standardabweichung < `gap_std` (0,03). *Lockeres* Basis-Pixel: `lum < d_ref + loose_delta` (0,15) und Standardabweichung < `loose_std` (0,08), oder außerhalb der Filmmaske. Die folgenden Schritte arbeiten innerhalb des umschließenden Rechtecks der Filmmaske; seine längere Seite ist die lange Achse des Streifens.
7. **Ränder beschneiden.** Für jede Spalte (und Zeile) wird der Anteil lockerer Basis-Pixel berechnet; von beiden Enden werden Spalten/Zeilen entfernt, solange der Anteil > 60 % ist (Filmrand, Steg-Saum, Halterkante). Bliebe weniger als 10 % der Achse übrig, wird nichts beschnitten. *Weiche Filmkante:* Ist die Kante zwischen Film und Halter nicht pixelscharf (Unschärfe, schräg liegender oder entzerrter Film), sind die äußersten Zeilen des Films ein Gemisch aus beidem und keine lockere Basis; der Filmrand dahinter würde dann nicht entfernt, und das Bildfeld samt Filmrand kann auf ein breiteres Format passen. Deshalb wird ein zweites Mal beschnitten, wobei ein Band lockerer Basis auch dann entfernt wird, wenn es erst innerhalb von 1 % der langen Kante hinter dem Ende beginnt (mit den Zeilen davor). Dieses Ergebnis gilt nur, wenn es in Schritt 9 auf ein anderes Format führt als das erste; führen beide auf dasselbe Format, bleibt es beim ersten.
8. **An Stegen teilen** (nur lange Achse). Im beschnittenen Bereich sind Folgen von Spalten mit > 90 % strengen Basis-Pixeln, die mindestens max(2, lange Seite des Rechtecks / 100) breit sind, Stege zwischen Bildern. Das breiteste Segment dazwischen ist das Bildfeld. Tiefe Schatten im Motiv erfüllen die strengen Kriterien praktisch nie.
9. **Format einrasten.** Das Verhältnis lange/kurze Seite wird mit 1:1 (1,00), 6×7 (1,24), 6×4,5 (1,35) und 3:2 (1,50) verglichen; das Format mit der kleinsten relativen Abweichung gewinnt, wenn diese < `aspect_tol` (8 %) ist. Die zu lange Seite wird auf das genaue Verhältnis gekürzt. Sonst bleibt das Format „frei“.
10. **Welches Ende gekürzt wird** (nur nach dem Einrasten; zuerst entlang der Spalten, dann entlang der Zeilen). Kantenwert einer Spalte = Median über die Zeilen des Bildfelds der absoluten Dichtedifferenz zur nächsten Spalte. Ein Ende ist *verankert* (scharfer Bildrand), wenn der höchste Kantenwert innerhalb ±6 % der Achsenlänge um das Ende 2,5 × (`EDGE_FACTOR`) den Median der Kantenwerte im Segment erreicht. Beide Enden verankert: als Kante gilt die Stelle des höchsten Kantenwerts im Fenster; was zwischen Segmentende und Kante liegt, ist Außenstreifen (Schleier, Filmrand). Der Überstand wird je zur Hälfte an beiden Enden entfernt, außer dabei bliebe ein Außenstreifen stehen: dann wird die Aufteilung gerade so weit verschoben, dass er wegfällt. Sind beide Außenstreifen zusammen breiter als der Überstand, liegt der Ausschnitt mittig zwischen den beiden Kanten (höchstens der ganze Überstand an einem Ende); ist das Bildfeld kürzer als das Format, kann der Ausschnitt dabei einige Zeilen über eine Kante hinausreichen. Bekannte Schwäche: Die steilste Stufe im Fenster ±6 % kann eine gerade Motivkante statt des Bildrands sein; der Schaden ist auf den Überstand begrenzt. Ein Ende verankert: der ganze Überstand wird am anderen Ende entfernt. Kein Ende verankert: von allen möglichen Aufteilungen wird die gewählt, deren entfernte Streifen die geringste summierte Median-Dichte haben (nahe Filmbasis: Schleier, Filmrand, Steg-Saum); bei Gleichstand gewinnt die symmetrische Aufteilung.
11. **Sicherheit und Fallback.** Die Erkennung ist *sicher*, wenn das Format eingerastet ist, mindestens ein Rand beschnitten oder ein Steg gefunden wurde und das Bildfeld 25–98 % der Filmmaske bedeckt. Sonst gilt das umschließende Rechteck der Filmmaske als Bildfeld (`crop=uncertain` in der Beschreibung).
11a. **Kantenprofile.** Zum gefundenen Bildfeld werden über das umschließende Rechteck der Filmmaske zwei Profile festgehalten, je Spalte und je Zeile der Vorschau: der Median des Dichteschritts zur nächsten Spalte bzw. Zeile (deutlich von 0 verschieden nur, wo eine gerade Kante über den größten Teil des Films läuft; positiv, wo unbelichteter Film in Bild übergeht, also am Anfang eines Bildfelds, negativ an seinem Ende) und ob die Spalte bzw. Zeile unbelichteter Film ist (entlang des Films die Stege aus Schritt 8, quer dazu die Randzeilen aus Schritt 7). Der Rollen-Kontext braucht sie, um ein Bildfeld bekannter Größe zu platzieren (Schritt 3.7).
12. **Zuschnitt** (Bereich 2). Das Bildfeld wird auf die verwendete Auflösung skaliert und je Seite um 1 % seiner längeren Seite nach innen gezogen (bei einem extrem schmalen Bildfeld nur so weit, dass von der kürzeren Seite ein Pixel bleibt).
13. **Inneres Fenster** (Bereich 3). Der Zuschnitt aus Schritt 12 ohne `measure_inset` (10 %) seiner Höhe und Breite je Seite.
14. **Filmbasis `d_min`** (Bereich 1). Je Kanal das `dmin_percentile`-Perzentil (0,2 %) der Dichte über die ganze entzerrte Filmmaske (Bildfelder, Stege, Filmrand; kein Halter). Signatur = (d_min_R − d_min_G, d_min_B − d_min_G): der Farbton der Filmbasis, verwendet für die Rollen-Gruppierung.
15. **Weißpunkt `d_white`** (Bereich 3). Je Kanal das `white_percentile`-Perzentil (99,5 %) der Dichte im inneren Fenster. *Helle Bildränder:* Himmel und helle Vordergründe liegen oft im äußeren Ring eines Bildes und würden, nur innen gemessen, über dem Weißpunkt liegen und ausfressen. Bei sicherem Zuschnitt wird deshalb dasselbe Perzentil auch auf fast dem ganzen Zuschnitt gemessen (je Seite 3 % ausgelassen, nur Pixel der Filmmaske); es darf den Weißpunkt je Kanal um höchstens `edge_white` (0,10) anheben und nie senken. Mehr als das ist eher ein Halterrand oder ein dichter Saum als Bild; ein solcher Saum dunkelt das Bild damit um höchstens diesen Betrag ab. `edge_white = 0` schaltet das ab.
16. **Farbe oder SW** (Bereich 2). Die Dichte des Zuschnitts wird wie in Durchgang 2, Schritt 3 normiert (mit eigenem `d_min` und `d_white` dieses Bildes), über Blöcke von 4 × 4 Pixeln gemittelt; je Block die mittlere absolute Abweichung der drei Kanäle von ihrem Mittel. Ist das 99,9-%-Perzentil dieser Abweichungen < `bw_threshold` (0,03), ist das Bild SW; schon ein kleiner Anteil klar farbiger Details entscheidet also für Farbe.
17. **Look-Statistik** (Bereich 3). Der Zuschnitt der Vorschau wird genau wie in Durchgang 2, Schritte 3, 4 und 7–10 entwickelt (eigenes `d_min`, `d_white`, Gamma nach dem eigenen Farbe/SW-Ergebnis, Schwarzpunkt im inneren Fenster, Kamera → sRGB bzw. gewichteter Grauwert bei SW, sRGB-Kurve). Filmbasis und Farbe/SW sind dabei immer die eigenen Werte aus Durchgang 1, auch wenn der Rollen-Kontext sie später ändert (High-Key-Fallback, Mehrheit für Farbe/SW); der Median der Gruppe dämpft diesen Unterschied. Im inneren Fenster, jedes 4. Pixel in beiden Richtungen: **Spread** = 95-%- minus 5-%-Perzentil der Luminanz (Rec.-709-Gewichte 0,2126, 0,7152, 0,0722), **Chroma** = Mittel von (größter − kleinster Kanal) je Pixel (0 bei SW). Alle Werte werden vorher auf 0–1 begrenzt.
18. **Stichproben für Farbübergang und Look** (Bereich 3). Die Dichte des inneren Fensters wird in Rasterreihenfolge auf jedes s-te Pixel ausgedünnt, s = ⌈Pixelzahl / 87 381⌉ (höchstens 1 MiB je Bild), dazu die Dichte des Look-Rasters aus Schritt 17 (inneres Fenster, jedes 4. Pixel). Beide werden bis zum Rollen-Kontext aufbewahrt (Schritte 3.4 und 3.5) und danach verworfen. Bis dahin braucht der Lauf je Datei im Ordner etwa 1,3–2,3 MiB zusätzlich (100 Dateien ≈ 130–230 MiB).

### 3. Rollen-Kontext

Gilt für die Dateien eines Laufs, die Durchgang 1 bestanden haben, in Namensreihenfolge.

1. **Gruppierung nach Filmbasis.** Zwei Bilder sind Nachbarn, wenn ihre Signaturen (Schritt 2.14) näher als `hue_tol` (0,06, euklidischer Abstand) liegen. Gruppen entstehen durch Verkettung (Single Linkage): Sind A–B und B–C Nachbarn, bilden A, B und C eine Gruppe. Bilder desselben Films unter demselben Licht landen in einer Gruppe.
2. **High-Key-Fallback** (Gruppen mit ≥ 2 Bildern). Verglichen werden die `d_min`-Werte auf einem gemeinsamen Maßstab: Ein länger belichteter Scan misst jede Dichte um den Logarithmus des Faktors niedriger; ist die Scan-Belichtung (Schritt 2.1) für alle Bilder der Gruppe bekannt, wird sie deshalb zu `d_min` addiert (und beim Übernehmen der Basislinie wieder abgezogen). Fehlt sie bei einem Bild, werden die gemessenen Werte verglichen. Basislinie = 25-%-Quantil je Kanal dieser Werte der Gruppe. Ein Bild nutzt die Basislinie statt seines eigenen `d_min` nur, wenn alles gilt: In jedem Kanal liegt sein `d_min` mehr als `highkey_delta` (0,10) über der Basislinie; die Anhebung ist gleichmäßig (größte ≤ `uniform_ratio` (2,0) × kleinste); seine Signatur liegt näher als `hue_tol` an der Median-Signatur der Gruppe. Nach unten wird nie korrigiert. Grund: In einem sehr hellen Bild (Schnee, Himmel) sind selbst die klarsten Pixel keine Filmbasis; die Rolle kennt die echte Basis. Die Beschreibung lautet dann `fallback=yes`.
3. **Farbe oder SW je Rolle.** In einer Gruppe mit ≥ 2 Bildern entscheidet die Mehrheit: mehr als die Hälfte SW → alle SW, sonst alle Farbe (Gleichstand ergibt Farbe). Ein farbloses Motiv auf Farbfilm bleibt so Farbe. Einzelbilder behalten ihr eigenes Ergebnis. Ein überstimmtes Bild bekommt eine Log-Zeile.
4. **Look-Parameter.** Grundlage ist die Look-Statistik des um den Farbübergang (Schritt 3.5, zuerst bestimmt) korrigierten Vorschaubilds: bei k ≠ 1 wird sie auf dem Look-Raster (Schritt 2.18) mit k neu gemessen, sonst gilt die aus Schritt 2.17. Keine Belichtungskorrektur; jedes Bild bekommt den Grundkontrast `contrast` und die Grundsättigung `saturation`, dazu je Gruppe eine Zugabe aus dem Median-Spread und der Median-Chroma ihrer Bilder (Bilder mit High-Key-Fallback bleiben außen vor, solange die Gruppe andere hat); Einzelbilder nutzen ihre eigenen Werte. Formeln: [Korrektur im Detail](#5-korrektur-im-detail).
5. **Farbübergang (Schichtsteilheit).** Die drei Farbschichten eines Farbnegativs haben leicht verschiedene Gradationskurven: Filmbasis und Weißpunkt sind nach der Kanal-Normierung neutral, die Mitteltöne nicht (typisch: das ganze Bild etwas zu warm). *Je Farbbild:* Auf der Stichprobe (Schritt 2.18) gilt x_c = (D_c − d_min_used_c) / max(d_white_c − d_min_used_c, 0,05), gemessen also mit der tatsächlich verwendeten Filmbasis (auch nach High-Key-Fallback) und dem tatsächlich verwendeten Weißpunkt (Schritt 3.6). Mittelgrau sind die Pixel mit |x_G − 0,5| < 0,05; sind es (hochgerechnet auf das ganze innere Fenster) weniger als 200, wird nicht gemessen (k_Bild = 1). Sonst ist mid_c der Median von x_c dieser Pixel und k_Bild_c = ln 0,5 / ln(mid_c, begrenzt auf 0,05–0,95) für R und B; G behält 1. *Je Rollen-Gruppe:* Ein Rollenwert gilt nur bei ≥ 3 gemessenen Farbbildern, von denen für R und für B je ≥ 80 % auf derselben Seite von 0,5 liegen wie der Gruppenmedian; dann k_Rolle aus den Gruppenmedianen der mid-Werte (gleiche Formel), sonst k_Rolle = 1. *Ergebnis:* k_c = clip(k_Rolle_c, 1 ± `crossover_roll_limit` (0,30)) · clip(sqrt(k_Bild_c / k_Rolle_c), 1 ± `crossover_limit` (0,10)). Ohne Begrenzung ist das sqrt(k_Bild_c · k_Rolle_c); begrenzt werden beide Teile getrennt: der Wert der Rolle weit (er stützt sich auf viele Bilder), die Abweichung des einzelnen Bildes eng (sie kann Motivfarbe sein: Schnee, warmes Abendlicht). Ein Bild ohne gültigen Rollenwert (k_Rolle = 1) bekommt die halbe Korrektur (im Logarithmus), höchstens ± `crossover_limit`. SW-Bilder: k = 1. `crossover_limit = 0` schaltet die Korrektur ab.

6. **Farbe des Weißpunkts.** Der Weißpunkt eines Bildes ist die Dichte seiner hellsten Stelle je Kanal. Seine Höhe (Mittel der drei Kanäle über der Filmbasis) gehört zum Bild, das Verhältnis der Kanäle zueinander aber zum Film – außer die hellste Stelle ist farbig (blauer Himmel, eine Lampe): Dann würde das eigene Verhältnis genau diese Farbe zu Weiß machen. In einer Gruppe mit ≥ 3 Farbbildern gilt deshalb je Bild: Verhältnis r_c = d_hi_c / Mittel(d_hi) mit d_hi = max(d_white − d_min_used, 0,05); Rollenwert = Median der r_c über die Farbbilder der Gruppe (auf Mittel 1 normiert); verwendet wird Rollenwert · clip(sqrt(r_Bild / r_Rolle), 1 ± `white_limit` (0,10)), wieder auf Mittel 1 normiert, mal die eigene Höhe. SW-Bilder, kleinere Gruppen und `white_limit = 0` behalten den eigenen Weißpunkt.
7. **Bildgröße der Rolle.** Alle Bilder einer Rolle haben dieselbe Größe und dasselbe Format. Ein dunkler Bildrand (Nachthimmel, schwarze Wand) sieht aus wie unbelichteter Film, sodass ein einzelnes Bild dort abgeschnitten wird, auf ein kleineres Format einrastet oder gar kein Bildfeld findet. Hat eine Gruppe ≥ 3 sichere Bilder desselben Formats und derselben Lage (Quer/Hoch), deren Größen innerhalb von 3 % um ihren Median liegen, ist deren Median die Bildgröße der Rolle. Zwei Arten von Bildern der Gruppe bekommen diese Größe: (a) ein sicheres Bild, das in einer Richtung um mehr als 3 % kleiner und in keiner größer ist – es wurde abgeschnitten, das Bildfeld der Rolle muss das gefundene ganz enthalten; (b) ein unsicheres Bild (ganzer Filmstreifen), wenn das Bildfeld der Rolle darin in beiden Richtungen an beiden Enden auf einer klaren Kante liegt (≥ 2,5 × typischer Kantenwert). Platziert wird je Achse mit den Kantenprofilen (Schritt 2.11a): dort, wo am Anfang eine steigende und am Ende eine fallende Kante am stärksten sind (± 2 Vorschau-Pixel), ohne unbelichtete Linien in der Mitte (das wäre der Steg zum Nachbarbild). Ein sicheres Bild, das in einer Richtung größer ist, wird nie verändert (es kann ein anderes Format sein); lässt sich ein Bild nicht platzieren, bleibt es, wie es ist. Der Grund des Zuschnitts nennt dann `frame size of the roll (<Format>) used instead of the frame's own (<Format>)`. Dieser Schritt wird als erster bestimmt: Jedes Bild, das so ein anderes Bildfeld bekommt, durchläuft Durchgang 1 noch einmal mit diesem Bildfeld (die Filmbasis bleibt dieselbe), sodass Weißpunkt, Farbe/SW, Farbübergang und Look-Statistik aus dem endgültigen Zuschnitt und seinem inneren Fenster stammen; erst danach folgen die Schritte 1–6.
8. **Hinweise zum ganzen Lauf.** *Scan-Belichtung:* Die Filmbasis ist die hellste Stelle eines Negativs. Liegt ihr hellster Kanal im Median einer Gruppe unter einem Achtel des Sensorbereichs (10^−min(d_min) < 0,125), meldet der Lauf „Die Scans sind dunkel belichtet (der Filmrand nutzt weniger als ein Achtel des Sensorbereichs): länger belichten verringert das Bildrauschen.“; erreicht er 0,98, „Die Scans sind zu hell belichtet (der Filmrand ist übersteuert): kürzer belichten, sonst stimmen die Farben nicht.“ *Kamera nicht senkrecht:* Weicht der Median der Kantenunterschiede (Schritt 2.5) über mindestens 3 Bilder des Laufs um mehr als 0,4° von 0 ab, „Gegenüberliegende Bildkanten sind nicht parallel (um etwa X°): Die Kamera steht nicht genau senkrecht über dem Film.“ *Flat-Field passt nicht:* Hat die Referenz ein anderes Seitenverhältnis als Scans des Laufs, „Die Flat-Field-Referenz hat ein anderes Seitenverhältnis als N der Scans (andere Kamera oder Kamera gedreht): Diese Bilder wurden ohne sie entwickelt.“ Die Hinweise stehen im Log (WARNING), in der Konsole, bei „Negative entwickeln“ als zusätzliche Zeilen im Ergebnisfenster; an den Bildern ändern sie nichts.

### 4. Durchgang 2: Entwicklung und Ausgabe jeder Datei

In voller Auflösung, parallel; die Schritte einer Datei laufen in dieser Reihenfolge.

1. **Laden.** Wie in Durchgang 1, Schritt 1 (samt Flat-Field), aber in voller Auflösung und mit ausgeglichenen Kanälen: Für das Demosaicing wird jeder Kanal auf das Niveau des stärksten gehoben (Faktor = Durchlass der Filmbasis `d_min_used` im stärksten Kanal geteilt durch den im jeweiligen Kanal, höchstens 16) und danach wieder zurückgerechnet. Die Werte bleiben dieselben; aber neben starken Kanälen rekonstruiert das Demosaicing einen schwachen mit Fehlern, die so groß sind wie sein Signal, und die nach der Umkehrung als einzelne falsche Pixel erscheinen. Werte bis zur Filmbasis bleiben unberührt; helleres (blankes Licht neben dem Film) kann in den angehobenen Kanälen begrenzt werden.
2. **Dichte und Entzerren.** D = −log10(max(T, 1/65535)) je Kanal. Das Dichtebild wird um den Winkel aus Durchgang 1 um die Mitte gedreht (Lanczos über 8 × 8 Pixel, Ränder fortgesetzt): Korn und feine Details bleiben so scharf wie in Bildern, die keine Drehung brauchen. Gedreht werden die Dichten und nicht das Positiv, weil Staub und Halter dort nur wenige Dichte-Einheiten vom Bild entfernt sind, im unbeschnittenen Positiv aber tausendfach heller; jedes Ergebnis wird zusätzlich auf den Wertebereich der 3 × 3 Quellpixel um seinen Ort begrenzt, sodass der scharfe Filter keine Säume oder Muster um solche Stellen legt.
3. **Neutralisierung und Kanal-Normierung.** `d_min_used` = Filmbasis aus dem Rollen-Kontext, `d_white` = Weißpunkt aus dem Rollen-Kontext (Schritt 3.6), sonst der aus Durchgang 1. Je Kanal d_hi = max(d_white − d_min_used, 0,05), D_target = Mittel der drei d_hi, D_norm = max(D − d_min_used, 0) · D_target / d_hi. Der Abzug der Filmbasis entfernt die orange Maske; die Skalierung gibt allen drei Kanälen denselben Dichteumfang, sodass Filmbasis und Weißpunkt neutral werden.
4. **Farbübergang und lineares Licht.** x = D_norm / D_target je Kanal, x' = x^k_c mit k aus Schritt 3.5 (Filmbasis 0 und Weißpunkt 1 bleiben fest, nur die Mitteltöne verschieben sich), dann Y = 10^((x' · D_target − D_target) / γ) mit γ = `gamma_color` (0,6) bzw. `gamma_bw` (0,65) gemäß der Rollen-Entscheidung. Der Weißpunkt wird 1,0, die Filmbasis der dunkelste Wert. Die Korrektur gehört zur Umkehrung, nicht zum Look: DNG, TIFF und JPEG enthalten sie gleichermaßen.
5. **Bildfeld.** Das Bildfeld ist das aus dem Rollen-Kontext (Schritt 3.7), sonst das aus Durchgang 1.
6. **Ausrichtung.** Erst horizontal spiegeln (`mirror`), dann im Uhrzeigersinn um `rotate` drehen; das Zuschnitt-Rechteck folgt.
7. **Schwarzpunkt** (Bereich 3). b = 0,5-%-Perzentil der Luminanz (Mittel der Kanäle, jedes 4. Pixel) im inneren Fenster des ausgerichteten Zuschnitts. Wenn 0 < b < 0,99: Y = (Y − b) / (1 − b), derselbe Versatz für alle Kanäle. Die Werte werden hier nicht begrenzt: Was über dem Weißpunkt liegt, bleibt über 1, was unter dem Schwarzpunkt liegt, unter 0 (für das DNG).
8. **SW.** Bei SW-Bildern werden die drei Kanäle zu einem zusammengefasst, gewichtet mit der Durchlässigkeit der Filmbasis je Kanal: Gewicht_c = 10^−d_min_used_c, auf Summe 1 normiert. Die drei Kanäle eines Silberbilds zeigen dasselbe Bild, aber ein Kanal, der durch Filmbasis, Lampe und Sensor weniger Licht bekommt, rauscht stärker.
9. **Farbraum** (nur Zuschnitt, für TIFF und JPEG). Farbe: Die Werte werden auf 0–1 begrenzt, dann Kamera-RGB → lineares sRGB mit der Kameramatrix (dcraw-Verfahren: (XYZ → Kamera) · (sRGB → XYZ, D65), Zeilen so normiert, dass Neutral neutral bleibt, invertiert; unbrauchbare Matrix → Einheitsmatrix und eine Warnung). Negative Werte werden 0. SW: Der Grauwert aus Schritt 8 (gewichtete Summe der unbegrenzten Kanäle) geht ohne Matrix weiter; begrenzt wird er erst in Schritt 10.
10. **sRGB-Kurve** (nur Zuschnitt). Werte auf 0–1 begrenzt, dann die Standard-sRGB-Übertragungsfunktion (IEC 61966-2-1). Das Ergebnis ist das sRGB-Bild vor der Korrektur.
11. **Beschreibung.** Eine Zeile, z. B. `rffilmlab 26.11.3 | color | dmin=0.415,0.437,0.908 | fallback=no | crop=1:1 | crossover: R x1.102 B x0.874 (frame+roll) | crop: …` (Farbe/SW, verwendete Filmbasis, Rollen-Fallback, eingerastetes Format oder `uncertain`; Farbübergang mit k für R und B und Herkunft `frame+roll`, `frame only`, `roll only` oder `none` (keine Korrektur), fehlt bei `crossover_limit = 0`; am Ende `| crop: …` mit der Begründung des Zuschnitts). Die Log-Zeile ab `-v` lautet `<Datei>: crop <B>×<H>, crossover R x… B x… (…) — <Grund>`. Sie steht in allen drei Dateien (`ImageDescription`) und im Log.
12. **DNG** (wenn `dng = true`). Das *ganze* entzerrte und ausgerichtete Bild nach den Schritten 3–8 (linear, Kamera-RGB, Schwarzpunkt 0, Weißpunkt 1; SW als drei gleiche Kanäle) mit der Korrektur (Abschnitt 5), nicht beschnitten. **Korrektur im DNG:** Je Pixel wird der Wert mit der Kameramatrix aus Schritt 9 nach linearem sRGB gerechnet (SW: der Grauwert, ohne Matrix), der Teil in 0–1 mit der sRGB-Kurve kodiert, genau wie das TIFF korrigiert und wieder linearisiert, der Teil außerhalb von 0–1 unverändert wieder addiert (Steigung 1) und das Ergebnis mit der inversen Matrix zurück nach Kamera-RGB gebracht. Mit ColorMatrix1 nach sRGB umgerechnet und kodiert, ergibt das DNG im Bereich 0–1 die Werte des TIFF: bei SW genau (bis auf die float16-Rundung), bei Farbe ebenso, außer bei Pixeln, in denen ein Kamerakanal außerhalb von 0–1 liegt – das TIFF begrenzt die Kamerawerte vor der Farbmatrix, das DNG behält sie. An echten Bildern beträgt die mittlere Abweichung im Bereich 0–1 weniger als 0,0001 auf der Skala 0–1. Außerhalb von 0–1 setzt sich die Kurve mit Steigung 1 fort, ohne Begrenzung: Lichter über dem Weißpunkt und Schatten unter dem Schwarzpunkt bleiben für die spätere Bearbeitung unverändert erhalten. An den Enden 0 und 1 ist die Kurve stetig, ihre Steigung dort 1 − Kontrast. **Formate:** `dng_finder_preview = false` (Standard): float16, unbegrenzt, Deflate mit Gleitkomma-Prädiktor, Kacheln 256 × 256 (nur NaN/Unendlich werden ersetzt und Werte auf den float16-Bereich ±65504 begrenzt; Programme können Werte unter 0 beim Öffnen auf 0 setzen). `true`: uint16 unkomprimiert, auf 0–1 begrenzt (0–65535, BlackLevel 0, WhiteLevel 65535), damit Finder und Quick Look es anzeigen. Das erste Bild der Datei ist eine 8-bit-sRGB-Vorschau des korrigierten, beschnittenen Bildes (dasselbe Bild wie das TIFF, lange Kante ≤ 1024 px), das Hauptbild folgt als SubIFD. Tags: DNGVersion 1.4.0.0, UniqueCameraModel (Hersteller und Modell per exiftool, sonst `real-fast-filmlab`), ColorMatrix1 = Kameramatrix, zeilenweise so skaliert, dass D65-Weiß die Kamerawerte (1, 1, 1) ergibt (die entwickelten Daten sind bei gleichen Kamerawerten neutral; ein Programm, das den DNG-Regeln folgt, leitet daraus D65 als Weißpunkt ab und erhält die Farben des TIFF), CalibrationIlluminant1 = D65, AsShotNeutral = (1, 1, 1), BaselineExposure = 0, Orientation = 1, dazu ein eingebettetes Profil für bereits entwickelte Daten: ProfileName `rffilmlab linear`, ProfileToneCurve linear (0,0 – 1,1), DefaultBlackRender = keiner, BaselineExposureOffset = 0, ProfileEmbedPolicy ohne Einschränkung. Der Zuschnitt steht als eingebettetes Camera-Raw-XMP darin (`crs:ProcessVersion 11.0`, `HasCrop`, `CropTop/Left/Bottom/Right` relativ 0–1, `CropAngle 0`, `AlreadyApplied False`): In Lightroom oder Camera Raw lässt er sich zurücksetzen oder bis zum vollen Scan aufziehen.
13. **TIFF.** Das beschnittene sRGB-Bild mit der Korrektur (Abschnitt 5). 16 bit, Deflate mit Prädiktor; Farbe als RGB mit eingebettetem sRGB-Profil, SW als ein Graukanal mit eingebettetem Graustufenprofil (sRGB-Kurve, D50): Ohne Profil nehmen farbverwaltete Programme ihren eigenen Grauraum an und zeigen SW-Bilder dunkler oder heller als die Farbdateien.
14. **JPEG.** Dasselbe korrigierte Bild wie das TIFF, nur komprimiert (kein zweiter Rechenweg). 8 bit, Qualität `jpeg_quality` (95); Farbe mit sRGB-Profil und Farbe in voller Auflösung (4:4:4; die übliche Halbierung der Farbkanäle verschmiert Farbkorn und feine farbige Details), SW als Graustufen mit dem Graustufenprofil. Mit `jpeg_sharpen = true` wird nur das JPEG vorher leicht geschärft: y = x + 0,5 · (x − Gauß-Unschärfe(x, Sigma 1 Pixel)), auf 0–1 begrenzt.
15. **EXIF.** Ist exiftool vorhanden, werden alle Metadaten des RAW in jede Ausgabe kopiert (`-TagsFromFile … -all:all`), außer MakerNotes, Orientation, ImageDescription, Software, ImageWidth/ImageHeight, ExifImageWidth/ExifImageHeight und ColorSpace (sie beschreiben das RAW, nicht das beschnittene Bild), Camera-Raw-Einstellungen (`XMP-crs`) und den DNG-eigenen Farb-, Darstellungs- und Rohdaten-Tags (`DNG_TAGS` in `fileio/exiftool.py`), damit ein DNG als Eingabe nie seine Kameramatrix, sein Profil, seine Kalibrierung, seine Schwarz-/Weißwerte oder seinen Zuschnitt in unser DNG schreibt: DNGVersion, DNGBackwardVersion, DNGPrivateData, DNGAdobeData, UniqueCameraModel, LocalizedCameraModel, ColorMatrix1, ColorMatrix2, ColorMatrix3, CameraCalibration1, CameraCalibration2, CameraCalibration3, CameraCalibrationSig, ReductionMatrix1, ReductionMatrix2, ReductionMatrix3, ForwardMatrix1, ForwardMatrix2, ForwardMatrix3, CalibrationIlluminant1, CalibrationIlluminant2, CalibrationIlluminant3, IlluminantData1, IlluminantData2, IlluminantData3, AnalogBalance, AsShotNeutral, AsShotWhiteXY, AsShotICCProfile, AsShotPreProfileMatrix, AsShotProfileName, BaselineExposure, BaselineExposureOffset, BaselineNoise, BaselineSharpness, LinearResponseLimit, DefaultBlackRender, NoiseProfile, ProfileName, ProfileCopyright, ProfileEmbedPolicy, ProfileCalibrationSig, ProfileDynamicRange, ProfileGroupName, ProfileType, ProfileGainTableMap, ProfileGainTableMap2, ProfileHueSatMapDims, ProfileHueSatMapData1, ProfileHueSatMapData2, ProfileHueSatMapData3, ProfileHueSatMapEncoding, ProfileLookTableDims, ProfileLookTableData, ProfileLookTableEncoding, ProfileToneCurve, RawToPreviewGain, MakerNoteSafety, OpcodeList1, OpcodeList2, OpcodeList3, ActiveArea, MaskedAreas, BlackLevel, BlackLevelRepeatDim, BlackLevelDeltaH, BlackLevelDeltaV, WhiteLevel, LinearizationTable, ShadowScale, BayerGreenSplit, AntiAliasStrength, ChromaBlurRadius, BestQualityScale, DefaultScale, DefaultCropOrigin, DefaultCropSize, DefaultUserCrop, ColumnInterleaveFactor, RowInterleaveFactor, RawImageDigest, NewRawImageDigest, OriginalRawFileData, OriginalRawFileDigest, RawImageSegmentation, ColorimetricReference, CacheVersion, EnhanceParams, DepthFormat, DepthNear, DepthFar, DepthUnits, DepthMeasureType, SemanticName, SemanticInstanceID, JXLDistance, JXLEffort, JXLDecodeSpeed; Vorschaubilder des RAW werden nicht übernommen, Orientation wird auf 1 gesetzt, bei TIFF und JPEG ColorSpace auf sRGB. Der Kameraname im DNG ist „Hersteller Modell“; nennt das Modell den Hersteller schon (Canon / Canon EOS R5), steht er nur einmal da. Ein Fehler hier ergibt nur eine Warnung.
16. **Schreiben.** Jede Datei wird zuerst als `.<name>.tmp.<pid>.<zufall><endung>` neben dem Ziel geschrieben auf den Datenträger geschrieben (fsync) und bekommt dann in einem Schritt ihren Namen; eine halb geschriebene Datei trägt nie den endgültigen Namen. Der Name wird dabei exklusiv vergeben (harter Link, sonst eine leere Platzhalterdatei, die ersetzt wird): Eine Datei, die inzwischen unter diesem Namen entstanden ist, wird nie ersetzt. In dem Fall bekommen alle drei Ausgaben dieses Bildes den nächsten freien Namen (bis zu 5 Versuche).
17. **Archiv.** Das Original wird nach `Archiv/` verschoben (`<name>_2.<endung>` usw., wenn der Name belegt ist). Der Name wird exklusiv vergeben, auch wenn zwei Läufe gleichzeitig dasselbe Archiv benutzen: Auf demselben Laufwerk bekommt die Datei dort einen zweiten Namen (harter Link) und verliert den alten; ohne harte Links (exFAT, manche Netzlaufwerke) wird der Name mit einer leeren Datei reserviert, die das umbenannte Original ersetzt. Auf ein anderes Laufwerk wird die Datei zuerst als `.<name>.<endung>.tmp.<pid>.<zufall>` in `Archiv/` kopiert, auf den Datenträger geschrieben (fsync), dann auf den reservierten Namen umbenannt und erst danach am alten Ort gelöscht; scheitert das Löschen, wird die Kopie wieder entfernt. Eine halb kopierte Datei trägt also nie den endgültigen Namen. Erst jetzt gilt die Datei als erledigt (Log-Zeile `OK <name> - <Beschreibung>`).
18. **Fehler.** Scheitert etwas in den Schritten 1–17, werden die bereits geschriebenen Ausgaben dieser Datei wieder gelöscht. Ist die Datei selbst schuld (RAW unlesbar oder beschädigt, JPEG lässt sich nicht kodieren, sonstiger Fehler bei Analyse oder Entwicklung), wandert das Original nach `Negative/_Fehler/` mit einer Textdatei `<name>.txt`: „<name> konnte nicht verarbeitet werden.“, „Grund: …“ (einfaches Deutsch: RAW unlesbar oder beschädigt, RAW einer Kamera ohne Farbfilter, sonst „Unerwarteter Fehler.“), „Technisch: …“ (Text der Ausnahme) und „Zeitpunkt: …“. Liegt der Grund in der Umgebung – ein Fehler des Dateisystems (kein Speicherplatz, keine Berechtigung, schreibgeschützt, Lese-/Schreibfehler, Ordner oder Laufwerk nicht mehr da) oder zu wenig Arbeitsspeicher (auch in LibRaw) –, bleibt das Original unverändert in `Negative/`; das gilt auch, wenn das RAW aus einem dieser Gründe nicht gelesen werden konnte. Eine fehlerhafte Datei hält den Lauf nie an; nur ein voller Datenträger oder ein Ordner bzw. Laufwerk, das während des Laufs verschwindet (z. B. getrenntes externes Laufwerk; vor jeder Datei wird geprüft, ob alle drei Ordner noch da sind), beendet den Lauf: Die übrigen Dateien bleiben unberührt in `Negative/`, fertige Dateien bleiben fertig. Die Meldung lautet dann „Kein Speicherplatz mehr frei. Verarbeitung angehalten: …“ bzw. „Ordner oder Laufwerk nicht mehr erreichbar – ist das Laufwerk angeschlossen? Verarbeitung angehalten: …“. Ein RAW, das während des Laufs aus `Negative/` gelöscht wird, wird still übersprungen (nur eine Log-Zeile `SKIPPED <name>`; kein Fehler, keine Meldung). Auch jeder andere Fehler, der auftritt, während einer der drei Ordner fehlt, gilt als Fehler der Umgebung; `_Fehler/` wird nie in einem verschwundenen Ordner neu angelegt. Wird das Programm mitten in einer Datei beendet (Update, Abmeldung, Stromausfall), bleibt deren RAW in `Negative/`; der nächste Lauf löscht die schon geschriebenen Ausgaben dieser Datei und entwickelt sie unter demselben Namen neu (Merker je Datei in Arbeit im Programmdatenordner unter `pending/`; er nennt nur die Ausgaben, die wirklich geschrieben wurden, und gilt nur für genau dieses RAW: Hat die Datei inzwischen eine andere Größe oder Änderungszeit, wird nichts gelöscht).

Nach dem Lauf: Zusammenfassung im Log, Konsolenausgabe `N umgewandelt, M fehlgeschlagen` (Exit-Code 1, wenn etwas fehlschlug) und bei Dateien, die wegen der Umgebung in `Negative/` blieben, eine Zeile mit dem Grund, z. B. „Kein Speicherplatz mehr frei. Verarbeitung angehalten: 3 Fotos fertig, die übrigen Negative bleiben im Ordner „Negative“.“ oder „Keine Berechtigung zum Schreiben/Lesen. 1 Negativ bleibt unverändert im Ordner „Negative“; 11 Fotos fertig.“ Die Meldungen nennen den eingestellten Ordner beim Namen. Mitteilung „N Fotos fertig, M Fehler“, bei Fehlern mit „– Details in Negative/_Fehler“; blieben Dateien wegen der Umgebung liegen, steht dort stattdessen dieser Grund und danach die Zahl der Dateien in `_Fehler`. Sie erscheint, wenn `notify = true` und etwas verarbeitet wurde; der Watch-Modus zeigt denselben Grund nicht noch einmal, solange kein Bild fertig wird.

### 5. Korrektur im Detail

Steckt in TIFF und JPEG, auf beide gleich (ein Bild wird einmal korrigiert und zweimal geschrieben), und im DNG (Schritt 4.12: dieselbe Korrektur auf den linearen Daten, Werte außerhalb von 0–1 bleiben erhalten). Im Code heißt sie „look“ (`core/look.py`). Sie ändert die Helligkeit nie: kein Auf- oder Abhellen, keine Belichtungskorrektur. Sie hat zwei Teile:

- **Grundwert** für jedes Bild: `contrast` (0,30) und `saturation` (1,15). Das neutrale Bild ist szenenlinear und wirkt ohne Wiedergabekurve flau; Kamera-JPEGs und Entwicklungsprogramme legen aus demselben Grund eine Kontrastkurve darüber.
- **Zugabe** für flaue oder blasse Rollen, aus den Messwerten unten.

**Eingaben der Zugabe.** Zwei Messwerte je Bild, gemessen auf dem neutralen sRGB-Vorschaubild des Zuschnitts (nach Farbübergang, Schwarzpunkt, Kameramatrix und sRGB-Kurve; Schritt 2.17 bzw. Schritt 3.4 mit neu gemessenem k) im inneren Fenster (`measure_inset`), jedes 4. Pixel (`SAMPLE_STEP`), Werte auf 0–1 begrenzt:

- **Spread** = 95-%- minus 5-%-Perzentil der Luminanz (Gewichte 0,2126, 0,7152, 0,0722).
- **Chroma** = Mittel von (größter − kleinster Kanal) je Pixel; bei SW 0.

**Rollen-Gruppe.** Spread und Chroma, aus denen die Zugabe folgt, sind der Median über alle Bilder der Gruppe (Bilder mit High-Key-Fallback zählen nicht, solange die Gruppe andere hat); ein Einzelbild nutzt seine eigenen Werte. Alle Bilder einer Gruppe bekommen damit dieselben Parameter, und eine Rolle sieht gleichmäßig aus.

**Formeln und Konstanten** (alle in `core/look.py`):

| Schritt | Formel | Konstanten |
|---------|--------|------------|
| Kontrast | s = min(`MAX_TOTAL_CONTRAST`, `contrast` + Stärke · clip(`SPREAD_TARGET` − Spread, 0, `MAX_CONTRAST`)) | `SPREAD_TARGET` = 0.70, `MAX_CONTRAST` = 0.35, `MAX_TOTAL_CONTRAST` = 0.8 |
| Stärke der Zugabe | Farbe 1.0, SW 0.5 | `COLOR_STRENGTH`, `BW_STRENGTH` |
| S-Kurve | y = (1 − s) · x + s · x² / (x² + (1 − x)²), je Kanal | – |
| Sättigung (nur Farbe) | sat = min(`MAX_TOTAL_SATURATION`, `saturation` · clip(1 + `SAT_GAIN` · (`CHROMA_TARGET` − Chroma), 1, `MAX_SATURATION`)) | `CHROMA_TARGET` = 0.10, `SAT_GAIN` = 1.5, `MAX_SATURATION` = 1.15, `MAX_TOTAL_SATURATION` = 1.6 |
| Chroma-Gewichtung | c = größter − kleinster Kanal; Faktor = 1 + (sat − 1) · (1 − clip(c / `CHROMA_FULL`, 0, 1)); y = L + (x − L) · Faktor | `CHROMA_FULL` = 0.5 |

Zum Schluss werden alle Werte auf 0–1 begrenzt. Die S-Kurve lässt 0, 0,5 und 1 unverändert; ihre Steigung ist in der Mitte 1 + s und an beiden Enden 1 − s (nie 0: Schatten und Lichter behalten Zeichnung). Die Sättigung wirkt nur auf blasse Pixel (kleines c) voll, kräftige behalten ihre Farbe.

**Was sie nie tut:** keine Belichtungsänderung, kein Aufhellen dunkler oder Abdunkeln heller Aufnahmen, keine Farbtonänderung und keine Abhängigkeit vom Ausgabeformat (TIFF, JPEG und DNG bekommen dieselbe Korrektur). Die Normierung auf Weiß- und Schwarzpunkt je Bild (Schritte 4.4 und 4.7) gehört nicht zur Korrektur, sondern zur Umkehrung; sie wirkt auch im DNG. `contrast = 0` und `saturation = 1` lassen nur die Zugabe übrig.

**Wirkung an Beispielbildern** mit den Standardwerten (beschrieben nur durch ihre Messwerte; Zahlen aus den Formeln oben):

| Beispielbild | Spread | Chroma | Kontrast s | Sättigung |
|--------------|--------|--------|------------|-----------|
| Normales Farbnegativ mit vollem Tonumfang | 0.75 | 0.15 | 0.30 (nur Grundwert) | 1.15 |
| Leicht flaues Farbnegativ | 0.60 | 0.08 | 0.40 | 1.18 |
| Flaues, blasses Farbnegativ | 0.50 | 0.04 | 0.50 | 1.25 |
| Sehr flaues, farbarmes Farbnegativ | 0.30 | 0.02 | 0.65 | 1.29 |
| Flaues SW-Negativ (halbe Zugabe) | 0.50 | – | 0.40 | – |

Bei s = 0,30 wird der Grauwert 0,25 zu 0,205 und 0,75 zu 0,795, 0,50 bleibt 0,50. Bei Sättigung 1,15 wächst der Abstand eines blassen Pixels (c = 0,05) zu seinem Grauwert L um den Faktor 1,135; ein kräftiges (c ≥ 0,5) bleibt unverändert.

### Was das Programm nicht tut

- Keine KI, keine trainierten Modelle, keine Cloud. Einziger Netzwerkzugriff ist die Frage nach einer neuen Version (`update_check`, abschaltbar).
- Keine automatische Lageerkennung: `rotate`/`mirror` gelten für alle Dateien gleich (ein Wert je Scan-Aufbau).
- Keine Staub-, Kratzer- oder Rauschentfernung. Ohne Infrarot-Kanal (wie bei Flachbettscannern mit ICE) ist Staub nicht sicher von Bilddetails wie Lichtreflexen oder Sternen zu unterscheiden, und Korn gehört zum Film. Dafür eignen sich Bildbearbeitungsprogramme, in denen das Ergebnis geprüft werden kann. Tipp: Negative vor dem Abfotografieren entstauben und den Scan so belichten, dass die Filmbasis nicht zu dunkel wird (zu knapp belichtete Scans zeigen nach der Umkehrung deutlich mehr Rauschen).
- Kein Schärfen von TIFF und DNG; das JPEG nur auf Wunsch (`jpeg_sharpen`).
- Keine Korrektur einer schräg stehenden Kamera (nicht parallele Bildkanten): Sie wird nur gemeldet (Schritt 3.8).
- Keine manuellen Korrekturen je Bild und keine Bedienoberfläche; Feinarbeit erfolgt danach im DNG mit einem Programm nach Wahl.
- Kein Diafilm (Positive) und keine Filmprofile.
- Keine RAW-Dateien von Kameras ohne Farbfilter (Monochrom-Sensor): Sie landen mit diesem Grund in `_Fehler/`.
- Zeigt ein Scan mehrere Bildfelder, wird nur das breiteste ausgegeben.
- Sichtbare Perforation (Kleinbild) und Masken mit abgerundeter Öffnung werden nicht zuverlässig beschnitten; das DNG enthält das volle Bild. Große Flächen blanken Lichts im Film (Perforation) können zudem als Filmbasis gemessen werden; der Grund des Zuschnitts nennt das (Schritt 2.4).
- Keine Unterordner: nur Dateien direkt in `Negative/` werden verarbeitet.
- Es werden keine XMP-Begleitdateien geschrieben oder gelesen.

## Ausgaben

Je RAW `<name>.<endung>` entstehen in `Fotos/` drei Dateien (ohne DNG bei `dng = false`, ohne TIFF bei `tiff = false`; das JPEG immer):

| Datei | Inhalt | Zuschnitt | Farbe | Korrektur | Größe je Megapixel |
|-------|--------|-----------|-------|-----------|--------------------|
| `<name>.dng` | linear, float16 Deflate ohne Begrenzung auf 0–1 (oder uint16 unkomprimiert, 0–1), eingebettete Vorschau | voller Scan, Zuschnitt als zurücksetzbare Einstellung | Kamera-RGB mit Farbmatrix und linearem Profil | wie das TIFF; float16: Werte außerhalb 0–1 bleiben, unbegrenzt | ca. 3,6 MB (uint16: ca. 6,1 MB) |
| `<name>.tif` | 16 bit, sRGB-Kurve, Deflate | beschnitten | sRGB (SW: Grau mit Profil) | Abschnitt 5 | ca. 3,3 MB |
| `<name>.jpg` | 8 bit, Qualität 95, Farbe 4:4:4 | beschnitten | sRGB (SW: Grau mit Profil) | wie das TIFF | ca. 0,3–0,5 MB |

Die Größen wachsen mit der Pixelzahl und hängen vom Bildinhalt ab (Korn und Rauschen vergrößern TIFF und JPEG); die Tabelle gibt grobe Richtwerte je Megapixel an. Die drei Dateien eines RAW tragen immer denselben Namen. Existiert `<name>.dng`, `.tif` oder `.jpg` bereits in `Fotos/` (oder haben zwei RAWs eines Laufs denselben Namen), wird für alle drei `<name>_2`, `<name>_3` … verwendet. Nichts wird überschrieben, auch nicht, wenn zwei Läufe gleichzeitig in denselben Ordner schreiben oder während eines Laufs eine gleichnamige Datei dort abgelegt wird.

### Kontaktabzug

Mit `contact_sheet = true` schreibt jeder Lauf, der neue Bilder erzeugt hat (auch ein Lauf des Dienstes), eine Übersicht nach `Fotos/`: `_Kontaktabzug JJJJ-MM-TT HH-MM.jpg` (Ortszeit am Ende des Laufs; gibt es den Namen schon, `_2`, `_3` …). Sie zeigt alle JPEGs dieses Laufs als Vorschaubilder mit ihrem Dateinamen darunter: festes Raster mit 6 Spalten, nach Dateinamen sortiert, jedes Bild in ein Feld von 320 × 240 Pixeln eingepasst, Schrift ist die eingebaute Standardschrift von Pillow (auf allen Systemen dieselbe), lange Namen werden mit „…“ gekürzt. Bilder, die einen Blick verdienen, sind orange eingerahmt und tragen unter dem Namen den Grund: „Beschnitt unsicher“ (kein Bildfeld gefunden, ganzer Filmstreifen), „Beschnitt aus der Rolle“ (Schritt 3.7), „Filmbasis aus der Rolle“ (High-Key-Fallback, Schritt 3.2); ein Kontaktabzug ohne solche Bilder sieht aus wie immer. Die Datei wird zuerst unter einem temporären Namen geschrieben und erst vollständig umbenannt. Hat ein Lauf mehr als 300 Bilder, entstehen mehrere Kontaktabzüge zu je höchstens 300 Bildern in Namensreihenfolge: `_Kontaktabzug JJJJ-MM-TT HH-MM Teil 1.jpg`, `… Teil 2.jpg` usw. Ein Kontaktabzug erscheint in keinem späteren Kontaktabzug. Kann er nicht geschrieben werden, steht das im Log; die Bilder des Laufs sind davon nicht betroffen.

### Warum dieser Zuschnitt?

Jedes Bild nennt den Grund für Zuschnitt und Drehung, im Log und in den Dateien. Mit `-v` zeigt die Konsole eine Zeile pro Datei, die Log-Datei hat sie immer (INFO):

```
scan_0001.ARW: crop 6178×6178 — rotated 0.54° (frame edges); snapped to 1:1; width: left edge + right edge anchored, excess 4.3 % of the width taken from the left
```

Die Größe ist die Ausgabegröße in Pixeln. Der Grund nennt in dieser Reihenfolge nur das, was zutrifft: die Drehung (`rotated 0.54° (frame edges)`, `rotated 0.21° (film outline)`, `not rotated (abs angle 0.12° < 0.2°)`, `rotated pass uncertain, kept unrotated`), `bare light (no film) ignored for the film base`, `translucent holder strips removed (left 4.2 %, right 7.3 % of the image side)`, `patches of bare light inside the film (perforation?): …`, das Format (`snapped to 3:2` oder `no format (crop uncertain, full film area kept)`) und je Achse, welche Bildkanten verankert waren und wo der Überschuss abgenommen wurde (`height: bottom edge anchored, excess 3.2 % of the height taken from the top`). Hat der Rollen-Kontext das Bildfeld ersetzt, folgt `frame size of the roll (3:2) used instead of the frame's own (6x7)`. Größen im Grund sind Prozent der Bildseite entlang dieser Achse. Derselbe Text steht in der Bildbeschreibung von DNG, TIFF und JPEG nach `crop: ` (z. B. im exiftool-Feld `ImageDescription`; das Gradzeichen erscheint dort als `deg`).

## Befehle und Optionen

| Befehl / Option | Beschreibung |
|-----------------|--------------|
| `rffilmlab` | Ohne Befehl: `Negative/` einmal verarbeiten (wie `run`) |
| `rffilmlab run` | `Negative/` einmal verarbeiten |
| `rffilmlab watch` | Dauerhaft laufen und neue Dateien verarbeiten (Strg+C beendet) |
| `rffilmlab service install` | Hintergrunddienst einrichten und starten |
| `rffilmlab service status` | Zeigen, ob der Dienst eingerichtet ist und läuft, die beiden Log-Dateien und welches exiftool benutzt wird |
| `service status --summary` | Für Installer und Starter: gibt nur die Zeilen `service=<absent\|installed\|running\|stopped>` (nicht eingerichtet; eingerichtet, Lauf unbekannt; läuft; läuft nicht) und `exiftool=<Pfad oder leer>` aus |
| `rffilmlab service uninstall` | Hintergrunddienst entfernen |
| `rffilmlab config init --negative PATH --photos PATH --archive PATH [--off SCHALTER]… [--expert-reset]` | Vollständige Konfiguration mit diesen Ordnern schreiben; eine vorhandene behält Ordner und Werte und bekommt nur fehlende Schlüssel dazu. `--off` (mehrfach) setzt `dng`, `tiff`, `contact_sheet`, `service` oder `update_check` auf `false`; `--expert-reset` setzt alle [Experten-Schwellen](#experten-schwellen) auf den Standard. Legt die konfigurierten Ordner an; gibt `config=`, `status=created\|completed\|kept` (neu angelegt, ergänzt, unverändert), `negative=`, `photos=`, `archive=` und je Schalter `<schalter>=true\|false` aus |
| `--config PATH` | Pfad der Konfigurationsdatei |
| `-Q`, `--silent` | Keine Konsolenausgabe (die Log-Datei wird weiter geschrieben) |
| `-v`, `--verbose` | Mehr Ausgabe (je Datei Zuschnittsgröße und Grund des Zuschnitts) |
| `-vv`, `--debug` | Debug-Ausgabe (auch in der Log-Datei) |
| `-V`, `--version` | Version anzeigen und beenden |
| `--help` | Hilfe (auch nach jedem Befehl) |
| `run --negative PATH` | Eingabeordner (überschreibt `negative_dir`) |
| `run --archive PATH` | Archivordner (überschreibt `archive_dir`) |
| `run --photos PATH` | Ausgabeordner (überschreibt `photos_dir`) |
| `run --dng` / `--no-dng` | Überschreibt `dng` |
| `run --dng-finder-preview` / `--no-dng-finder-preview` | Überschreibt `dng_finder_preview` |
| `run --summary` | Für Starter: gibt die Zeile `processed=<n> failed=<m> busy=<0\|1>` aus (verarbeitet, fehlgeschlagen, Ordner belegt), davor nur bei Bedarf je Problem der Selbstprüfung `check=<Text>` und bei einer neuen Version `update=<Version>`; keine Desktop-Mitteilung. Blieben Dateien wegen der Umgebung in `Negative/` (z. B. Speicher voll), statt der Zeile `Error: <Grund>` mit Exit-Code 1 |

Jeder Lauf (`run`, ohne Befehl) gleicht vorher den Hintergrunddienst mit dem Schalter `service` ab, prüft sich still selbst (Probleme als eigene Zeilen, nicht mit `-Q`; ist ein Ordner nicht benutzbar, `Error: …` und kein Lauf) und gibt bei einer neuen Version eine Zeile `Neue Version X verfügbar: https://github.com/jcmx9/real-fast-filmlab#update` aus. Globale Optionen (`--config`, `-Q`, `-v`, `-vv`) stehen vor dem Befehl, z. B. `rffilmlab -v run --photos ~/Film/Fotos --no-dng`. Exit-Codes: 0 = alles erledigt (auch wenn der Ordner belegt war), 1 = mindestens eine Datei fehlgeschlagen oder Konfigurations- bzw. Ordnerfehler. Mit `run --summary` steht das Ergebnis in der Zeile; der Exit-Code ist dann nur bei einem Fehler vor der Verarbeitung (z. B. Konfiguration, Ordner nicht erreichbar) oder bei Dateien, die wegen der Umgebung in `Negative/` blieben, 1. Fehler des Betriebssystems erscheinen immer als eine Zeile `Error: …`, nie als Python-Traceback.

## Unterstützte Kameras und Formate

Alles, was LibRaw 0.22 liest, mit den Endungen `.arw .sr2 .raf .nef .nrw .cr2 .cr3 .orf .rw2 .pef .srw .dng`. Das Sensorformat der Kamera spielt keine Rolle: Erkannt wird das Bildfeld auf dem Film.

## Fehlersuche

- **Eine Datei liegt in `Negative/_Fehler/`:** Die `.txt` daneben nennt den Grund. Nach Behebung der Ursache das RAW zurück nach `Negative/` schieben.
- **„Ordner nicht erreichbar“, „Ordner oder Laufwerk nicht mehr erreichbar“, „Kein Speicherplatz mehr frei“ oder „Keine Berechtigung“:** Laufwerk anschließen, Platz schaffen oder die Berechtigung prüfen (macOS: Systemeinstellungen › Datenschutz & Sicherheit, z. B. „Festplattenvollzugriff“ oder „Wechselmedien“ für den Dienst). Die RAW-Dateien liegen unverändert in `Negative/`; danach „Negative entwickeln“ starten. Nach „Kein Speicherplatz mehr frei“ versucht der Dienst sie automatisch erneut, sobald mindestens 1 GB mehr frei ist (spätestens nach 10 Minuten), nach „Ordner oder Laufwerk nicht mehr erreichbar“ beim nächsten Lauf, sobald die Ordner wieder erreichbar sind; sonst nimmt er sie erst wieder auf, wenn sie sich ändern oder er neu gestartet wird.
- **Es passiert nichts:** `rffilmlab service status` zeigt, ob der Dienst läuft und wo die Log-Datei liegt. Ohne Dienst: `rffilmlab run` von Hand starten.
- **Fehlermeldung zur Konfiguration:** Sie nennt den fehlenden oder falschen Schlüssel und den Pfad der Konfigurationsdatei.
- **„Der Dienst verarbeitet gerade …“:** Ein anderer Lauf arbeitet am Ordner; später erneut versuchen.
- **Bilder stehen Kopf, liegen quer oder sind gespiegelt:** `rotate` und/oder `mirror` setzen und neu verarbeiten. Die Lage-Markierung der Kamera wird nicht ausgewertet; ein Wert je Scan-Aufbau genügt.
- **Bilder wirken zu hart oder zu flau, zu bunt oder zu blass:** `contrast` und `saturation` ändern (Abschnitt 5) und neu verarbeiten.
- **Bildecken heller als die Mitte:** Lampe oder Objektiv geben am Rand weniger Licht; ein RAW des leeren Halters als `flatfield` eintragen (je Aufbau eine eigene Aufnahme, so kurz belichtet, dass nichts übersteuert; siehe [Bildwirkung](#bildwirkung)).
- **Hinweis „Die Scans sind dunkel belichtet“ oder „… zu hell belichtet“:** die Belichtung beim Abfotografieren anpassen (Schritt 3.8); die Bilder dieses Laufs sind trotzdem entwickelt.
- **Zuschnitt falsch:** Im DNG lässt sich der Zuschnitt in Lightroom/Camera Raw zurücksetzen. `crop=uncertain` in der Beschreibung heißt: Die Erkennung war unsicher und hat den ganzen Filmstreifen verwendet.
- **Keine Kameradaten in den Dateien:** exiftool ist nicht installiert oder wird nicht gefunden (Warnung im Log; `rffilmlab service status` zeigt das gefundene exiftool). Ist `exiftool_path` gesetzt, gilt nur dieser Pfad (fehlt die Datei dort, läuft das Programm ohne exiftool); sonst wird im `PATH` gesucht, dann die Kopie des Installers im Programmdatenordner. Den Installer erneut ausführen, exiftool installieren oder `exiftool_path` setzen.

Log-Dateien: `rffilmlab.log` (Hintergrunddienst) und `rffilmlab-run.log` (einzelne Läufe: „Negative entwickeln“, `rffilmlab run`), getrennt, damit sich zwei gleichzeitig laufende Prozesse nicht in die Quere kommen; je bis zu 6 Dateien (die aktuelle und 5 ältere) zu je 5 MB im Wechsel. Unter macOS zusätzlich `service.out.log`/`service.err.log` des Dienstes.

| System | Ordner |
|--------|--------|
| macOS | `~/Library/Logs/real-fast-filmlab/` |
| Linux | `~/.local/state/real-fast-filmlab/log/` |
| Windows | `%LOCALAPPDATA%\real-fast-filmlab\Logs\` |

## Entwicklung

```bash
git clone git@github.com:jcmx9/real-fast-filmlab.git
```

```bash
cd real-fast-filmlab && uv sync
```

```bash
uv run ruff check --fix . && uv run ruff format . && uv run mypy src/
```

Entwicklungsläufe nutzen immer einen isolierten App-Ordner, damit eine echte Installation unberührt bleibt (Konfiguration, Logs, Daten, exiftool und Dienstdateien liegen dann darunter; Dienstbefehle wie `launchctl` werden nicht ausgeführt, nur angezeigt):

```bash
RFFILMLAB_HOME=.devhome uv run rffilmlab --help
```

Die Umgebungsvariable `RFFILMLAB_HOME` verlegt alle Programmordner nach `<RFFILMLAB_HOME>/config`, `log`, `data` und `service`. Der Ordner `.devhome/` ist von Git ausgeschlossen. Für die Entwicklung nie `uv tool install` verwenden: Das würde eine echte Installation überschreiben.

Die Testsuite wird getrennt gepflegt und nicht veröffentlicht; dieses Repository enthält nur den Quellcode.

## Versionierung

Das Projekt nutzt [CalVer](https://calver.org/) im Format `YY.M.MICRO` (z. B. `26.11.3`); Entwicklungsversionen tragen `.devN`. Die Version setzt `scripts/release.sh <Version>` mit [bump-my-version](https://github.com/callowayproject/bump-my-version) in allen Dateien und prüft sie mit `scripts/check_release.sh`.

## Mitwirken

Siehe [CONTRIBUTING.md](CONTRIBUTING.md). Kurzfassung: Branch von `main` abzweigen, mit Conventional Commits committen, Pull Request gegen `main` öffnen.

## Sicherheit

Sicherheitslücken bitte **nicht** über öffentliche Issues melden. Siehe [SECURITY.md](SECURITY.md).

## Changelog

Siehe [CHANGELOG.md](CHANGELOG.md).

## Lizenz

MIT, siehe [LICENSE](LICENSE).
