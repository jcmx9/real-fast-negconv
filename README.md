# real-fast-negconv

**Version 26.10.7** · [English](README.en.md)

> Wandelt Kamera-RAW-Scans von Filmnegativen (Farbe und Schwarzweiß) automatisch in DNG-, TIFF- und JPEG-Positive um.

[![CI](https://github.com/jcmx9/real-fast-negconv/actions/workflows/ci.yml/badge.svg)](https://github.com/jcmx9/real-fast-negconv/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

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

## Installation und Update

Ein Befehl richtet alles ein. macOS und Linux (Terminal):

```bash
curl -LsSf https://raw.githubusercontent.com/jcmx9/real-fast-negconv/main/install.sh | sh
```

Windows (PowerShell):

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/jcmx9/real-fast-negconv/main/install.ps1 | iex"
```

**Update:** denselben Befehl noch einmal ausführen. Vorhandene Konfiguration, Ordner und Bilder werden dabei nie verändert.

Der Installer

1. richtet [uv](https://docs.astral.sh/uv/) ein, falls es fehlt (uv bringt sein eigenes Python mit),
2. installiert real-fast-negconv in der zum Installer gehörenden Version, mit den dafür festgelegten Bibliotheksversionen (`constraints.txt` dieser Version),
3. legt im Bilder-Ordner des Benutzers (macOS und Linux `~/Pictures`, Windows „Bilder“) die Ordner `rfnegconv/Negative`, `Fotos` und `Archiv` an und schreibt die Konfiguration – nur, wenn noch keine existiert (sonst gelten die dort eingetragenen Ordner),
4. startet den Hintergrunddienst (mit der Option „ohne Dienst“ stattdessen: kein Dienst, ein vorhandener wird entfernt – siehe unten),
5. legt die Verknüpfungen „Negative“ und „Fotos“ auf den Schreibtisch (gleichnamige eigene Verknüpfungen bleiben unberührt),
6. legt das Programm „Negative entwickeln“ an: macOS im Ordner „Programme“ des Benutzers (`~/Applications`), Windows im Startmenü, Linux im Anwendungsmenü (`~/.local/share/applications`); ein gleichnamiges eigenes Programm bleibt unberührt,
7. richtet zuletzt exiftool ein, falls es fehlt (macOS mit Homebrew über `brew`, sonst das offizielle Paket von exiftool.org mit geprüfter Prüfsumme im Programmdatenordner; unter Linux nur, wenn Perl vorhanden ist). Das dauert meist höchstens etwa eine Minute. Ist der Server nicht erreichbar, gibt der Installer nach etwa 20 Sekunden auf (Verbindungsaufbau höchstens 10 Sekunden, eine Wiederholung; eine abgelehnte Verbindung sofort). Mit curl dauert ein Download einschließlich einer Wiederholung höchstens etwa 2 Minuten, das exiftool-Paket höchstens etwa 10 Minuten; scheitert es, wird es einmal vom Spiegelserver geladen (wieder höchstens etwa 10 Minuten). Unter Windows bricht ein Download ab, wenn der Server 30 Sekunden lang nicht antwortet (keine Wiederholung); das exiftool-Paket hat höchstens 10 Minuten und wird bei einem Fehler einmal vom Spiegelserver geladen. Ohne curl, mit wget, gibt es keine Gesamtgrenze: Ein Download bricht ab, sobald 10 Sekunden lang keine Daten kommen, und wird einmal wiederholt. Die Installation über Homebrew hat keine Zeitgrenze. Klappt es nicht, erscheint ein Hinweis, und alles andere ist trotzdem eingerichtet,
8. zeigt Version, Dienststatus und wo die Ordner liegen. Wird `rfnegconv` danach im Terminal nicht gefunden, ein neues Terminalfenster öffnen.

Ein Update unter Windows beendet nur den Hintergrunddienst; läuft gerade eine Verarbeitung über „Negative entwickeln“, wird sie nicht unterbrochen, sondern das Update bricht mit einem Hinweis ab und kann danach wiederholt werden.

Danach genügt es, Scans in den Ordner „Negative“ zu legen; die Bilder erscheinen automatisch in „Fotos“. Wer nicht warten will, startet „Negative entwickeln“.

### Ohne Hintergrunddienst

Wer die Verarbeitung lieber selbst auslöst, installiert ohne Dienst. Ein bereits laufender Dienst wird dabei entfernt; die Verarbeitung startet dann nur über das Programm „Negative entwickeln“. macOS und Linux:

```bash
curl -LsSf https://raw.githubusercontent.com/jcmx9/real-fast-negconv/main/install.sh | sh -s -- --ohne-dienst
```

Windows (PowerShell):

```powershell
powershell -ExecutionPolicy ByPass -c "& ([scriptblock]::Create((irm https://raw.githubusercontent.com/jcmx9/real-fast-negconv/main/install.ps1))) -OhneDienst"
```

Der normale Installationsbefehl (ohne die Option) richtet den Dienst wieder ein. Für Updates denselben Befehl wie bei der Installation verwenden, also mit der Option, solange kein Dienst laufen soll.

### Für Fortgeschrittene: manuell mit uv

uv installieren (einmalig), macOS und Linux:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Windows (PowerShell):

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

real-fast-negconv installieren (braucht git):

```bash
uv tool install git+https://github.com/jcmx9/real-fast-negconv.git
```

Ohne `--constraints` löst uv dabei die jeweils neuesten passenden Bibliotheken auf; dieselben Versionen wie der Installer ergibt `--constraints constraints.txt` mit der Datei aus dem Repository.

Update auf die neueste Version (die Konfiguration bleibt erhalten):

```bash
uv tool install --force git+https://github.com/jcmx9/real-fast-negconv.git
```

Ordner und Konfiguration anlegen (schreibt nur, wenn noch keine Konfiguration existiert) und den Dienst starten:

```bash
rfnegconv config init --negative ~/Pictures/rfnegconv/Negative --photos ~/Pictures/rfnegconv/Fotos --archive ~/Pictures/rfnegconv/Archiv
```

```bash
rfnegconv service install
```

## Deinstallation

macOS und Linux:

```bash
curl -LsSf https://raw.githubusercontent.com/jcmx9/real-fast-negconv/main/install.sh | sh -s -- --uninstall
```

Windows (PowerShell):

```powershell
powershell -ExecutionPolicy ByPass -c "& ([scriptblock]::Create((irm https://raw.githubusercontent.com/jcmx9/real-fast-negconv/main/install.ps1))) -Uninstall"
```

Entfernt werden der Hintergrunddienst, das Programm, „Negative entwickeln“ und die vom Installer angelegten Verknüpfungen auf dem Schreibtisch (nur, wenn sie noch auf die Ordner zeigen); exiftool und uv nur, wenn der Installer sie selbst eingerichtet hat (vermerkt in der Datei `installer-state` im Programmdatenordner). Das von uv verwaltete Python und der Tool-Ordner von uv werden nur entfernt, wenn der Installer uv selbst eingerichtet hat und `uv tool list` erfolgreich meldet, dass keine anderen uv-Tools mehr installiert sind. **Die Ordner, die Bilder, die Konfiguration und die Log-Dateien werden nie gelöscht.** Hat der Installer uv eingerichtet, wird außerdem der Download-Zwischenspeicher von uv geleert. Manuell: `rfnegconv service uninstall`, dann `uv tool uninstall real-fast-negconv`.

## Ordner und täglicher Gebrauch

Das Programm arbeitet mit drei Ordnern, die einmal in der Konfiguration festgelegt werden (die Namen sind frei wählbar; hier: `Negative`, `Fotos`, `Archiv`):

| Ordner | Schlüssel | Zweck |
|--------|-----------|-------|
| `Negative/` | `negative_dir` | Eingang: hier RAW-Dateien hineinlegen |
| `Fotos/` | `photos_dir` | Ergebnisse: `<name>.dng`, `<name>.tif`, `<name>.jpg` |
| `Archiv/` | `archive_dir` | Originale nach erfolgreicher Verarbeitung |

Täglicher Gebrauch:

1. Die RAW-Dateien eines Films nach `Negative/` kopieren – am besten den ganzen Film auf einmal, weil Bilder desselben Films aufeinander abgestimmt werden.
2. Verarbeitung starten (Programm „Negative entwickeln“, `rfnegconv run` oder gar nichts, wenn der Hintergrunddienst läuft).
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

Die Verarbeitung kann bei einem ganzen Film einige Minuten dauern; die Ergebnismeldung erscheint erst danach. Das Programm führt `rfnegconv -Q run --summary` aus (der Pfad zu `rfnegconv` und unter macOS und Linux der `PATH` werden bei der Installation eingetragen). Umsetzung: macOS `~/Applications/Negative entwickeln.app` mit einem Shell-Skript und AppleScript-Dialog; Windows `Negative entwickeln.lnk` im Startmenü, das `negative-entwickeln.vbs` im Programmdatenordner mit `wscript.exe` startet; Linux `negative-entwickeln.desktop`, das `negative-entwickeln.sh` im Programmdatenordner startet und das Ergebnis mit zenity, kdialog oder notify-send zeigt (je nachdem, was vorhanden ist; den Hinweis zu Beginn nur mit notify-send).

### Ohne Terminal: Doppelklick-Starter

`scripts/rfnegconv.command` (macOS) und `scripts/rfnegconv.bat` (Windows) verarbeiten den Ordner `Negative/` einmal und lassen das Fenster offen, bis eine Taste gedrückt wird. Die Datei aus dem Repository z. B. auf den Schreibtisch kopieren. Ein Start, während der Hintergrunddienst arbeitet, ist unschädlich: Eine Sperrdatei in `Negative/` verhindert doppelte Verarbeitung, und der Starter meldet „Der Dienst verarbeitet gerade – bitte später erneut versuchen.“

### Hintergrunddienst

Der Dienst beobachtet `Negative/`, wartet, bis das Kopieren abgeschlossen ist, und verarbeitet die Dateien dann selbstständig. Er startet bei jeder Anmeldung. Am Ende jedes Laufs zeigt eine Desktop-Mitteilung „N Fotos fertig, M Fehler“, bei Problemen mit einem Ordner zusätzlich den Grund. Ist ein Ordner nicht erreichbar (z. B. externes Laufwerk getrennt), meldet der Dienst das einmal (Log und Mitteilung) und versucht es still weiter, bis der Ordner wieder da ist.

```bash
rfnegconv service install
```

```bash
rfnegconv service status
```

```bash
rfnegconv service uninstall
```

Umsetzung: macOS LaunchAgent `~/Library/LaunchAgents/io.github.jcmx9.rfnegconv.plist` (nach einem Absturz neu gestartet), Windows `rfnegconv.vbs` im Autostart-Ordner (keine Administratorrechte nötig), Linux systemd-User-Unit `~/.config/systemd/user/rfnegconv.service` (`Restart=on-failure`). Der Dienst führt `rfnegconv -Q watch` aus; der `PATH` zum Zeitpunkt der Installation wird übernommen, damit exiftool gefunden wird.

## Konfiguration

### Ort der Konfigurationsdatei

| System | Pfad |
|--------|------|
| macOS | `~/Library/Application Support/real-fast-negconv/config.toml` |
| Linux | `~/.config/real-fast-negconv/config.toml` |
| Windows | `%LOCALAPPDATA%\real-fast-negconv\config.toml` |

Eine andere Datei lässt sich mit `--config PATH` angeben. Fehlt die Datei oder ist ein Ordner nicht gesetzt, nennt das Programm den fehlenden Schlüssel und den erwarteten Pfad der Datei. Unbekannte Schlüssel sind ein Fehler (Schutz vor Tippfehlern).

### Beispiel

```toml
negative_dir = "~/Film/Negative"
archive_dir  = "~/Film/Archiv"
photos_dir   = "~/Film/Fotos"
rotate = 0                    # 0 | 90 | 180 | 270 (im Uhrzeigersinn)
mirror = false                # true, wenn von der Schichtseite aus fotografiert
dng = true                    # false: nur TIFF + JPEG
dng_finder_preview = false    # true: größeres DNG, das Finder und Quick Look anzeigen
```

`~` steht für den Benutzerordner. Die drei Ordner müssen verschieden sein. Ein fehlender Ordner wird bei der Verarbeitung nur angelegt, wenn der Ordner darüber existiert; sonst (z. B. Laufwerk nicht angeschlossen) meldet das Programm „Ordner nicht erreichbar“, statt die Ordner auf der Systemfestplatte anzulegen. `rfnegconv config init` legt die Ordner samt fehlender übergeordneter Ordner an.

### Alle Schlüssel

Jeder Schlüssel ist optional, außer den drei Ordnern. Typen: `path` = Text in Anführungszeichen, `bool` = `true`/`false`, `int`/`float` = Zahl.

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
| `dng_finder_preview` | bool | `false` | `true`, `false` | `false`: float16-DNG mit Deflate (kleiner), behält Werte über dem Weißpunkt und unter dem Schwarzpunkt. `true`: unkomprimiertes uint16-DNG, das Finder und Quick Look unter macOS anzeigen (größer), auf 0–1 begrenzt |
| `jpeg_quality` | int | `95` | 1–100 | JPEG-Qualität |

#### Ausrichtung

| Schlüssel | Typ | Standard | Erlaubt | Wirkung |
|-----------|-----|----------|---------|---------|
| `rotate` | int | `0` | `0`, `90`, `180`, `270` | Im Uhrzeigersinn drehen (je Scan-Aufbau, gilt für alle Dateien) |
| `mirror` | bool | `false` | `true`, `false` | Horizontal spiegeln, vor dem Drehen (Film von der Schichtseite fotografiert) |

#### Korrektur

TIFF und JPEG enthalten das korrigierte Bild (sanfte Korrektur, Abschnitt 5), das DNG die neutralen linearen Daten (float16 ohne Begrenzung auf 0–1, Schritt 4.12).

#### Dienst und Betrieb

| Schlüssel | Typ | Standard | Erlaubt | Wirkung |
|-----------|-----|----------|---------|---------|
| `notify` | bool | `true` | `true`, `false` | Desktop-Mitteilung nach jedem Lauf |
| `parallel_jobs` | int | `0` | ≥ 0 | Gleichzeitig verarbeitete Dateien; `0` = automatisch: min(CPU-Kerne, ⌊halber Arbeitsspeicher / 4 GiB⌋, Anzahl Dateien), mindestens 1 |
| `settle_seconds` | float | `5.0` | > 0 | Watch-Modus: so lange müssen die Dateien unverändert sein, bevor ein Lauf startet; auch die Wartezeit vor einem neuen Versuch (begrenzt auf 5–60 s) |
| `exiftool_path` | path | leer | Pfad zum Programm | Gesetzt: nur dieses Programm (gibt es die Datei nicht, ohne exiftool). Leer: `exiftool` im `PATH`, sonst die Kopie des Installers im Programmdatenordner |

Die Ausgabemenge wird nur auf der Kommandozeile gewählt (`-Q`, `-v`, `-vv`); ein Schlüssel `verbosity` in der Datei wird ignoriert.

#### Experten-Schwellen

Nur nötig, wenn die Erkennung bei ungewöhnlichem Material scheitert. Namen wie im Code (`AnalyzerSettings`, `RollSettings`); die Schritte sind unter [Verarbeitung Schritt für Schritt](#verarbeitung-schritt-für-schritt) erklärt.

| Schlüssel | Typ | Standard | Erlaubt | Wirkung |
|-----------|-----|----------|---------|---------|
| `measure_inset` | float | `0.10` | 0–0,25 | Inneres Messfenster: Anteil von Höhe/Breite des Zuschnitts, der je Seite ausgelassen wird (0,10 = innere 80 %) |
| `holder_delta` | float | `1.8` | > 0 | Filmmaske: Dichte über der klarsten Basis, bis zu der ein Pixel als Film zählt |
| `holder_min` | float | `1.0` | 0,3–`holder_delta` | Durchscheinender Halter: Mindestdichte über der klarsten Basis, ab der ein Randstreifen als Halter gelten kann (Schritt 4); Standard min(1,0; holder_delta), mindestens 0,3 |
| `gap_delta` | float | `0.10` | > 0 | Strenges Basis-Pixel (Steg zwischen Bildern): Dichtegrenze über der Basis |
| `gap_std` | float | `0.03` | > 0 | Strenges Basis-Pixel: Grenze der lokalen Standardabweichung |
| `loose_delta` | float | `0.15` | > 0 | Lockeres Basis-Pixel (Randbeschnitt): Dichtegrenze über der Basis |
| `loose_std` | float | `0.08` | > 0 | Lockeres Basis-Pixel: Grenze der lokalen Standardabweichung |
| `aspect_tol` | float | `0.08` | > 0 und < 1 | Auf ein Filmformat einrasten, wenn das Seitenverhältnis um weniger als diesen Anteil abweicht |
| `min_skew_deg` | float | `0.2` | 0–45 | Kleinster Schräglagenwinkel, der korrigiert wird (Grad) |
| `max_skew_deg` | float | `5.0` | 0–45 | Größter Schräglagenwinkel, der korrigiert wird (Grad) |
| `dmin_percentile` | float | `0.2` | 0–100 | Perzentil (in %) der Dichte über die Filmmaske, das als Filmbasis gilt |
| `white_percentile` | float | `99.5` | > 0 und ≤ 100 | Perzentil (in %) der Dichte im inneren Fenster, das als Weißpunkt gilt |
| `bw_threshold` | float | `0.03` | > 0 | Farbe/SW-Entscheidung: Grenze für die Kanalabweichung (99,9-%-Perzentil) |
| `gamma_color` | float | `0.6` | > 0 | Gradation von Farbfilm bei der Umrechnung in lineares Licht |
| `gamma_bw` | float | `0.65` | > 0 | Gradation von Schwarzweißfilm |
| `hue_tol` | float | `0.06` | > 0 | Rollen-Gruppierung: größter Abstand des Farbtons der Filmbasis |
| `highkey_delta` | float | `0.10` | ≥ 0 | High-Key-Fallback: Mindestanhebung der Filmbasis in jedem Kanal |
| `uniform_ratio` | float | `2.0` | ≥ 1 | High-Key-Fallback: größte Anhebung höchstens so viel mal die kleinste |
| `crossover_limit` | float | `0.15` | 0–0,5 | Farbübergangs-Korrektur: Exponent k je Kanal höchstens so weit von 1 entfernt; `0` schaltet sie ab (Schritt 3.5) |

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
| `BORDER_MARGIN` | 0.02 | `core/analyzer.py` | Blankes Licht: Rand von 2 % der langen Kante je Seite für die erste Basis-Schätzung ausgelassen |
| `BARE_GAP` | 0.2 | `core/analyzer.py` | Blankes Licht: mehr als 0,2 unter der ersten Basis-Schätzung |
| `BW_PERCENTILE` | 99.9 | `core/analyzer.py` | Farbe/SW: Perzentil der Block-Abweichung |
| `HOLDER_MIN_FLOOR` | 0.3 | `config.py` | Untergrenze von `holder_min` |
| `ASPECTS` | 1:1 = 1,00, 6x7 = 1,24, 6x4.5 = 1,35, 3:2 = 1,50 | `core/analyzer.py` | Filmformate zum Einrasten |
| `crop_rect(inset)` | 0.01 | `core/geometry.py` | Zuschnitt je Seite um 1 % seiner längeren Seite nach innen gezogen |
| `MEASURE_INSET` | 0.10 | `core/geometry.py` | Standardwert von `measure_inset` |
| `MIN_SPREAD` | 0.05 | `core/converter.py` | Kleinster Dichteumfang je Kanal |
| `black_point(percentile)` | 0.5 | `core/converter.py` | Schwarzpunkt: 0,5-%-Perzentil der Luminanz |
| `EPS` | 1/65535 | `core/converter.py` | Kleinster Wert vor dem Logarithmus |
| `COLOR_STRENGTH`, `BW_STRENGTH` | 1.0, 0.5 | `core/look.py` | Stärke der Korrektur für Farbe und SW |
| `SPREAD_TARGET`, `MAX_CONTRAST` | 0.70, 0.35 | `core/look.py` | Kontrastregel (Gruppe) |
| `CHROMA_TARGET`, `SAT_GAIN`, `MAX_SATURATION`, `CHROMA_FULL` | 0.10, 1.5, 1.15, 0.5 | `core/look.py` | Sättigungsregel |
| `SAMPLE_STEP` | 4 | `core/look.py` | Look-Statistik auf jedem 4. Pixel |
| `MID_BAND`, `MIN_MID_PIXELS` | 0.05, 200 | `core/crossover.py` | Farbübergang: Mittelgrau-Pixel mit \|x_G − 0,5\| < 0,05; weniger als 200 im inneren Fenster: keine Messung |
| `MID_CLIP` | 0.05–0.95 | `core/crossover.py` | Farbübergang: Mittelwerte vor dem Logarithmus auf diesen Bereich begrenzt |
| `ROLL_MIN_FRAMES`, `ROLL_AGREEMENT` | 3, 0.8 | `core/crossover.py` | Farbübergang je Rolle: mindestens 3 gemessene Farbbilder, davon ≥ 80 % je Kanal R und B auf derselben Seite |
| `SAMPLE_MAX_PIXELS` | 87 381 | `core/crossover.py` | Dichte-Stichprobe des inneren Fensters je Bild (höchstens 1 MiB) |
| `PREVIEW_LONG_EDGE` | 1024 | `service/render.py` | Lange Kante der im DNG eingebetteten Vorschau |
| `MEMORY_PER_WORKER` | 4 GiB | `service/batch.py` | Arbeitsspeicher-Budget je parallelem Job |
| `STALE_TEMP_SECONDS` | 3600 | `service/batch.py` | Liegengebliebene temporäre Dateien älter als 1 h werden gelöscht |
| `STALE_TEMP_PATTERNS` | `.*.tmp.*`, `*_exiftool_tmp` | `service/batch.py` | Namensmuster dieser temporären Dateien |
| `TIMEOUT_SECONDS` | 300 | `fileio/exiftool.py` | Längste Laufzeit eines exiftool-Aufrufs |
| `RESCAN_SECONDS` | 60 | `service/watcher.py` | Watch-Modus: Ordner mindestens einmal pro Minute neu prüfen |
| `MIN_BACKOFF`, `MAX_BACKOFF` | 5 s, 60 s | `service/watcher.py` | Watch-Modus: Grenzen der Wartezeit vor einem neuen Versuch |
| `FINDER_BUSY_DAY` | 24.01.1984 (±12 h) | `service/watcher.py` | macOS: Erstellungsdatum, mit dem der Finder eine Datei während des Kopierens markiert |

## Verarbeitung Schritt für Schritt

### Überblick

Jeder Lauf verarbeitet alle Dateien in zwei Durchgängen: **Durchgang 1** analysiert jede Datei auf einer kleinen Vorschau, danach vergleicht der **Rollen-Kontext** die Dateien miteinander, und **Durchgang 2** entwickelt jede Datei in voller Auflösung und schreibt die Ausgaben. Drei Bereiche des Scans werden unterschieden, und sie werden in dieser Reihenfolge bestimmt:

1. **Filmmaske** – der ganze Filmstreifen im Bild (Bildfelder, Stege zwischen den Bildern, Filmrand), ohne den Halter. Hier wird die Filmbasis `d_min` gemessen.
2. **Zuschnitt** – das erkannte Bildfeld, zuerst und vollständig bestimmt (Entzerrung, Ränder, Stege, Format-Einrasten, 1 % nach innen). TIFF und JPEG werden darauf beschnitten; das DNG trägt ihn als zurücksetzbare Zuschnitt-Einstellung. Hier wird Farbe/SW gemessen.
3. **Inneres Fenster** – der Zuschnitt ohne `measure_inset` (10 %) seiner Höhe/Breite je Seite (innere 80 % × 80 %), immer relativ zum *endgültigen* Zuschnitt gelegt. Weißpunkt, Schwarzpunkt, Farbübergang und alle Look-Statistiken werden hier gemessen, damit ein Streifen Filmrand oder Halter am Rand sie nicht verschieben kann. Weiß- und Schwarzpunkt gelten nur für dieses eine Bild (Normierung je Bild, siehe Grundsätze).

### 1. Auslöser und Lauf-Start

1. **Auslöser.** `rfnegconv run` (oder `rfnegconv` ohne Befehl, das Programm „Negative entwickeln“ oder ein Doppelklick-Starter) verarbeitet den Ordner einmal. Im Watch-Modus (`rfnegconv watch`, Hintergrunddienst) weckt ein Dateisystem-Ereignis oder spätestens eine Neuprüfung alle 60 s das Programm; beim Start bereits wartende Dateien werden verarbeitet.
2. **Ruhephase (nur Watch-Modus).** Alle 0,5 s werden Größe und Änderungszeit (`mtime_ns`) aller Kandidaten gelesen; eine Datei, die sich noch nicht zum Lesen öffnen lässt (Windows während des Kopierens) oder die der Finder unter macOS noch kopiert (Erstellungsdatum 24.01.1984, `FINDER_BUSY_DAY`), gilt als instabil. Der Lauf startet, sobald sich dieser Zustand `settle_seconds` (5 s) lang nicht geändert hat. Fehlgeschlagene Dateien, die in `Negative/` geblieben sind, werden übersprungen, bis sich Größe oder Zeit ändern (ein Lauf über „Negative entwickeln“ oder `rfnegconv run` versucht sie erneut).
3. **Ordner.** Alle drei Ordner müssen gesetzt und verschieden sein. Ein fehlender Ordner wird nur angelegt, wenn der Ordner darüber existiert. Ist ein Ordner nicht erreichbar oder nicht beschreibbar (auch beim Anlegen der Sperrdatei oder beim Lesen von `Negative/`), endet der Lauf mit einer klaren Meldung, z. B. `Error: Ordner nicht erreichbar: <Pfad> – ist das Laufwerk angeschlossen? (folder not reachable: …)`, `Keine Berechtigung für den Ordner: …`, `Der Ordner ist schreibgeschützt: …` oder `Kein Speicherplatz mehr frei: …` (Exit-Code 1). Der Watch-Modus meldet das einmal in Log und Mitteilung, versucht es alle min(60, max(5, `settle_seconds`)) s still erneut (ist `Negative/` selbst nicht lesbar, spätestens bei der Neuprüfung alle 60 s) und meldet erst eine Änderung wieder.
4. **Sperre.** Exklusive, nicht blockierende Sperre auf `Negative/.rfnegconv.lock`. Hält ein anderer Lauf sie, endet dieser Lauf sofort, ohne etwas anzufassen („Der Dienst verarbeitet gerade – bitte später erneut versuchen.“, Exit-Code 0); der Watch-Modus versucht es nach min(60, max(5, `settle_seconds`)) s erneut. Dateisysteme ohne Sperr-Unterstützung: Warnung, Lauf ohne Sperre.
5. **Aufräumen.** Temporäre Dateien abgebrochener Läufe in `Fotos/` und `Archiv/` (`.<name>.tmp.*` und `<name>_exiftool_tmp` eines abgebrochenen exiftool), die älter als 1 h sind, werden gelöscht.
6. **Eingabeliste.** Dateien direkt in `Negative/` (keine Unterordner, `_Fehler/` wird also ignoriert), deren Endung ein bekanntes RAW-Format ist (Groß-/Kleinschreibung egal), ohne Namen, die mit `.` beginnen (versteckte Dateien, macOS-`._`-AppleDouble-Dateien). Nach Namen sortiert.
7. **exiftool und Parallelität.** exiftool wird gesucht: Ist `exiftool_path` gesetzt, nur dort; sonst im `PATH`, dann die Kopie des Installers im Programmdatenordner (fehlt es: eine Warnung). Anzahl paralleler Jobs: siehe `parallel_jobs`. Parallele Jobs sind Threads; sie ändern das Ergebnis nicht.

### 2. Durchgang 1: Analyse jeder Datei

Auf einer Vorschau des RAW in halber Auflösung. Eine Datei, die hier scheitert, wandert sofort nach `_Fehler/`; nur bei zu wenig Arbeitsspeicher oder einem Fehler des Dateisystems bleibt sie in `Negative/` (Schritt 4.18).

1. **Laden.** LibRaw (über rawpy) dekodiert das RAW in halber Auflösung mit 16 bit, linear (Gamma 1), ohne Weißabgleich (alle Multiplikatoren 1), ohne automatische Helligkeit, im eigenen RGB-Farbraum der Kamera; das Demosaicing ist der LibRaw-Standard. LibRaw wendet die im RAW gespeicherte Ausrichtung an, daher tragen alle Ausgaben `Orientation = 1`. Die Werte werden durch 65535 geteilt (0–1). Die Farbmatrix der Kamera (XYZ → Kamera) wird mitgelesen; fehlt sie, gilt die Einheitsmatrix.
2. **Vorschau.** Jedes n-te Pixel in beiden Richtungen, n = max(1, ⌊lange Kante / 1000⌋); die lange Kante der Vorschau hat also 1000–1999 Pixel.
3. **Dichte.** Je Kanal D = −log10(max(T, 1/65535)), T = linearer Wert. Auf einem Negativ hat die Filmbasis die geringste Dichte, die hellsten Stellen der Szene die höchste. Für die Erkennung wird das Kanalmittel `lum` verwendet.
4. **Filmmaske** (Bereich 1). Referenz `d_ref` = 0,5-%-Perzentil von `lum` (die klarste Filmbasis), gemessen ohne *blankes Licht*: Pixel, die mehr als 0,2 unter dem 0,5-%-Perzentil des Bildinneren (ohne 2 % der langen Kante Rand je Seite) liegen, sind ein Lichtstreifen am Bildrand (kein Film) und zählen weder für `d_ref` noch für die Filmmaske noch für `d_min`. Das gilt nur, solange der Teil des Streifens im Bildinneren unter 0,5 % der Pixel des Bildinneren liegt; darüber stellt der Streifen selbst das Perzentil, und das Ergebnis entspricht dem Verhalten ohne Behandlung von blankem Licht. Pixel mit `lum < d_ref + holder_delta` (1,8) sind Film, dichtere Pixel sind Halter. Danach morphologisches Öffnen und Schließen mit einem quadratischen Kern von max(3, lange Kante / 100) Pixeln (ungerade), und nur der größte zusammenhängende Bereich bleibt. Gibt es keinen, gilt das ganze Bild als Film. *Durchscheinender Halter:* Ist die Erkennung mit dieser festen Schwelle nicht sicher (Schritt 11), werden Randstreifen gesucht, die weniger dicht als `holder_delta`, aber deutlich dichter als die Basis sind. Je Bildseite zählen die Spalten (links/rechts) bzw. Zeilen (oben/unten) vom Bildrand nach innen, deren Dichte über `d_ref` über die ganze Seitenlänge einen Median ≥ `holder_min` (1,0) und ein 10-%-Perzentil ≥ 0,8 × `holder_min` hat (gleichmäßig dicht auf ≥ 90 % der Seite). Ein solcher Streifen gilt nur dann als Halter, wenn innerhalb von max(2, 0,5 % der langen Kante) Linien danach eine basisartige Linie folgt (Median ≤ `d_ref` + `loose_delta`, der Filmrand); der Streifen reicht bis zu dieser Linie. Ein heller Motivbereich am Rand (Himmel) hat keine solche Linie danach und bleibt Film. Die Streifen werden aus der Filmmaske genommen, die Schritte 6–11 laufen erneut, und das Ergebnis gilt nur, wenn es sicher ist; sonst bleibt alles wie mit der festen Schwelle. Eine sichere Erkennung mit der festen Schwelle wird nie verändert (dichte Filmhalter).
5. **Schräglage** (an den Außenkanten des Bildfelds). Zuerst laufen die Schritte 6–11 ohne Drehung und liefern ein grobes Bildfeld-Rechteck: die Kanten des gefundenen Segments *vor* dem Format-Einrasten und Kürzen (Schritte 9–10), bei unsicherer Erkennung das umschließende Rechteck der Filmmaske. So hängt der Winkel nicht davon ab, welches Ende gekürzt wird. Kantenbild = Betrag des Gradienten von `lum`, nur auf Film-Pixeln (Filmmaske, um max(3, lange Kante / 100) Pixel geschrumpft, ungerade; die Kante Film/Halter zählt nicht) und nur in vier Bändern um die Außenkanten dieses Rechtecks: je Kante 4 % seiner längeren Seite nach innen und nach außen. Das Bildinnere zählt nicht, Linien im Motiv beeinflussen den Winkel also nicht. Die Band-Pixel werden probeweise um θ gedreht (gegen den Uhrzeigersinn, um die Bildmitte, wie beim Entzerren); Gütemaß = Summe der quadrierten Zeilenprofile des oberen und unteren Bands plus Summe der quadrierten Spaltenprofile des linken und rechten Bands (Profilschritt 1 Pixel, lineare Verteilung auf die zwei Nachbarzellen nach einem festen Zufallsversatz von ±0,5 Pixel je Pixel, damit 0° nicht durch das Pixelraster bevorzugt wird). θ läuft von −`max_skew_deg` bis +`max_skew_deg` (5°) in Schritten von 0,25°, dann in Schritten von 0,02° im Bereich ±0,25° um das beste Grobergebnis (13 Schritte je Seite); bei Gleichstand gewinnt der kleinere |θ|, bei ±θ der negative. Liegt das beste Gütemaß weniger als 1 % über dem bei θ = 0 (keine nennenswerte Kante), liefert stattdessen `cv2.minAreaRect` um den Umriss der Filmmaske den Winkel, normiert auf −45° bis +45°. Nur wenn `min_skew_deg` (0,2°) ≤ |Winkel| ≤ `max_skew_deg` (5°), werden Vorschau und Maske um die Mitte um diesen Winkel gedreht und die Schritte 6–11 laufen erneut auf dem gedrehten Bild; sonst ist der Winkel 0 und das Ergebnis des ersten Laufs gilt. War der erste Lauf sicher, der zweite (gedrehte) aber nicht, gilt ebenfalls das ungedrehte Ergebnis des ersten Laufs (Winkel 0).
6. **Basis-Pixel.** Lokale Standardabweichung von `lum` in einem Fenster von max(3, lange Kante / 100) Pixeln (ungerade: `max(3, Kante // 100) | 1`), nur über Film-Pixel (der Halter kann sie an der Filmkante nicht anheben). *Strenges* Basis-Pixel: `lum < d_ref + gap_delta` (0,10) und Standardabweichung < `gap_std` (0,03). *Lockeres* Basis-Pixel: `lum < d_ref + loose_delta` (0,15) und Standardabweichung < `loose_std` (0,08), oder außerhalb der Filmmaske. Die folgenden Schritte arbeiten innerhalb des umschließenden Rechtecks der Filmmaske; seine längere Seite ist die lange Achse des Streifens.
7. **Ränder beschneiden.** Für jede Spalte (und Zeile) wird der Anteil lockerer Basis-Pixel berechnet; von beiden Enden werden Spalten/Zeilen entfernt, solange der Anteil > 60 % ist (Filmrand, Steg-Saum, Halterkante). Bliebe weniger als 10 % der Achse übrig, wird nichts beschnitten.
8. **An Stegen teilen** (nur lange Achse). Im beschnittenen Bereich sind Folgen von Spalten mit > 90 % strengen Basis-Pixeln, die mindestens max(2, lange Seite des Rechtecks / 100) breit sind, Stege zwischen Bildern. Das breiteste Segment dazwischen ist das Bildfeld. Tiefe Schatten im Motiv erfüllen die strengen Kriterien praktisch nie.
9. **Format einrasten.** Das Verhältnis lange/kurze Seite wird mit 1:1 (1,00), 6×7 (1,24), 6×4,5 (1,35) und 3:2 (1,50) verglichen; das Format mit der kleinsten relativen Abweichung gewinnt, wenn diese < `aspect_tol` (8 %) ist. Die zu lange Seite wird auf das genaue Verhältnis gekürzt. Sonst bleibt das Format „frei“.
10. **Welches Ende gekürzt wird** (nur nach dem Einrasten; zuerst entlang der Spalten, dann entlang der Zeilen). Kantenwert einer Spalte = Median über die Zeilen des Bildfelds der absoluten Dichtedifferenz zur nächsten Spalte. Ein Ende ist *verankert* (scharfer Bildrand), wenn der höchste Kantenwert innerhalb ±6 % der Achsenlänge um das Ende 2,5 × (`EDGE_FACTOR`) den Median der Kantenwerte im Segment erreicht. Beide Enden verankert: als Kante gilt die Stelle des höchsten Kantenwerts im Fenster; was zwischen Segmentende und Kante liegt, ist Außenstreifen (Schleier, Filmrand). Der Überstand wird je zur Hälfte an beiden Enden entfernt, außer dabei bliebe ein Außenstreifen stehen: dann wird die Aufteilung gerade so weit verschoben, dass er wegfällt. Sind beide Außenstreifen zusammen breiter als der Überstand, liegt der Ausschnitt mittig zwischen den beiden Kanten (höchstens der ganze Überstand an einem Ende); ist das Bildfeld kürzer als das Format, kann der Ausschnitt dabei einige Zeilen über eine Kante hinausreichen. Bekannte Schwäche: Die steilste Stufe im Fenster ±6 % kann eine gerade Motivkante statt des Bildrands sein; der Schaden ist auf den Überstand begrenzt. Ein Ende verankert: der ganze Überstand wird am anderen Ende entfernt. Kein Ende verankert: von allen möglichen Aufteilungen wird die gewählt, deren entfernte Streifen die geringste summierte Median-Dichte haben (nahe Filmbasis: Schleier, Filmrand, Steg-Saum); bei Gleichstand gewinnt die symmetrische Aufteilung.
11. **Sicherheit und Fallback.** Die Erkennung ist *sicher*, wenn das Format eingerastet ist, mindestens ein Rand beschnitten oder ein Steg gefunden wurde und das Bildfeld 25–98 % der Filmmaske bedeckt. Sonst gilt das umschließende Rechteck der Filmmaske als Bildfeld (`crop=uncertain` in der Beschreibung).
12. **Zuschnitt** (Bereich 2). Das Bildfeld wird auf die verwendete Auflösung skaliert und je Seite um 1 % seiner längeren Seite nach innen gezogen.
13. **Inneres Fenster** (Bereich 3). Der Zuschnitt aus Schritt 12 ohne `measure_inset` (10 %) seiner Höhe und Breite je Seite.
14. **Filmbasis `d_min`** (Bereich 1). Je Kanal das `dmin_percentile`-Perzentil (0,2 %) der Dichte über die ganze entzerrte Filmmaske (Bildfelder, Stege, Filmrand; kein Halter). Signatur = (d_min_R − d_min_G, d_min_B − d_min_G): der Farbton der Filmbasis, verwendet für die Rollen-Gruppierung.
15. **Weißpunkt `d_white`** (Bereich 3). Je Kanal das `white_percentile`-Perzentil (99,5 %) der Dichte im inneren Fenster.
16. **Farbe oder SW** (Bereich 2). Die Dichte des Zuschnitts wird wie in Durchgang 2, Schritt 3 normiert (mit eigenem `d_min` und `d_white` dieses Bildes), über Blöcke von 4 × 4 Pixeln gemittelt; je Block die mittlere absolute Abweichung der drei Kanäle von ihrem Mittel. Ist das 99,9-%-Perzentil dieser Abweichungen < `bw_threshold` (0,03), ist das Bild SW; schon ein kleiner Anteil klar farbiger Details entscheidet also für Farbe.
17. **Look-Statistik** (Bereich 3). Der Zuschnitt der Vorschau wird genau wie in Durchgang 2, Schritte 3, 4 und 7–10 entwickelt (eigenes `d_min`, `d_white`, Gamma nach dem eigenen Farbe/SW-Ergebnis, Schwarzpunkt im inneren Fenster, Kamera → sRGB bzw. Kanalmittel bei SW, sRGB-Kurve). Filmbasis und Farbe/SW sind dabei immer die eigenen Werte aus Durchgang 1, auch wenn der Rollen-Kontext sie später ändert (High-Key-Fallback, Mehrheit für Farbe/SW); der Median der Gruppe dämpft diesen Unterschied. Im inneren Fenster, jedes 4. Pixel in beiden Richtungen: **Spread** = 95-%- minus 5-%-Perzentil der Luminanz (Rec.-709-Gewichte 0,2126, 0,7152, 0,0722), **Chroma** = Mittel von (größter − kleinster Kanal) je Pixel (0 bei SW). Alle Werte werden vorher auf 0–1 begrenzt.
18. **Stichproben für Farbübergang und Look** (Bereich 3). Die Dichte des inneren Fensters wird in Rasterreihenfolge auf jedes s-te Pixel ausgedünnt, s = ⌈Pixelzahl / 87 381⌉ (höchstens 1 MiB je Bild), dazu die Dichte des Look-Rasters aus Schritt 17 (inneres Fenster, jedes 4. Pixel). Beide werden bis zum Rollen-Kontext aufbewahrt (Schritte 3.4 und 3.5) und danach verworfen. Bis dahin braucht der Lauf je Datei im Ordner etwa 1,3–2,3 MiB zusätzlich (100 Dateien ≈ 130–230 MiB).

### 3. Rollen-Kontext

Gilt für die Dateien eines Laufs, die Durchgang 1 bestanden haben, in Namensreihenfolge.

1. **Gruppierung nach Filmbasis.** Zwei Bilder sind Nachbarn, wenn ihre Signaturen (Schritt 2.14) näher als `hue_tol` (0,06, euklidischer Abstand) liegen. Gruppen entstehen durch Verkettung (Single Linkage): Sind A–B und B–C Nachbarn, bilden A, B und C eine Gruppe. Bilder desselben Films unter demselben Licht landen in einer Gruppe.
2. **High-Key-Fallback** (Gruppen mit ≥ 2 Bildern). Basislinie = 25-%-Quantil je Kanal der `d_min`-Werte der Gruppe. Ein Bild nutzt die Basislinie statt seines eigenen `d_min` nur, wenn alles gilt: In jedem Kanal liegt sein `d_min` mehr als `highkey_delta` (0,10) über der Basislinie; die Anhebung ist gleichmäßig (größte ≤ `uniform_ratio` (2,0) × kleinste); seine Signatur liegt näher als `hue_tol` an der Median-Signatur der Gruppe. Nach unten wird nie korrigiert. Grund: In einem sehr hellen Bild (Schnee, Himmel) sind selbst die klarsten Pixel keine Filmbasis; die Rolle kennt die echte Basis. Die Beschreibung lautet dann `fallback=yes`.
3. **Farbe oder SW je Rolle.** In einer Gruppe mit ≥ 2 Bildern entscheidet die Mehrheit: mehr als die Hälfte SW → alle SW, sonst alle Farbe (Gleichstand ergibt Farbe). Ein farbloses Motiv auf Farbfilm bleibt so Farbe. Einzelbilder behalten ihr eigenes Ergebnis. Ein überstimmtes Bild bekommt eine Log-Zeile.
4. **Look-Parameter.** Grundlage ist die Look-Statistik des um den Farbübergang (Schritt 3.5, zuerst bestimmt) korrigierten Vorschaubilds: bei k ≠ 1 wird sie auf dem Look-Raster (Schritt 2.18) mit k neu gemessen, sonst gilt die aus Schritt 2.17. Keine Belichtungskorrektur; Kontrast und Sättigung je Gruppe aus dem Median-Spread und der Median-Chroma ihrer Bilder (Bilder mit High-Key-Fallback bleiben außen vor, solange die Gruppe andere hat); Einzelbilder nutzen ihre eigenen Werte. Formeln: [Sanfte Korrektur im Detail](#5-sanfte-korrektur-im-detail).
5. **Farbübergang (Schichtsteilheit).** Die drei Farbschichten eines Farbnegativs haben leicht verschiedene Gradationskurven: Filmbasis und Weißpunkt sind nach der Kanal-Normierung neutral, die Mitteltöne nicht (typisch: das ganze Bild etwas zu warm). *Je Farbbild:* Auf der Stichprobe (Schritt 2.18) gilt x_c = (D_c − d_min_used_c) / max(d_white_c − d_min_used_c, 0,05), gemessen also mit der tatsächlich verwendeten Filmbasis (auch nach High-Key-Fallback). Mittelgrau sind die Pixel mit |x_G − 0,5| < 0,05; sind es (hochgerechnet auf das ganze innere Fenster) weniger als 200, wird nicht gemessen (k_Bild = 1). Sonst ist mid_c der Median von x_c dieser Pixel und k_Bild_c = ln 0,5 / ln(mid_c, begrenzt auf 0,05–0,95) für R und B; G behält 1. *Je Rollen-Gruppe:* Ein Rollenwert gilt nur bei ≥ 3 gemessenen Farbbildern, von denen für R und für B je ≥ 80 % auf derselben Seite von 0,5 liegen wie der Gruppenmedian; dann k_Rolle aus den Gruppenmedianen der mid-Werte (gleiche Formel), sonst k_Rolle = 1. *Ergebnis:* k_c = sqrt(k_Bild_c · k_Rolle_c), begrenzt auf 1 ± `crossover_limit` (0,15). Die Rolle dämpft so Bilder, deren Motivfarbe überwiegt (Schnee, warmes Abendlicht); ein Bild ohne gültigen Rollenwert bekommt die halbe Korrektur (im Logarithmus). SW-Bilder: k = 1. `crossover_limit = 0` schaltet die Korrektur ab.

### 4. Durchgang 2: Entwicklung und Ausgabe jeder Datei

In voller Auflösung, parallel; die Schritte einer Datei laufen in dieser Reihenfolge.

1. **Laden.** Wie in Durchgang 1, Schritt 1, aber in voller Auflösung.
2. **Dichte.** D = −log10(max(T, 1/65535)) je Kanal.
3. **Neutralisierung und Kanal-Normierung.** `d_min_used` = Filmbasis aus dem Rollen-Kontext, `d_white` aus Durchgang 1. Je Kanal d_hi = max(d_white − d_min_used, 0,05), D_target = Mittel der drei d_hi, D_norm = max(D − d_min_used, 0) · D_target / d_hi. Der Abzug der Filmbasis entfernt die orange Maske; die Skalierung gibt allen drei Kanälen denselben Dichteumfang, sodass Filmbasis und Weißpunkt neutral werden.
4. **Farbübergang und lineares Licht.** x = D_norm / D_target je Kanal, x' = x^k_c mit k aus Schritt 3.5 (Filmbasis 0 und Weißpunkt 1 bleiben fest, nur die Mitteltöne verschieben sich), dann Y = 10^((x' · D_target − D_target) / γ) mit γ = `gamma_color` (0,6) bzw. `gamma_bw` (0,65) gemäß der Rollen-Entscheidung. Der Weißpunkt wird 1,0, die Filmbasis der dunkelste Wert. Die Korrektur gehört zur Umkehrung, nicht zum Look: DNG, TIFF und JPEG enthalten sie gleichermaßen.
5. **Entzerren.** Drehung um den Winkel aus Durchgang 1 um die Mitte (bilinear, Ränder fortgesetzt).
6. **Ausrichtung.** Erst horizontal spiegeln (`mirror`), dann im Uhrzeigersinn um `rotate` drehen; das Zuschnitt-Rechteck folgt.
7. **Schwarzpunkt** (Bereich 3). b = 0,5-%-Perzentil der Luminanz (Mittel der Kanäle, jedes 4. Pixel) im inneren Fenster des ausgerichteten Zuschnitts. Wenn 0 < b < 0,99: Y = (Y − b) / (1 − b), derselbe Versatz für alle Kanäle. Die Werte werden hier nicht begrenzt: Was über dem Weißpunkt liegt, bleibt über 1, was unter dem Schwarzpunkt liegt, unter 0 (für das DNG).
8. **SW.** Bei SW-Bildern werden die drei Kanäle zu einem gemittelt.
9. **Farbraum** (nur Zuschnitt, für TIFF und JPEG). Die Werte werden auf 0–1 begrenzt (bei SW vor dem Mitteln der Kanäle), dann Kamera-RGB → lineares sRGB mit der Kameramatrix (dcraw-Verfahren: (XYZ → Kamera) · (sRGB → XYZ, D65), Zeilen so normiert, dass Neutral neutral bleibt, invertiert; unbrauchbare Matrix → Einheitsmatrix und eine Warnung). Negative Werte werden 0.
10. **sRGB-Kurve** (nur Zuschnitt). Standard-sRGB-Übertragungsfunktion (IEC 61966-2-1). Das Ergebnis ist das neutrale sRGB-Bild.
11. **Beschreibung.** Eine Zeile, z. B. `rfnegconv 26.10.7 | color | dmin=0.415,0.437,0.908 | fallback=no | crop=1:1 | crossover: R x1.102 B x0.874 (frame+roll) | crop: …` (Farbe/SW, verwendete Filmbasis, Rollen-Fallback, eingerastetes Format oder `uncertain`; Farbübergang mit k für R und B und Herkunft `frame+roll`, `frame only`, `roll only` oder `none` (keine Korrektur), fehlt bei `crossover_limit = 0`; am Ende `| crop: …` mit der Begründung des Zuschnitts). Die Log-Zeile ab `-v` lautet `<Datei>: crop <B>×<H>, crossover R x… B x… (…) — <Grund>`. Sie steht in allen drei Dateien (`ImageDescription`) und im Log.
12. **DNG** (wenn `dng = true`). Das *ganze* entzerrte und ausgerichtete Bild nach den Schritten 3–8 (neutral, linear, Kamera-RGB, Schwarzpunkt 0, Weißpunkt 1; SW als drei gleiche Kanäle), nicht beschnitten. `dng_finder_preview = false`: float16, Deflate mit Gleitkomma-Prädiktor, Kacheln 256 × 256, ohne Begrenzung: Lichter über dem Weißpunkt (> 1) und Schatten unter dem Schwarzpunkt (< 0) bleiben erhalten und lassen sich im Bildbearbeitungsprogramm zurückholen (nur NaN/Unendlich werden ersetzt und auf den float16-Bereich ±65504 begrenzt; Programme können Werte unter 0 beim Öffnen auf 0 setzen). `true`: uint16 unkomprimiert, auf 0–1 begrenzt (0–65535, BlackLevel 0, WhiteLevel 65535). Das erste Bild der Datei ist eine 8-bit-sRGB-Vorschau des neutralen beschnittenen Bildes aus den auf 0–1 begrenzten Werten (lange Kante ≤ 1024 px), das Hauptbild folgt als SubIFD. Tags: DNGVersion 1.4.0.0, UniqueCameraModel (Hersteller und Modell per exiftool, sonst `real-fast-negconv`), ColorMatrix1 = Kameramatrix, CalibrationIlluminant1 = D65, AsShotNeutral = (1, 1, 1), BaselineExposure = 0, Orientation = 1. Der Zuschnitt steht als eingebettetes Camera-Raw-XMP darin (`crs:ProcessVersion 11.0`, `HasCrop`, `CropTop/Left/Bottom/Right` relativ 0–1, `CropAngle 0`, `AlreadyApplied False`): In Lightroom oder Camera Raw lässt er sich zurücksetzen oder bis zum vollen Scan aufziehen.
13. **TIFF.** Das beschnittene sRGB-Bild mit der sanften Korrektur (Abschnitt 5). 16 bit, Deflate mit Prädiktor; Farbe als RGB mit eingebettetem sRGB-Profil, SW als ein Graukanal.
14. **JPEG.** Dasselbe korrigierte Bild wie das TIFF, nur komprimiert (kein zweiter Rechenweg). 8 bit, Qualität `jpeg_quality` (95); Farbe mit sRGB-Profil, SW als Graustufen.
15. **EXIF.** Ist exiftool vorhanden, werden alle Metadaten des RAW in jede Ausgabe kopiert (`-TagsFromFile … -all:all`), außer MakerNotes, Orientation, ImageDescription, Software, ImageWidth/ImageHeight, Camera-Raw-Einstellungen (`XMP-crs`) und den DNG-eigenen Farb-, Darstellungs- und Rohdaten-Tags (`DNG_TAGS` in `fileio/exiftool.py`), damit ein DNG als Eingabe nie seine Kameramatrix, sein Profil, seine Kalibrierung, seine Schwarz-/Weißwerte oder seinen Zuschnitt in unser DNG schreibt: DNGVersion, DNGBackwardVersion, DNGPrivateData, DNGAdobeData, UniqueCameraModel, LocalizedCameraModel, ColorMatrix1, ColorMatrix2, ColorMatrix3, CameraCalibration1, CameraCalibration2, CameraCalibration3, CameraCalibrationSig, ReductionMatrix1, ReductionMatrix2, ReductionMatrix3, ForwardMatrix1, ForwardMatrix2, ForwardMatrix3, CalibrationIlluminant1, CalibrationIlluminant2, CalibrationIlluminant3, IlluminantData1, IlluminantData2, IlluminantData3, AnalogBalance, AsShotNeutral, AsShotWhiteXY, AsShotICCProfile, AsShotPreProfileMatrix, AsShotProfileName, BaselineExposure, BaselineExposureOffset, BaselineNoise, BaselineSharpness, LinearResponseLimit, DefaultBlackRender, NoiseProfile, ProfileName, ProfileCopyright, ProfileEmbedPolicy, ProfileCalibrationSig, ProfileDynamicRange, ProfileGroupName, ProfileType, ProfileGainTableMap, ProfileGainTableMap2, ProfileHueSatMapDims, ProfileHueSatMapData1, ProfileHueSatMapData2, ProfileHueSatMapData3, ProfileHueSatMapEncoding, ProfileLookTableDims, ProfileLookTableData, ProfileLookTableEncoding, ProfileToneCurve, RawToPreviewGain, MakerNoteSafety, OpcodeList1, OpcodeList2, OpcodeList3, ActiveArea, MaskedAreas, BlackLevel, BlackLevelRepeatDim, BlackLevelDeltaH, BlackLevelDeltaV, WhiteLevel, LinearizationTable, ShadowScale, BayerGreenSplit, AntiAliasStrength, ChromaBlurRadius, BestQualityScale, DefaultScale, DefaultCropOrigin, DefaultCropSize, DefaultUserCrop, ColumnInterleaveFactor, RowInterleaveFactor, RawImageDigest, NewRawImageDigest, OriginalRawFileData, OriginalRawFileDigest, RawImageSegmentation, ColorimetricReference, CacheVersion, EnhanceParams, DepthFormat, DepthNear, DepthFar, DepthUnits, DepthMeasureType, SemanticName, SemanticInstanceID, JXLDistance, JXLEffort, JXLDecodeSpeed; Vorschaubilder des RAW werden nicht übernommen, Orientation wird auf 1 gesetzt. Ein Fehler hier ergibt nur eine Warnung.
16. **Schreiben.** Jede Datei wird zuerst als `.<name>.tmp.<pid>.<zufall><endung>` neben dem Ziel geschrieben und dann in einem Schritt umbenannt; eine halb geschriebene Datei trägt nie den endgültigen Namen.
17. **Archiv.** Das Original wird nach `Archiv/` verschoben (`<name>_2.<endung>` usw., wenn der Name belegt ist). Auf demselben Laufwerk ist das ein Umbenennen. Auf ein anderes Laufwerk wird die Datei zuerst als `.<name>.<endung>.tmp.<pid>.<zufall>` in `Archiv/` kopiert, auf den Datenträger geschrieben (fsync), dann umbenannt und erst danach am alten Ort gelöscht; scheitert das Löschen, wird die Kopie wieder entfernt. Eine halb kopierte Datei trägt also nie den endgültigen Namen. Erst jetzt gilt die Datei als erledigt (Log-Zeile `OK <name> - <Beschreibung>`).
18. **Fehler.** Scheitert etwas in den Schritten 1–17, werden die bereits geschriebenen Ausgaben dieser Datei wieder gelöscht. Ist die Datei selbst schuld (RAW unlesbar oder beschädigt, JPEG lässt sich nicht kodieren, sonstiger Fehler bei Analyse oder Entwicklung), wandert das Original nach `Negative/_Fehler/` mit einer Textdatei `<name>.txt`: „<name> konnte nicht verarbeitet werden.“, „Grund: …“ (einfaches Deutsch: RAW unlesbar oder beschädigt, sonst „Unerwarteter Fehler.“), „Technisch: …“ (Text der Ausnahme) und „Zeitpunkt: …“. Liegt der Grund in der Umgebung – ein Fehler des Dateisystems (kein Speicherplatz, keine Berechtigung, schreibgeschützt, Lese-/Schreibfehler) oder zu wenig Arbeitsspeicher (auch in LibRaw) –, bleibt das Original unverändert in `Negative/`; das gilt auch, wenn das RAW aus einem dieser Gründe nicht gelesen werden konnte. Eine fehlerhafte Datei hält den Lauf nie an; nur ein voller Datenträger beendet den Lauf: Die übrigen Dateien bleiben unberührt in `Negative/`.

Nach dem Lauf: Zusammenfassung im Log, Konsolenausgabe `N converted, M failed` (Exit-Code 1, wenn etwas fehlschlug) und bei Dateien, die wegen der Umgebung in `Negative/` blieben, eine Zeile mit dem Grund, z. B. „Kein Speicherplatz mehr frei. Verarbeitung angehalten: 3 Fotos fertig, die übrigen Negative bleiben im Ordner „Negative“.“ oder „Keine Berechtigung zum Schreiben/Lesen. 1 Negativ bleibt unverändert im Ordner „Negative“; 11 Fotos fertig.“ Mitteilung „N Fotos fertig, M Fehler“ (mit diesem Grund, falls vorhanden), wenn `notify = true` und etwas verarbeitet wurde; der Watch-Modus zeigt denselben Grund nicht noch einmal, solange kein Bild fertig wird.

### 5. Sanfte Korrektur im Detail

Steckt in TIFF und JPEG, auf beide gleich (ein Bild wird einmal korrigiert und zweimal geschrieben); das DNG bleibt neutral. Im Code heißt sie „look“ (`core/look.py`). Sie ändert die Helligkeit nie: kein Auf- oder Abhellen, keine Belichtungskorrektur. Sie korrigiert nur, was Film, Scan und Inversion flau machen: Kontrast und, bei blassen Farbbildern, Sättigung.

**Eingaben.** Zwei Messwerte je Bild, gemessen auf dem neutralen sRGB-Vorschaubild des Zuschnitts (nach Farbübergang, Schwarzpunkt, Kameramatrix und sRGB-Kurve; Schritt 2.17 bzw. Schritt 3.4 mit neu gemessenem k) im inneren Fenster (`measure_inset`), jedes 4. Pixel (`SAMPLE_STEP`), Werte auf 0–1 begrenzt:

- **Spread** = 95-%- minus 5-%-Perzentil der Luminanz (Gewichte 0,2126, 0,7152, 0,0722).
- **Chroma** = Mittel von (größter − kleinster Kanal) je Pixel; bei SW 0.

**Rollen-Gruppe.** Spread und Chroma, aus denen die Parameter folgen, sind der Median über alle Bilder der Gruppe (Bilder mit High-Key-Fallback zählen nicht, solange die Gruppe andere hat); ein Einzelbild nutzt seine eigenen Werte. Alle Bilder einer Gruppe bekommen damit dieselben Parameter, und eine Rolle sieht gleichmäßig aus.

**Formeln und Konstanten** (alle in `core/look.py`):

| Schritt | Formel | Konstanten |
|---------|--------|------------|
| Kontrast | s = Stärke · clip(`SPREAD_TARGET` − Spread, 0, `MAX_CONTRAST`) | `SPREAD_TARGET` = 0.70, `MAX_CONTRAST` = 0.35 |
| Stärke | Farbe 1.0, SW 0.5 | `COLOR_STRENGTH`, `BW_STRENGTH` |
| S-Kurve | y = (1 − s) · x + s · (3x² − 2x³), je Kanal | – |
| Sättigung (nur Farbe) | sat = clip(1 + `SAT_GAIN` · (`CHROMA_TARGET` − Chroma), 1, `MAX_SATURATION`) | `CHROMA_TARGET` = 0.10, `SAT_GAIN` = 1.5, `MAX_SATURATION` = 1.15 |
| Chroma-Gewichtung | c = größter − kleinster Kanal; Faktor = 1 + (sat − 1) · (1 − clip(c / `CHROMA_FULL`, 0, 1)); y = L + (x − L) · Faktor | `CHROMA_FULL` = 0.5 |

Zum Schluss werden alle Werte auf 0–1 begrenzt. Die S-Kurve lässt 0, 0,5 und 1 unverändert; sie vertieft Schatten und hellt Lichter leicht an, der Mittelton bleibt. Die Sättigung wirkt nur auf blasse Pixel (kleines c) voll, kräftige behalten ihre Farbe.

**Was sie nie tut:** keine Belichtungsänderung, kein Aufhellen dunkler oder Abdunkeln heller Aufnahmen, keine Farbtonänderung, keine Wirkung auf das DNG und keine Abhängigkeit vom Ausgabeformat. Die Normierung auf Weiß- und Schwarzpunkt je Bild (Schritte 4.4 und 4.7) gehört nicht zur sanften Korrektur, sondern zur Umkehrung; sie wirkt auch im DNG.

**Wirkung an Beispielbildern** (beschrieben nur durch ihre Messwerte; Zahlen aus den Formeln oben):

| Beispielbild | Spread | Chroma | Kontrast s | Sättigung |
|--------------|--------|--------|------------|-----------|
| Normales Farbnegativ mit vollem Tonumfang | 0.75 | 0.15 | 0 (keine Änderung) | 1.00 |
| Leicht flaues Farbnegativ | 0.60 | 0.08 | 0.10 | 1.03 |
| Flaues, blasses Farbnegativ | 0.50 | 0.04 | 0.20 | 1.09 |
| Sehr flaues, farbarmes Farbnegativ | 0.30 | 0.02 | 0.35 (Obergrenze) | 1.12 |
| Flaues SW-Negativ (halbe Stärke) | 0.50 | – | 0.10 | – |

Bei s = 0,20 wird der Grauwert 0,25 zu 0,231 und 0,75 zu 0,769, 0,50 bleibt 0,50. Bei Sättigung 1,09 wächst der Abstand eines blassen Pixels (c = 0,05) zu seinem Grauwert L um den Faktor 1,081; ein kräftiges (c ≥ 0,5) bleibt unverändert.

### Was das Programm nicht tut

- Keine KI, keine trainierten Modelle, kein Cloud- oder Netzwerkzugriff.
- Keine automatische Lageerkennung: `rotate`/`mirror` gelten für alle Dateien gleich (ein Wert je Scan-Aufbau).
- Keine Staub-, Kratzer- oder Rauschentfernung. Ohne Infrarot-Kanal (wie bei Flachbettscannern mit ICE) ist Staub nicht sicher von Bilddetails wie Lichtreflexen oder Sternen zu unterscheiden, und Korn gehört zum Film. Dafür eignen sich Bildbearbeitungsprogramme, in denen das Ergebnis geprüft werden kann. Tipp: Negative vor dem Abfotografieren entstauben und den Scan so belichten, dass die Filmbasis nicht zu dunkel wird (zu knapp belichtete Scans zeigen nach der Umkehrung deutlich mehr Rauschen).
- Kein Schärfen.
- Keine manuellen Korrekturen je Bild und keine Bedienoberfläche; Feinarbeit erfolgt danach im DNG mit einem Programm nach Wahl.
- Kein Diafilm (Positive) und keine Filmprofile.
- Zeigt ein Scan mehrere Bildfelder, wird nur das breiteste ausgegeben.
- Sichtbare Perforation (Kleinbild) und Masken mit abgerundeter Öffnung werden nicht zuverlässig beschnitten; das DNG enthält das volle Bild.
- Keine Unterordner: nur Dateien direkt in `Negative/` werden verarbeitet.
- Es werden keine XMP-Begleitdateien geschrieben oder gelesen.

## Ausgaben

Je RAW `<name>.<endung>` entstehen in `Fotos/` drei Dateien (ohne DNG bei `dng = false`):

| Datei | Inhalt | Zuschnitt | Farbe | Korrektur | Größe je Megapixel |
|-------|--------|-----------|-------|-----------|--------------------|
| `<name>.dng` | linear, float16 Deflate ohne Begrenzung auf 0–1 (oder uint16 unkomprimiert, 0–1), eingebettete Vorschau | voller Scan, Zuschnitt als zurücksetzbare Einstellung | Kamera-RGB mit Farbmatrix | neutral | ca. 3,6 MB (uint16: ca. 6,1 MB) |
| `<name>.tif` | 16 bit, sRGB-Kurve, Deflate | beschnitten | sRGB (SW: Grau) | sanft (Abschnitt 5) | ca. 3,3 MB |
| `<name>.jpg` | 8 bit, Qualität 95 | beschnitten | sRGB (SW: Grau) | sanft, wie das TIFF | ca. 0,2–0,4 MB |

Die Größen wachsen mit der Pixelzahl und hängen vom Bildinhalt ab (Korn und Rauschen vergrößern TIFF und JPEG); die Tabelle gibt grobe Richtwerte je Megapixel an. Die drei Dateien eines RAW tragen immer denselben Namen. Existiert `<name>.dng`, `.tif` oder `.jpg` bereits in `Fotos/` (oder haben zwei RAWs eines Laufs denselben Namen), wird für alle drei `<name>_2`, `<name>_3` … verwendet. Nichts wird überschrieben.

**Warum dieser Zuschnitt?** Jedes Bild nennt den Grund für Zuschnitt und Drehung, im Log und in den Dateien. Mit `-v` zeigt die Konsole eine Zeile pro Datei, die Log-Datei hat sie immer (INFO):

```
scan_0001.ARW: crop 6178×6178 — rotated 0.54° (frame edges); snapped to 1:1; width: left edge + right edge anchored, excess 4.3 % of the width taken from the left
```

Die Größe ist die Ausgabegröße in Pixeln. Der Grund nennt in dieser Reihenfolge nur das, was zutrifft: die Drehung (`rotated 0.54° (frame edges)`, `rotated 0.21° (film outline)`, `not rotated (abs angle 0.12° < 0.2°)`, `rotated pass uncertain, kept unrotated`), `bare light (no film) ignored for the film base`, `translucent holder strips removed (left 4.2 %, right 7.3 % of the image side)`, das Format (`snapped to 3:2` oder `no format (crop uncertain, full film area kept)`) und je Achse, welche Bildkanten verankert waren und wo der Überschuss abgenommen wurde (`height: bottom edge anchored, excess 3.2 % of the height taken from the top`). Größen im Grund sind Prozent der Bildseite entlang dieser Achse. Derselbe Text steht in der Bildbeschreibung von DNG, TIFF und JPEG nach `crop: ` (z. B. im exiftool-Feld `ImageDescription`; das Gradzeichen erscheint dort als `deg`).

## Befehle und Optionen

| Befehl / Option | Beschreibung |
|-----------------|--------------|
| `rfnegconv` | Ohne Befehl: `Negative/` einmal verarbeiten (wie `run`) |
| `rfnegconv run` | `Negative/` einmal verarbeiten |
| `rfnegconv watch` | Dauerhaft laufen und neue Dateien verarbeiten (Strg+C beendet) |
| `rfnegconv service install` | Hintergrunddienst einrichten und starten |
| `rfnegconv service status` | Zeigen, ob der Dienst eingerichtet ist und läuft, die beiden Log-Dateien und welches exiftool benutzt wird |
| `rfnegconv service uninstall` | Hintergrunddienst entfernen |
| `rfnegconv config init --negative PATH --photos PATH --archive PATH` | Konfiguration mit diesen Ordnern schreiben, nur wenn noch keine existiert; die konfigurierten Ordner anlegen; gibt `config=`, `status=created\|kept`, `negative=`, `photos=`, `archive=` aus |
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
| `run --summary` | Für Starter: gibt nur die Zeile `processed=<n> failed=<m> busy=<0\|1>` aus (verarbeitet, fehlgeschlagen, Ordner belegt); keine Desktop-Mitteilung. Blieben Dateien wegen der Umgebung in `Negative/` (z. B. Speicher voll), stattdessen `Error: <Grund>` mit Exit-Code 1 |

Globale Optionen (`--config`, `-Q`, `-v`, `-vv`) stehen vor dem Befehl, z. B. `rfnegconv -v run --photos ~/Film/Fotos --no-dng`. Exit-Codes: 0 = alles erledigt (auch wenn der Ordner belegt war), 1 = mindestens eine Datei fehlgeschlagen oder Konfigurations- bzw. Ordnerfehler. Mit `run --summary` steht das Ergebnis in der Zeile; der Exit-Code ist dann nur bei einem Fehler vor der Verarbeitung (z. B. Konfiguration, Ordner nicht erreichbar) oder bei Dateien, die wegen der Umgebung in `Negative/` blieben, 1. Fehler des Betriebssystems erscheinen immer als eine Zeile `Error: …`, nie als Python-Traceback.

## Unterstützte Kameras und Formate

Alles, was LibRaw 0.22 liest, mit den Endungen `.arw .sr2 .raf .nef .nrw .cr2 .cr3 .orf .rw2 .pef .srw .dng`. Das Sensorformat der Kamera spielt keine Rolle: Erkannt wird das Bildfeld auf dem Film.

## Fehlersuche

- **Eine Datei liegt in `Negative/_Fehler/`:** Die `.txt` daneben nennt den Grund. Nach Behebung der Ursache das RAW zurück nach `Negative/` schieben.
- **„Ordner nicht erreichbar“, „Kein Speicherplatz mehr frei“ oder „Keine Berechtigung“:** Laufwerk anschließen, Platz schaffen oder die Berechtigung prüfen (macOS: Systemeinstellungen › Datenschutz & Sicherheit, z. B. „Festplattenvollzugriff“ oder „Wechselmedien“ für den Dienst). Die RAW-Dateien liegen unverändert in `Negative/`; danach „Negative entwickeln“ starten. Der Dienst nimmt sie erst wieder auf, wenn sie sich ändern oder er neu gestartet wird.
- **Es passiert nichts:** `rfnegconv service status` zeigt, ob der Dienst läuft und wo die Log-Datei liegt. Ohne Dienst: `rfnegconv run` von Hand starten.
- **Fehlermeldung zur Konfiguration:** Sie nennt den fehlenden oder falschen Schlüssel und den Pfad der Konfigurationsdatei.
- **„Der Dienst verarbeitet gerade …“:** Ein anderer Lauf arbeitet am Ordner; später erneut versuchen.
- **Bilder stehen Kopf oder sind gespiegelt:** `rotate` und/oder `mirror` setzen und neu verarbeiten.
- **Zuschnitt falsch:** Im DNG lässt sich der Zuschnitt in Lightroom/Camera Raw zurücksetzen. `crop=uncertain` in der Beschreibung heißt: Die Erkennung war unsicher und hat den ganzen Filmstreifen verwendet.
- **Keine Kameradaten in den Dateien:** exiftool ist nicht installiert oder wird nicht gefunden (Warnung im Log; `rfnegconv service status` zeigt das gefundene exiftool). Ist `exiftool_path` gesetzt, gilt nur dieser Pfad (fehlt die Datei dort, läuft das Programm ohne exiftool); sonst wird im `PATH` gesucht, dann die Kopie des Installers im Programmdatenordner. Den Installer erneut ausführen, exiftool installieren oder `exiftool_path` setzen.

Log-Dateien: `rfnegconv.log` (Hintergrunddienst) und `rfnegconv-run.log` (einzelne Läufe: „Negative entwickeln“, `rfnegconv run`), getrennt, damit sich zwei gleichzeitig laufende Prozesse nicht in die Quere kommen; je 5 Dateien zu je 5 MB im Wechsel. Unter macOS zusätzlich `service.out.log`/`service.err.log` des Dienstes.

| System | Ordner |
|--------|--------|
| macOS | `~/Library/Logs/real-fast-negconv/` |
| Linux | `~/.local/state/real-fast-negconv/log/` |
| Windows | `%LOCALAPPDATA%\real-fast-negconv\Logs\` |

## Entwicklung

```bash
git clone git@github.com:jcmx9/real-fast-negconv.git
```

```bash
cd real-fast-negconv && uv sync
```

```bash
uv run ruff check --fix . && uv run ruff format . && uv run mypy src/
```

Entwicklungsläufe nutzen immer einen isolierten App-Ordner, damit eine echte Installation unberührt bleibt (Konfiguration, Logs, Daten, exiftool und Dienstdateien liegen dann darunter; Dienstbefehle wie `launchctl` werden nicht ausgeführt, nur angezeigt):

```bash
RFNEGCONV_HOME=.devhome uv run rfnegconv --help
```

Die Umgebungsvariable `RFNEGCONV_HOME` verlegt alle Programmordner nach `<RFNEGCONV_HOME>/config`, `log`, `data` und `service`. Der Ordner `.devhome/` ist von Git ausgeschlossen. Für die Entwicklung nie `uv tool install` verwenden: Das würde eine echte Installation überschreiben.

Die Testsuite wird getrennt gepflegt und nicht veröffentlicht; dieses Repository enthält nur den Quellcode.

## Versionierung

Das Projekt nutzt [CalVer](https://calver.org/) im Format `YY.M.MICRO` (z. B. `26.10.7`); Entwicklungsversionen tragen `.devN`. Releases entstehen mit [bump-my-version](https://github.com/callowayproject/bump-my-version) und `scripts/release.sh`.

## Mitwirken

Siehe [CONTRIBUTING.md](CONTRIBUTING.md). Kurzfassung: Branch von `dev` abzweigen, mit Conventional Commits committen, Pull Request gegen `dev` öffnen.

## Sicherheit

Sicherheitslücken bitte **nicht** über öffentliche Issues melden. Siehe [SECURITY.md](SECURITY.md).

## Changelog

Siehe [CHANGELOG.md](CHANGELOG.md).

## Lizenz

MIT, siehe [LICENSE](LICENSE).
