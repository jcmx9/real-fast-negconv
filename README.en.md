# real-fast-filmlab

**Version 26.11.1** · [Deutsch](README.md)

> Automatically converts camera RAW scans of film negatives (colour and black and white) into DNG, TIFF and JPEG positives.

[![CI](https://github.com/jcmx9/real-fast-filmlab/actions/workflows/ci.yml/badge.svg)](https://github.com/jcmx9/real-fast-filmlab/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

## Update

To get the latest version, run the same command as for the installation. macOS and Linux (Terminal):

```bash
curl -LsSf https://raw.githubusercontent.com/jcmx9/real-fast-filmlab/main/install.sh | sh
```

Windows (PowerShell):

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/jcmx9/real-fast-filmlab/main/install.ps1 | iex"
```

Settings, folders and images are kept; the switches in the configuration stay as they are (an update without an option switches nothing, see [Installer options](#installer-options)). The configuration only gets the keys it lacks. The program never updates itself; with `update_check = true` it points out a new version (see [Notice of new versions](#notice-of-new-versions)). Manually with uv: see [For advanced users](#for-advanced-users-manually-with-uv).

While the program is replaced, the background service is stopped; afterwards it runs again, also when the update fails or is interrupted (then with the previous version). If the program is converting outside the service (for example via „Negative entwickeln“ or `rffilmlab` in a terminal), the update stops with the hint „Gerade läuft eine Verarbeitung (zum Beispiel „Negative entwickeln“). Sie wird nicht unterbrochen – bitte warten, bis sie fertig ist, und das Update dann erneut starten.“ (a conversion is running, for example „Negative entwickeln“; it is not interrupted – please wait until it has finished, then start the update again) and changes nothing.

## Principles

- **Fully automatic.** Drop RAW files into a folder, get finished pictures. No user interface, and no settings are needed for daily use; the configuration is written once (three folders, optionally orientation).
- **Traceable and transparent.** Every decision follows fixed, documented rules and thresholds; all of them are described below, with the names of the constants in the code. Every output file carries a line saying how it was processed (colour/BW, film base, roll fallback, crop).
- **Deterministic.** The same RAW files in the same batch, the same configuration and the same program version give bit-identical DNG, TIFF and JPEG files on the same operating system (checked on real files, including the EXIF copy). For every program version the installer installs exactly the library versions from `constraints.txt` (generated from `uv.lock`, e.g. LibRaw 0.22 via rawpy). Note: within a batch, frames of the same film influence each other (roll context), so the result of a frame also depends on which frames were processed together with it.
- **White and black point per frame.** Every frame is normalised to its own white point (99.5th percentile of the density in the inner window) and black point (0.5th percentile of the luminance there). This is a deliberate normalisation that only the program can do, because it measures every frame: the bright and dark detail of a frame then spans the whole tonal range. A deliberately dark or low-contrast subject (night, fog) is stretched to the full range as well. The frames of a film do not share white and black point. Beyond that there is no exposure correction.
- **No AI.** No neural networks, no trained models, no machine learning, no cloud. Only classical image processing (logarithms, percentiles, morphology, contours, rotation) with fixed numbers.
- **Safe for originals.** RAW files are only read and then moved to the archive. Existing outputs are never overwritten. Every file is written to a temporary file first and only renamed when complete; this also applies to moving into the archive on another drive. If a folder is unreachable, full or not writable, the RAW files stay unchanged in `Negative/`.

## Requirements

- macOS, Windows 10/11 or Linux and an internet connection for the installation. No administrator rights needed.
- The installer sets up everything else (see below). Only for the manual installation: [uv](https://docs.astral.sh/uv/) (installs a suitable Python ≥ 3.12 on its own), git and [exiftool](https://exiftool.org/) (recommended, copies camera metadata): `brew install exiftool` (macOS), `winget install OliverBetz.ExifTool` (Windows) or your distribution's package manager (Linux). Without exiftool everything works, the outputs just carry no camera data.
- Linux only: Perl for exiftool (usually present) and, for notifications, `notify-send` (e.g. package `libnotify-bin` on Debian/Ubuntu)

## Installation

One command sets up everything. macOS and Linux (Terminal):

```bash
curl -LsSf https://raw.githubusercontent.com/jcmx9/real-fast-filmlab/main/install.sh | sh
```

Windows (PowerShell):

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/jcmx9/real-fast-filmlab/main/install.ps1 | iex"
```

**Update:** run the same command again (see [Update](#update)).

The installer

1. sets up [uv](https://docs.astral.sh/uv/) if it is missing (uv brings its own Python),
2. installs real-fast-filmlab in the version that belongs to the installer, with the library versions fixed for it (`constraints.txt` of that version),
3. creates the folders `rffilmlab/Negative`, `Fotos` and `Archiv` in the user's Pictures folder (macOS and Linux `~/Pictures`, Windows „Bilder“) and writes the complete configuration: every key with its value and a short comment, all switches `true`. If a configuration exists already, its folders and values apply; it only gets missing keys, each with the value that applied so far (a missing `service` with the current state: service set up – `true`, otherwise `false`). Switches given as options are set to `false` (see [Installer options](#installer-options)),
4. sets up the background service according to the switch `service`: `true` sets it up and starts it, `false` removes an existing one,
5. puts the shortcuts „Negative“ and „Fotos“ on the desktop (your own shortcuts of the same name are left alone),
6. creates the program „Negative entwickeln“ (develop negatives): macOS in the user's Applications folder (`~/Applications`), Windows in the Start menu, Linux in the application menu (`~/.local/share/applications`); your own program of the same name is left alone,
7. sets up exiftool last if it is missing (macOS with Homebrew via `brew`, otherwise the official package from exiftool.org with a verified checksum in the app data folder; on Linux only if Perl is present). This usually takes at most about a minute. If the server is unreachable, the installer gives up after about 20 seconds (connecting takes at most 10 seconds, with one retry; a refused connection fails at once). With curl a download takes at most about 2 minutes including a retry, the exiftool package at most about 10 minutes; if that fails, it is loaded once from the mirror (again at most about 10 minutes). On Windows a download stops when the server does not answer for 30 seconds (no retry); the exiftool package has at most 10 minutes and is loaded once from the mirror if that fails. Without curl, with wget, there is no overall limit: a download stops as soon as no data arrives for 10 seconds and is retried once. The installation via Homebrew has no time limit. If it fails, a hint appears and everything else is set up anyway,
8. shows the version, the service status and where the folders are. If `rffilmlab` is not found in the terminal afterwards, open a new terminal window.

An update only stops the background service and starts it again afterwards; if a run via „Negative entwickeln“ is in progress, it is not interrupted, the update stops with a hint instead, changes nothing and can be repeated afterwards.

After that it is enough to put scans into the „Negative“ folder; the pictures appear in „Fotos“ automatically. If you do not want to wait, start „Negative entwickeln“.

### Installer options

Each option sets a switch in the configuration to `false`:

| macOS, Linux | Windows | Switch | Effect |
|--------------|---------|--------|--------|
| `--ohne-dng` | `-OhneDng` | `dng = false` | no DNG files |
| `--ohne-tiff` | `-OhneTiff` | `tiff = false` | no TIFF files |
| `--ohne-kontaktabzug` | `-OhneKontaktabzug` | `contact_sheet = false` | no contact sheet after a run |
| `--ohne-dienst` | `-OhneDienst` | `service = false` | no background service (an existing one is removed); processing then starts only via „Negative entwickeln“ |

Precisely:

- A run of the installer changes only the switches given as options. All others keep the value in the configuration – also on an update without an option.
- An option only switches off. A switch is switched on by replacing `false` with `true` in the configuration file (location see [Configuration](#location-of-the-configuration-file)). For `service` the next run („Negative entwickeln“, `rffilmlab run` or the installer) then sets up the service again.
- Options can be combined. JPEG is always written.

Example without service and without TIFF, macOS and Linux:

```bash
curl -LsSf https://raw.githubusercontent.com/jcmx9/real-fast-filmlab/main/install.sh | sh -s -- --ohne-dienst --ohne-tiff
```

Windows (PowerShell):

```powershell
powershell -ExecutionPolicy ByPass -c "& ([scriptblock]::Create((irm https://raw.githubusercontent.com/jcmx9/real-fast-filmlab/main/install.ps1))) -OhneDienst -OhneTiff"
```

### For advanced users: manually with uv

Install uv (once), macOS and Linux:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Windows (PowerShell):

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Install real-fast-filmlab (needs git):

```bash
uv tool install git+https://github.com/jcmx9/real-fast-filmlab.git
```

Without `--constraints` uv resolves the newest matching libraries; the same versions as the installer are obtained with `--constraints constraints.txt` using the file from the repository.

Update to the latest version (the configuration is kept; `config init` afterwards adds missing keys):

```bash
uv tool install --force git+https://github.com/jcmx9/real-fast-filmlab.git
```

Create the folders and the complete configuration (an existing one only gets missing keys; `--off SWITCH` sets a switch to `false`) and start the service:

```bash
rffilmlab config init --negative ~/Pictures/rffilmlab/Negative --photos ~/Pictures/rffilmlab/Fotos --archive ~/Pictures/rffilmlab/Archiv
```

```bash
rffilmlab service install
```

## Uninstall

macOS and Linux:

```bash
curl -LsSf https://raw.githubusercontent.com/jcmx9/real-fast-filmlab/main/install.sh | sh -s -- --uninstall
```

Windows (PowerShell):

```powershell
powershell -ExecutionPolicy ByPass -c "& ([scriptblock]::Create((irm https://raw.githubusercontent.com/jcmx9/real-fast-filmlab/main/install.ps1))) -Uninstall"
```

This removes the background service, the program, „Negative entwickeln“ and the desktop shortcuts the installer created (only if they still point to the folders); exiftool and uv only if the installer set them up itself (recorded in the file `installer-state` in the app data folder). uv's managed Python and uv's tool folder are removed only if the installer set up uv itself and `uv tool list` succeeds and reports that no other uv tools remain. **The folders, the images, the configuration and the log files are never deleted.** If the installer set up uv, uv's download cache is also cleared. Manually: `rffilmlab service uninstall`, then `uv tool uninstall real-fast-filmlab`.

## Folders and daily use

The program works with three folders that you choose once in the configuration (the names are up to you; here: `Negative`, `Fotos`, `Archiv`):

| Folder | Key | Purpose |
|--------|-----|---------|
| `Negative/` | `negative_dir` | Inbox: put RAW files here |
| `Fotos/` | `photos_dir` | Results: `<name>.dng`, `<name>.tif`, `<name>.jpg` |
| `Archiv/` | `archive_dir` | Originals after successful processing |

Daily use:

1. Copy the RAW files of a film into `Negative/` – ideally the whole film at once, because frames of the same film are matched to each other.
2. Start processing (program „Negative entwickeln“, `rffilmlab run`, or nothing at all when the background service runs).
3. The pictures appear in `Fotos/`, the originals move to `Archiv/`.
4. If a file itself is faulty (unreadable or damaged RAW, analysis failed), it moves to `Negative/_Fehler/`; next to it is a `.txt` file with the reason in plain words. If the cause lies elsewhere (storage full, no permission, drive disconnected, not enough memory), the file stays in `Negative/` and a message gives the reason.
5. To create a picture again (e.g. after changing the configuration), move the RAW from `Archiv/` back into `Negative/`. Existing results are kept; the new ones are called `<name>_2` and so on.

### Program „Negative entwickeln“

Where to find it: on macOS in the „Programme“ (Applications) folder inside your own home folder (in the Finder: Go › Home › Applications), and via Launchpad or Spotlight (type „Negative entwickeln“); on Windows in the Start menu, on Linux in the application menu.

One click processes the `Negative/` folder once. At the start a short notice „Negative werden entwickelt …“ (developing negatives) appears and disappears by itself; then a small window with „OK“ reports the result:

| Message | Meaning |
|---------|---------|
| „12 Fotos fertig.“ | Everything converted (12 pictures done) |
| „12 Fotos fertig, 1 Fehler – Details in Negative/_Fehler.“ | One file failed; the reason is in `Negative/_Fehler/` |
| „Keine neuen Negative gefunden.“ | `Negative/` contained no RAW files (no new negatives found) |
| „Wird gerade im Hintergrund verarbeitet.“ | The service (or another run) is working right now; it takes care of the files (being processed in the background) |
| „Die Negative konnten nicht entwickelt werden.“ | With the reason below, e.g. „Ordner nicht erreichbar: … – ist das Laufwerk angeschlossen?“ (folder not reachable – is the drive connected?), „Kein Speicherplatz mehr frei. Verarbeitung angehalten: …“ (no space left, processing stopped) or a faulty configuration (the negatives could not be developed) |

Further lines appear below only when needed: one per problem of the [self-check](#self-check) (e.g. „Wenig Speicherplatz frei: 1,5 GB …“, little free space) and, if there is a new version, „Neue Version X verfügbar – siehe Update-Abschnitt auf der Projektseite.“ (new version X available – see the Update section on the project page). The window then has a second button „Projektseite öffnen“ (open project page) that opens the section [Update](#update) of this page in the browser (Windows: buttons „Ja“/„Nein“ (yes/no) to the question „Projektseite öffnen?“; Linux without zenity and kdialog: the address is in the message).

Processing a whole film can take a few minutes; the result message appears only afterwards. There is no second program or button for the check. The program runs `rffilmlab -Q run --summary` (the path to `rffilmlab` and, on macOS and Linux, the `PATH` are filled in at installation). Implementation: macOS `~/Applications/Negative entwickeln.app` with a shell script and an AppleScript dialog; Windows `Negative entwickeln.lnk` in the Start menu, which starts `negative-entwickeln.vbs` in the app data folder with `wscript.exe`; Linux `negative-entwickeln.desktop`, which starts `negative-entwickeln.sh` in the app data folder and shows the result with zenity, kdialog or notify-send (whichever is present; the notice at the start only with notify-send).

### Without a terminal: double-click starters

`scripts/rffilmlab.command` (macOS) and `scripts/rffilmlab.bat` (Windows) process the `Negative/` folder once and keep the window open until you press a key. Copy the file from the repository to the desktop, for example. Starting it while the background service is working is harmless: a lock file in `Negative/` prevents double processing, and the starter reports „Der Dienst verarbeitet gerade – bitte später erneut versuchen.“ (the service is busy, try again later).

### Background service

The service watches `Negative/`, waits until copying has finished and then processes the files on its own. It starts at every login. At the end of each batch a desktop notification shows „N Fotos fertig, M Fehler“ (N pictures done, M errors), with the reason added for a folder problem. If a folder is unreachable (e.g. external drive disconnected), the service reports this once (log and notification) and keeps retrying quietly until the folder is back. If a full disk stopped a batch, the service starts no new batch until the drive of `Fotos/` has at least 1 GB more free than when it stopped or 10 minutes have passed (new files in `Negative/` wait until then). Then it retries the remaining negatives automatically. Before each batch it checks itself quietly ([self-check](#self-check)); each problem appears as one notification, and again only when it has changed or has gone and come back. It reports a new version once with „Neue Version X verfügbar – siehe Update-Abschnitt auf der Projektseite“. Only one service runs per user; a second start ends at once. When the system ends the service (logout, update on macOS and Linux), it finishes the files in work and starts no further one.

**The service follows the switch `service`.** Every run („Negative entwickeln“, `rffilmlab run`) and every run of the installer reconciles it: `service = true` and no service set up – set it up and start it; `service = false` and a service set up – remove it. If it already is as the switch says, nothing is touched. This applies only to runs with the normal configuration file (the service always uses that one); a run with `--config OTHER.toml` neither changes nor checks the service. The service itself re-reads the configuration before each of its batches: changed switches apply from its next batch; changed folders only after the service restarts (e.g. at the next login); if the file is faulty, it keeps working with the last valid settings and reports this once; if it is already faulty when the service starts, the service reports this once („Konfiguration fehlerhaft – die automatische Verarbeitung wartet auf die Korrektur: …“) and begins as soon as the file is corrected. On Windows a running service ends after its current batch once `service = false` is set. The commands below act at once; at the next run, however, the switch applies again. To switch it off for good: set `service = false` or install with `--ohne-dienst`.

```bash
rffilmlab service install
```

```bash
rffilmlab service status
```

```bash
rffilmlab service uninstall
```

Implementation: macOS LaunchAgent `~/Library/LaunchAgents/io.github.jcmx9.rffilmlab.plist` (restarted after a crash), Windows `rffilmlab.vbs` in the startup folder (no admin rights needed), Linux systemd user unit `~/.config/systemd/user/rffilmlab.service` (`Restart=on-failure`). The service runs `rffilmlab -Q watch`; the `PATH` at installation time is taken over so that exiftool is found.

### Self-check

Before every run („Negative entwickeln“, `rffilmlab run`) and before every batch of the service the program checks quietly:

| Check | Message only for a problem |
|-------|----------------------------|
| The three folders are reachable and writable | „Ordner nicht erreichbar: …“ (folder not reachable) or „Keine Berechtigung für den Ordner: …“ (no permission); a run then does not start (the service reports folder problems itself, see above) |
| Free space on the drive of `Negative/` and `Fotos/` at least 2 GiB (about 2.1 GB; the message gives GB like Finder and Explorer) | „Wenig Speicherplatz frei: 1,5 GB auf dem Laufwerk mit dem Ordner „Fotos“.“ (little free space) |
| exiftool is found | „exiftool wurde nicht gefunden – die Fotos bekommen keine Kameradaten.“ (exiftool not found, no camera data) |
| New files in `Negative/_Fehler/` since the last check | „1 neue Datei in Negative/_Fehler – der Grund steht jeweils in der .txt-Datei daneben.“ (1 new file, the reason is in the .txt file next to it) |
| The background service matches the switch `service` | „Der Hintergrunddienst ist nicht eingerichtet, obwohl „service = true“ eingestellt ist.“ (service not set up although `service = true`; or the other way round) |

If everything is fine, nothing appears. Problems appear as additional lines in the result window of „Negative entwickeln“, on the console for `rffilmlab run`, for the service as one notification each (not repeated at every batch while nothing changes), and always in the log. Which files in `_Fehler/` have been reported, the program remembers once for all runs and the service together (file `selfcheck.json` in the app data folder): a file is reported only once – in the result of the run that put it there, or by the next self-check – and not again by the service or by „Negative entwickeln“. If `_Fehler/` cannot be read, this record stays unchanged.

### Notice of new versions

With `update_check = true` the program asks GitHub for the latest version at most once in 7 days (before a run or a batch of the service). Exactly one HTTPS request is sent, to `https://api.github.com/repos/jcmx9/real-fast-filmlab/releases/latest` (with the identifier `real-fast-filmlab/<version>`), nothing else – no file names, pictures or settings. As with any web page, GitHub sees the IP address. It waits at most 5 seconds; without internet or on an error nothing happens (the next attempt after 7 days). If the version on GitHub is newer than the installed one, it reports this once per new version:

- „Negative entwickeln“: a line in the result window and the button „Projektseite öffnen“ (open project page), which opens the section [Update](#update) in the browser,
- service: a notification „Neue Version X verfügbar – siehe Update-Abschnitt auf der Projektseite“,
- `rffilmlab run`: a line with the address.

The program never updates itself; the update is started with the command under [Update](#update). `update_check = false` switches the request off completely. A version counts as reported only once the notice was shown: a silent run (`-Q` without `--summary`) and a service with `notify = false` do not use it up. The time of the last request and the reported versions are in `update-check.json` in the app data folder.

## Configuration

### Location of the configuration file

| System | Path |
|--------|------|
| macOS | `~/Library/Application Support/real-fast-filmlab/config.toml` |
| Linux | `~/.config/real-fast-filmlab/config.toml` |
| Windows | `%LOCALAPPDATA%\real-fast-filmlab\config.toml` |

A different file can be given with `--config PATH`. If the file is missing or a folder is not set, the program says which key is missing and where it expects the file. Unknown keys are an error (protection against typos).

### Example

`rffilmlab config init` (and so the installer) writes every key with its value and a short comment (in German, for the end user), grouped as below; to change something, replace just a value, e.g. `true` with `false`. An excerpt:

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

A configuration that lacks keys is completed by `rffilmlab config init` (also on every run of the installer): these keys are added at the end of the file, each with the value that applied so far (default or derived from other keys, e.g. `holder_min` from `holder_delta`; a missing `service` with the current state of the service, so that an update never brings back a removed service); existing lines and values stay unchanged. A faulty configuration is not touched.

`~` stands for the home folder. The three folders must be different. A missing folder is created during processing only if the folder above it exists; otherwise (e.g. drive not connected) the program reports „Ordner nicht erreichbar“ (folder not reachable) instead of creating the folders on the system disk. `rffilmlab config init` creates the folders including missing parent folders.

### All keys

Every key is optional except the three folders (a missing one applies with its default). The switches `dng`, `tiff`, `contact_sheet`, `service` and `update_check` are all `true` in a new configuration. Types: `path` = text in quotes, `bool` = `true`/`false`, `int`/`float` = number.

#### Folders

| Key | Type | Default | Allowed | Effect |
|-----|------|---------|---------|--------|
| `negative_dir` | path | – (required) | existing folder or one whose parent folder exists | Inbox for RAW files; only files directly in it are processed |
| `photos_dir` | path | – (required) | different from the other two | Output folder for DNG, TIFF, JPEG |
| `archive_dir` | path | – (required) | different from the other two | Originals are moved here after success |

#### Outputs

| Key | Type | Default | Allowed | Effect |
|-----|------|---------|---------|--------|
| `dng` | bool | `true` | `true`, `false` | Write the DNG |
| `tiff` | bool | `true` | `true`, `false` | Write the TIFF (the JPEG is always written) |
| `contact_sheet` | bool | `true` | `true`, `false` | After a run with new pictures, write a [contact sheet](#contact-sheet) into `Fotos/` |
| `dng_finder_preview` | bool | `false` | `true`, `false` | `false`: float16 DNG with Deflate (smaller), not limited: keeps values above the white point and below the black point. `true`: uncompressed uint16 DNG that macOS Finder and Quick Look display (larger), limited to 0–1. Both contain the correction (section 5) |
| `jpeg_quality` | int | `95` | 1–100 | JPEG quality |
| `jpeg_sharpen` | bool | `false` | `true`, `false` | `true`: sharpen the JPEG slightly (step 4.14); TIFF and DNG stay unsharpened |

#### Look

| Key | Type | Default | Allowed | Effect |
|-----|------|---------|---------|--------|
| `contrast` | float | `0.30` | 0–0.8 | Base contrast of every picture (section 5): mid-tone slope 1 + value; `0` = no base contrast |
| `saturation` | float | `1.15` | 1–1.6 | Base saturation of every colour picture (section 5); `1` = unchanged |
| `flatfield` | path | empty | RAW file | Empty: off. Set: a RAW of the empty holder on the same light, taken with the same lens, aperture and distance; the light fall-off of lamp and lens is then taken out of every scan (step 2.1) |

#### Orientation

| Key | Type | Default | Allowed | Effect |
|-----|------|---------|---------|--------|
| `rotate` | int | `0` | `0`, `90`, `180`, `270` | Rotate clockwise (per scanning setup, applies to all files). The starting point is the picture as the sensor recorded it; the camera's orientation flag is not used (step 2.1) |
| `mirror` | bool | `false` | `true`, `false` | Mirror horizontally, before rotating (film shot from the emulsion side) |

#### Correction

All three outputs contain the same correction (section 5); within 0–1 the DNG gives the same values as the TIFF (BW exactly, colour except for pixels with a camera channel outside 0–1). The float16 DNG additionally keeps the values outside 0–1, not limited (step 4.12). The DNG carries a profile with a linear tone curve and without automatic black subtraction, so that Lightroom and Camera Raw show it like the TIFF instead of with their own default curve.

#### Service and operation

| Key | Type | Default | Allowed | Effect |
|-----|------|---------|---------|--------|
| `service` | bool | `true` | `true`, `false` | Background service: `true` = set up, `false` = not set up; every run and the installer reconcile it |
| `update_check` | bool | `true` | `true`, `false` | Look for a new version at most once in 7 days ([Notice of new versions](#notice-of-new-versions)) |
| `notify` | bool | `true` | `true`, `false` | Desktop notification with the result of each run (not for „Negative entwickeln“, which shows its own window); for the service also self-check problems and a new version |
| `parallel_jobs` | int | `0` | ≥ 0 | Files processed at the same time; `0` = automatic: min(CPU cores, ⌊half the RAM / 4 GiB⌋, number of files), at least 1. The comment in the file names the automatic value of the computer on which `config init` wrote it |
| `settle_seconds` | float | `5.0` | > 0 | Files must be unchanged this long before a batch starts (a single run waits only while files are still being copied); in watch mode also the retry wait (limited to 5–60 s) |
| `exiftool_path` | path | empty | path to the program | Set: only this program (if the file does not exist, without exiftool). Empty: `exiftool` on the `PATH`, otherwise the installer's copy in the app data folder |

The amount of output is chosen only on the command line (`-Q`, `-v`, `-vv`); a key `verbosity` in the file is ignored.

#### Expert thresholds

Only needed if detection fails on unusual material. Names as in the code (`AnalyzerSettings`, `RollSettings`); the steps are explained in [Processing step by step](#processing-step-by-step).

An update keeps changed values. `rffilmlab config init --negative … --photos … --archive … --expert-reset` sets every expert threshold back to its default; all other keys stay unchanged.

| Key | Type | Default | Allowed | Effect |
|-----|------|---------|---------|--------|
| `measure_inset` | float | `0.10` | 0–0.25 | Inner measurement window: share of the crop's height/width left out on each side (0.10 = inner 80 %) |
| `holder_delta` | float | `1.8` | > 0 | Film mask: density above the clearest base up to which a pixel counts as film |
| `holder_min` | float | `1.0` | ≥ 0.3 | Translucent holder: minimum density above the clearest base from which a border strip can count as holder (step 4). Effective is max(0.3, min(`holder_min`, `holder_delta`)): lowering `holder_delta` needs no change of `holder_min` |
| `gap_delta` | float | `0.10` | > 0 | Strict base pixel (gap between frames): density limit above the base |
| `gap_std` | float | `0.03` | > 0 | Strict base pixel: limit of the local standard deviation |
| `loose_delta` | float | `0.15` | > 0 | Loose base pixel (edge trimming): density limit above the base |
| `loose_std` | float | `0.08` | > 0 | Loose base pixel: limit of the local standard deviation |
| `aspect_tol` | float | `0.08` | > 0 and < 1 | Snap to a film format if the aspect ratio deviates by less than this (relative) |
| `min_skew_deg` | float | `0.2` | 0–45 | Smallest skew angle that is corrected (degrees) |
| `max_skew_deg` | float | `5.0` | 0–45 | Largest skew angle that is corrected (degrees) |
| `dmin_percentile` | float | `0.2` | 0–100 | Percentile (in %) of the density over the film mask that counts as film base |
| `white_percentile` | float | `99.5` | > 0 and ≤ 100 | Percentile (in %) of the density in the inner window that counts as white point |
| `edge_white` | float | `0.10` | 0–0.5 | White point: bright picture parts near the border may raise it by at most this much density (step 2.15); `0` = only the inner window counts |
| `bw_threshold` | float | `0.03` | > 0 | Colour/BW decision: limit for the channel deviation (99.9th percentile) |
| `gamma_color` | float | `0.6` | > 0 | Gradation of colour film in the conversion to linear light |
| `gamma_bw` | float | `0.65` | > 0 | Gradation of black-and-white film |
| `hue_tol` | float | `0.06` | > 0 | Roll grouping: largest distance of the film-base hue |
| `highkey_delta` | float | `0.10` | ≥ 0 | High-key fallback: minimum lift of the film base in every channel |
| `uniform_ratio` | float | `2.0` | ≥ 1 | High-key fallback: largest lift at most this times the smallest |
| `crossover_limit` | float | `0.10` | 0–0.5 | Colour crossover correction: a frame may deviate from the value of its roll by at most this much; `0` switches the correction off (step 3.5) |
| `crossover_roll_limit` | float | `0.30` | 0–0.5 | Colour crossover correction: the value of the roll is at most this far from 1 (step 3.5) |
| `white_limit` | float | `0.10` | 0–0.5 | Colour of the white point: a frame may deviate from the roll by at most this much (step 3.6); `0` = every frame keeps its own white point |

### Fixed values (not configurable)

| Constant | Value | Module | Meaning |
|----------|-------|--------|---------|
| `PREVIEW_EDGE` | 1000 | `core/analyzer.py` | Analysis preview: step n = max(1, ⌊long edge / 1000⌋) |
| `EDGE_BAND_FRACTION` | 0.6 | `core/analyzer.py` | Trimming: remove column/row while > 60 % loose base pixels |
| `GAP_FRACTION` | 0.9 | `core/analyzer.py` | Gap: column/row with > 90 % strict base pixels |
| `EDGE_FACTOR` | 2.5 | `core/analyzer.py` | Anchored edge: edge score ≥ 2.5 × typical score |
| `EDGE_WINDOW` | 0.06 | `core/analyzer.py` | Search window around an end: ±6 % of the axis length |
| `EDGE_BAND` | 0.04 | `core/analyzer.py` | Skew: band per edge, 4 % of the longer side of the rough rectangle inwards and outwards |
| `COARSE_STEP`, `FINE_STEP` | 0.25°, 0.02° | `core/analyzer.py` | Skew: step of the coarse and of the fine search |
| `MIN_GAIN` | 0.01 | `core/analyzer.py` | Skew: less than 1 % gain over 0° = no edge, the film mask outline applies |
| `HOLDER_P10` | 0.8 | `core/analyzer.py` | Translucent holder: 10th percentile ≥ 0.8 × `holder_min` |
| `HOLDER_STEP` | 0.005 | `core/analyzer.py` | Translucent holder: base-like line within max(2, 0.5 % of the long edge) |
| `STRIP_FRAME_SHARE`, `STRIP_AREA_SLACK` | 0.005, 0.03 | `core/analyzer.py` | Translucent holder: a confident frame is detected again if more than 0.5 % of its area are holder strips; beyond that the new one may be at most 3 % smaller |
| `BORDER_MARGIN` | 0.02 | `core/analyzer.py` | Bare light: border of 2 % of the long edge per side left out for the first base estimate |
| `BARE_GAP` | 0.2 | `core/analyzer.py` | Bare light: more than 0.2 below the first base estimate |
| `PATCH_DECILE`, `PATCH_BIN`, `PATCH_VALLEY` | 10 %, 0.02, 0.1 | `core/analyzer.py` | Bare light in patches: clearest 10 % of the pixels, density grid 0.02, valley = cells with at most 10 % of the highest cell below |
| `PATCH_MIN_COUNT`, `PATCH_AREA_RATIO`, `PATCH_SPAN`, `PATCH_MIN_PIXELS` | 4, 4, 0.25, 9 | `core/analyzer.py` | Bare light in patches: at least 4 patches, the largest at most 4 × the smallest, none longer than 25 % of the long edge, ones smaller than 9 pixels do not count |
| `BW_PERCENTILE` | 99.9 | `core/analyzer.py` | Colour/BW: percentile of the block deviation |
| `HOLDER_MIN_FLOOR` | 0.3 | `config.py` | Lower bound of `holder_min` |
| `ASPECTS` | 1:1 = 1.00, 6x7 = 1.24, 6x4.5 = 1.35, 3:2 = 1.50 | `core/analyzer.py` | Film formats for snapping |
| `crop_rect(inset)` | 0.01 | `core/geometry.py` | Crop pulled in by 1 % of its longer side on every side |
| `MEASURE_INSET` | 0.10 | `core/geometry.py` | Default of `measure_inset` |
| `EDGE_INSET` | 0.03 | `core/geometry.py` | White point: window for bright picture parts at the border, 3 % smaller than the crop on every side |
| `PICTURE_INTERPOLATION` | Lanczos (8 × 8) | `core/geometry.py` | Deskew of the picture at full resolution |
| `MAX_BALANCE_GAIN` | 16 | `fileio/raw_loader.py` | largest lift of a channel for the demosaicing |
| `EDGE_TOLERANCE`, `FIT_EDGE_FACTOR` | 2 px, 2.5 | `core/geometry.py` | Frame size of the roll: an edge may lie 2 preview pixels beside the expected place; clear edge = 2.5 × typical edge value |
| `MIN_SPREAD` | 0.05 | `core/converter.py` | Smallest density range per channel |
| `black_point(percentile)` | 0.5 | `core/converter.py` | Black point: 0.5th percentile of the luminance |
| `EPS` | 1/65535 | `core/converter.py` | Smallest value before the logarithm |
| `BASE_CONTRAST`, `BASE_SATURATION` | 0.30, 1.15 | `core/look.py` | Defaults of `contrast` and `saturation` |
| `MAX_TOTAL_CONTRAST`, `MAX_TOTAL_SATURATION` | 0.8, 1.6 | `core/look.py` | Upper limits for base value plus top-up |
| `COLOR_STRENGTH`, `BW_STRENGTH` | 1.0, 0.5 | `core/look.py` | Strength of the top-up for colour and BW |
| `SPREAD_TARGET`, `MAX_CONTRAST` | 0.70, 0.35 | `core/look.py` | Contrast top-up (group) |
| `CHROMA_TARGET`, `SAT_GAIN`, `MAX_SATURATION`, `CHROMA_FULL` | 0.10, 1.5, 1.15, 0.5 | `core/look.py` | Saturation top-up and chroma weighting |
| `SAMPLE_STEP` | 4 | `core/look.py` | Look statistics on every 4th pixel |
| `MID_BAND`, `MIN_MID_PIXELS` | 0.05, 200 | `core/crossover.py` | Crossover: mid-grey pixels with \|x_G − 0.5\| < 0.05; fewer than 200 in the inner window: no measurement |
| `MID_CLIP` | 0.05–0.95 | `core/crossover.py` | Crossover: mids are clipped to this range before the logarithm |
| `ROLL_MIN_FRAMES`, `ROLL_AGREEMENT` | 3, 0.8 | `core/crossover.py` | Crossover per roll: at least 3 measured colour frames, ≥ 80 % of them on the same side for R and for B |
| `ROLL_LIMIT` | 0.30 | `core/crossover.py` | Default of `crossover_roll_limit` |
| `ROLL_MIN_FRAMES`, `SIZE_TOLERANCE` | 3, 0.03 | `core/rolls.py` | Roll values for white colour and frame size: at least 3 frames; frame sizes within 3 % count as equal |
| `BASE_TOO_DARK`, `BASE_CLIPPED` | 0.125, 0.98 | `core/rolls.py` | Hint about the scan exposure: film base below one eighth of, or at the limit of, the sensor range |
| `KEYSTONE_TOLERANCE` | 0.4° | `core/rolls.py` | Hint when opposite frame edges differ by more in the median of the run |
| `MAP_EDGE`, `BLUR_FRACTION`, `CENTRE_FRACTION` | 256 px, 0.05, 0.1 | `fileio/flatfield.py` | Flat field: size of the fall-off map, blur (5 % of its long edge), central region taken as "full light" |
| `MIN_GAIN`, `MAX_GAIN`, `ASPECT_TOLERANCE` | 0.2, 1.5, 0.02 | `fileio/flatfield.py` | Flat field: limits of the fall-off; reference and scan must have the same proportions (± 2 %) |
| `SHARPEN_SIGMA`, `SHARPEN_AMOUNT` | 1.0 px, 0.5 | `service/render.py` | JPEG sharpening (`jpeg_sharpen`) |
| `SAMPLE_MAX_PIXELS` | 87,381 | `core/crossover.py` | Density sample of the inner window per frame (at most 1 MiB) |
| `PREVIEW_LONG_EDGE` | 1024 | `service/render.py` | Long edge of the preview embedded in the DNG |
| `MEMORY_PER_WORKER` | 4 GiB | `system.py` | RAM budget per parallel job |
| `STALE_TEMP_SECONDS` | 3600 | `service/batch.py` | Leftover temporary files older than 1 h are deleted |
| `STALE_TEMP_PATTERNS` | `.*.tmp.*`, `*_exiftool_tmp` | `service/batch.py` | Name patterns of these temporary files |
| `TIMEOUT_SECONDS` | 300 | `fileio/exiftool.py` | Longest run time of one exiftool call |
| `RESCAN_SECONDS` | 60 | `service/watcher.py` | Watch mode: rescan the folder at least once a minute |
| `MIN_BACKOFF`, `MAX_BACKOFF` | 5 s, 60 s | `service/watcher.py` | Watch mode: limits of the wait before a retry |
| `DISK_FULL_PAUSE` | 600 s | `service/watcher.py` | Watch mode: longest pause after a full disk while not enough space becomes free |
| `DISK_FULL_RESUME_BYTES` | 1 GiB | `service/watcher.py` | Watch mode: this much more free space than at the stop ends the pause early |
| `FINDER_BUSY_DAY` | 1984-01-24 (±12 h) | `service/settle.py` | macOS: creation date the Finder gives a file while copying it |
| `LOW_SPACE_BYTES` | 2 GiB | `service/selfcheck.py` | Self-check: below this, warning „Wenig Speicherplatz frei“ (little free space) |
| `CHECK_INTERVAL_SECONDS` | 7 days | `service/update.py` | At most one request for a new version in this interval |
| `TIMEOUT_SECONDS` | 5 s | `service/update.py` | Longest wait for GitHub's answer |
| `COLUMNS`, `THUMB_SIZE`, `LABEL_HEIGHT` | 6, 320 × 240 px, 28 px | `service/contact_sheet.py` | Contact sheet: columns, box per thumbnail, room for the file name |
| `NOTE_HEIGHT`, `NOTE_FRAME` | 20 px, 3 px | `service/contact_sheet.py` | Contact sheet: line for the review note, width of the frame around a marked picture |
| `SHEET_MAX_PICTURES` | 300 | `service/contact_sheet.py` | Contact sheet: at most this many pictures per file, beyond that „Teil 1“, „Teil 2“ … (part 1, part 2) |
| `GAP`, `MARGIN`, `FONT_SIZE`, `QUALITY` | 16 px, 24 px, 14 px, 85 | `service/contact_sheet.py` | Contact sheet: gap, margin, font size (Pillow's default font), JPEG quality |

## Processing step by step

### Overview

Each run processes all files of a batch in two passes: **pass 1** analyses every file on a small preview, then the **roll context** compares the files with each other, and **pass 2** develops every file at full resolution and writes the outputs. Three regions of the scan are distinguished, and they are determined in this order:

1. **Film mask** – the whole film strip in the picture (frames, gaps between frames, rebate), without the holder. The film base `d_min` is measured here.
2. **Crop** – the detected frame, determined first and completely (deskew, edges, gaps, format snapping, 1 % pull-in). TIFF and JPEG are cut to it; the DNG carries it as a resettable crop setting. Colour/BW is measured here.
3. **Inner window** – the crop without `measure_inset` (10 %) of its height/width on every side (inner 80 % × 80 %), always placed relative to the *final* crop. White point, black point, crossover and all look statistics are measured here, so that a sliver of rebate or holder at the edge cannot shift them. White and black point apply to this one frame only (normalisation per frame, see Principles).

### 1. Trigger and batch start

1. **Trigger.** `rffilmlab run` (or `rffilmlab` without a command, the program „Negative entwickeln“ or a double-click starter) processes the folder once. In watch mode (`rffilmlab watch`, background service) a file system event or, at the latest, a rescan every 60 s wakes the program; files already waiting are processed at start.
2. **Settle gate.** In watch mode: every 0.5 s the size and modification time (`mtime_ns`) of all candidate files are read; a file that cannot be opened for reading yet (Windows while copying) or that the macOS Finder is still copying (creation date 1984-01-24, `FINDER_BUSY_DAY`) counts as unstable. The batch starts once this state has not changed for `settle_seconds` (5 s). Failed files that stayed in `Negative/` are skipped until their size or time changes (a run via „Negative entwickeln“ or `rffilmlab run` tries them again). A single run takes files that have been unchanged for `settle_seconds` and are not recognisably being copied at once; if a file was changed more recently or is still being copied, it waits for the same settle gate and leaves out files that are still being copied after that.
3. **Folders.** All three folders must be set and different. A missing folder is created only if the folder above it exists. If a folder is unreachable or not writable (also when creating the lock file or reading `Negative/`), the run ends with a clear message, e.g. `Error: Ordner nicht erreichbar: <path> – ist das Laufwerk angeschlossen? (folder not reachable: …)`, `Keine Berechtigung für den Ordner: …` (permission denied), `Der Ordner ist schreibgeschützt: …` (read-only) or `Kein Speicherplatz mehr frei: …` (disk full) (exit code 1). Watch mode reports this once in the log and as a notification, retries quietly every min(60, max(5, `settle_seconds`)) s (if `Negative/` itself is unreadable, at the latest at the rescan every 60 s) and reports again only on a change.
4. **Lock.** Exclusive, non-blocking lock on `Negative/.rffilmlab.lock`. If another run holds it, this run ends immediately without touching anything („Der Dienst verarbeitet gerade – bitte später erneut versuchen.“, exit code 0); watch mode retries after min(60, max(5, `settle_seconds`)) s. File systems without lock support: warning, run without lock.
5. **Cleanup.** Temporary files of interrupted runs in `Fotos/` and `Archiv/` (`.<name>.tmp.*` and `<name>_exiftool_tmp` of an interrupted exiftool) that are older than 1 h are deleted.
6. **Input list.** Files directly in `Negative/` (no subfolders, so `_Fehler/` is ignored) whose extension is a known RAW format (case does not matter), excluding names starting with `.` (hidden files, macOS `._` AppleDouble files). Sorted by name.
7. **exiftool and parallelism.** exiftool is looked up: if `exiftool_path` is set, only there; otherwise on the `PATH`, then the installer's copy in the app data folder (if missing: one warning). Number of parallel jobs: see `parallel_jobs`. Parallel jobs are threads; they do not change the result.

### 2. Pass 1: analysis of every file

On a preview of the half-resolution RAW. A file that fails here goes to `_Fehler/` immediately; only with too little memory or a file system error does it stay in `Negative/` (step 4.18).

1. **Loading.** LibRaw (via rawpy) decodes the RAW at half resolution with 16 bit, linear (gamma 1), without white balance (all multipliers 1), without auto brightness, in the camera's own RGB colour space; demosaicing is LibRaw's default. The picture is decoded as the sensor recorded it (`user_flip = 0`): the camera's orientation flag is arbitrary when the camera points straight down at the film, so `rotate` and `mirror` alone set the orientation; all outputs carry `Orientation = 1`. The values keep the sensor's scale (`adjust_maximum_thr = 0`; LibRaw would otherwise rescale a file to its own brightest pixel, which shifts the densities from frame to frame) and are divided by 65535 (0–1). The camera colour matrix (XYZ → camera) is read along; if it is missing, the identity matrix is used. The *scan exposure* is read from the shooting data: log10(shutter time · ISO / aperture²); without a time or ISO value it counts as unknown, a missing aperture (manual lens) counts as 1. *Flat field:* if `flatfield` is set, the reference is decoded once at half resolution, reduced to a map with a long edge of 256 pixels, blurred (sigma 5 % of the long edge; dust on the reference therefore leaves no marks) and normalised per channel to the mean of its central tenth (fall-off, limited to 0.2–1.5). Every scan is divided per channel by the map brought to its size. If the reference has other proportions (± 2 %) or cannot be read, this is logged once and the scans are developed without it.
2. **Preview.** Every n-th pixel in both directions, n = max(1, ⌊long edge / 1000⌋), so the long edge of the preview is 1000–1999 pixels.
3. **Density.** Per channel D = −log10(max(T, 1/65535)), T = linear value. On a negative the film base has the lowest density, the brightest parts of the scene the highest. For detection the channel mean `lum` is used.
4. **Film mask** (region 1). Reference `d_ref` = 0.5th percentile of `lum` (the clearest film base), measured without *bare light*: pixels more than 0.2 below the 0.5th percentile of the image interior (without a 2 % of the long edge border on each side) are a strip of light at the image border (no film) and count neither for `d_ref`, nor for the film mask, nor for `d_min`. This works only while the part of the strip inside the interior is below 0.5 % of the interior pixels; above that the strip itself sets the percentile and the result equals the behaviour without bare-light handling. Pixels with `lum < d_ref + holder_delta` (1.8) are film, denser pixels are holder. Then morphological opening and closing with a square kernel of max(3, long edge / 100) pixels (odd), and only the largest connected region is kept. If there is none, the whole picture counts as film. *Translucent holder:* border strips are searched that are less dense than `holder_delta` but clearly denser than the base. Per image side, the columns (left/right) or rows (top/bottom) from the image border inwards count whose density above `d_ref` has, over the whole side length, a median ≥ `holder_min` (1.0) and a 10th percentile ≥ 0.8 × `holder_min` (uniformly dense along ≥ 90 % of the side). Such a strip only counts as holder if a base-like line (median ≤ `d_ref` + `loose_delta`, the rebate) follows within max(2, 0.5 % of the long edge) lines; the strip then reaches up to that line. A bright motif area at the border (sky) has no such line after it and stays film. The strips are taken out of the film mask, steps 6–11 run again, and the result is used only if it is confident; otherwise everything stays as with the fixed threshold. This happens when the detection with the fixed threshold is not confident (step 11) or when its frame reaches into such a strip (more than 0.5 % of its area); whether the first run happened to be confident therefore does not decide whether a translucent holder stays in the crop. A frame that was confident may only lose what the strips took from it (area ≥ (1 − strip share)² × 0.97 of the previous one); if a wide "strip" cuts deeper into it, it is picture and not holder, and the first result stays. With dense film holders the strips lie outside the film mask and thus outside any frame; a confident detection then stays unchanged. *Bare light in patches* (e.g. visible perforation) is recognised but not corrected: among the clearest 10 % of the pixels of the image interior there is a second cluster, at least 0.2 clearer than the rest (with a valley of density cells of 0.02 holding at most 10 % of the highest cell below in between), spread over at least 4 patches of similar size (the largest at most 4 × the smallest, from 9 pixels on), none of which is longer than 25 % of the long edge. The reason of the crop then says `patches of bare light inside the film (perforation?): the film base may be measured on them`: the film base may have been measured on these patches, and the picture then keeps the colour of the film mask.
5. **Skew** (from the outer edges of the frame). Steps 6–11 first run without rotation and give a rough frame rectangle: the edges of the segment found *before* format snapping and shortening (steps 9–10), or the bounding box of the film mask if the detection is not confident. So the angle does not depend on which end is shortened. Edge map = magnitude of the gradient of `lum`, only on film pixels (film mask shrunk by max(3, long edge / 100) pixels, odd; the film/holder edge does not count) and only in four bands around the outer edges of this rectangle: per edge 4 % of its longer side inwards and outwards. The interior of the frame does not count, so lines in the motif do not influence the angle. The band pixels are rotated by a trial angle θ (counter-clockwise, around the image centre, as in deskewing); score = sum of the squared row profiles of the top and bottom bands plus sum of the squared column profiles of the left and right bands (profile step 1 pixel, linear split onto the two neighbouring cells after a fixed random offset of ±0.5 pixel per pixel, so that the pixel grid does not favour 0°). θ runs from −`max_skew_deg` to +`max_skew_deg` (5°) in steps of 0.25°, then in steps of 0.02° within ±0.25° around the best coarse result (13 steps per side); on a tie the smaller |θ| wins, for ±θ the negative one. If the best score is less than 1 % above the one at θ = 0 (no noticeable edge), `cv2.minAreaRect` around the outline of the film mask gives the angle instead, normalised to −45° to +45°. Only if `min_skew_deg` (0.2°) ≤ abs angle ≤ `max_skew_deg` (5°) are preview and mask rotated around the centre by this angle and steps 6–11 run again on the rotated image; otherwise the angle is 0 and the result of the first run applies. If the first run was confident but the second (rotated) one is not, the unrotated result of the first run applies as well (angle 0). *Parallel edges:* if the edges give an angle, each of the four bands is also scored on its own over the coarse angles (peak refined by a parabola; a band without a clear edge does not count), and the difference top − bottom and left − right is kept. A single frame is unreliable here; only the median over the whole run is used (step 3.8).
6. **Base pixels.** Local standard deviation of `lum` in a window of max(3, long edge / 100) pixels (odd: `max(3, edge // 100) | 1`), over film pixels only (the holder cannot raise it at the film edge). *Strict* base pixel: `lum < d_ref + gap_delta` (0.10) and standard deviation < `gap_std` (0.03). *Loose* base pixel: `lum < d_ref + loose_delta` (0.15) and standard deviation < `loose_std` (0.08), or outside the film mask. The following steps work inside the bounding box of the film mask; its longer side is the long axis of the strip.
7. **Trimming the edges.** For every column (and row) the share of loose base pixels is computed; from both ends, columns/rows are removed while the share is > 60 % (rebate, gap fringe, holder edge). If less than 10 % of the axis would remain, nothing is trimmed.
8. **Splitting at gaps** (long axis only). Within the trimmed range, runs of columns with > 90 % strict base pixels that are at least max(2, long side of the box / 100) wide are gaps between frames. The widest segment between them is the frame. Deep shadows in the scene practically never meet the strict criteria.
9. **Format snapping.** The ratio long/short side is compared with 1:1 (1.00), 6×7 (1.24), 6×4.5 (1.35) and 3:2 (1.50); the format with the smallest relative deviation wins if that deviation is < `aspect_tol` (8 %). The side that is too long is shortened to the exact ratio. Otherwise the format stays "free".
10. **Which end is shortened** (only after snapping; first along the columns, then along the rows). Edge score of a column = median over the frame's rows of the absolute density difference to the next column. An end is *anchored* (a sharp frame border) if the highest edge score within ±6 % of the axis length around it reaches 2.5 × (`EDGE_FACTOR`) the median edge score inside the segment. Both ends anchored: the edge is the position of the highest edge score in the window; whatever lies between the segment end and the edge is an outer band (fog, rebate). The excess is removed half from each end, unless an outer band would remain: then the split is shifted just far enough to remove it. If both outer bands together are wider than the excess, the crop is centred between the two edges (at most the whole excess at one end); if the frame is shorter than the format, the crop may then extend a few rows past one edge. Known failure mode: the steepest step within the ±6 % window may be a straight motif edge instead of the frame border; the damage is bounded by the excess. One end anchored: the whole excess is removed at the other end. No end anchored: of all possible splits, the one is taken whose removed bands have the lowest summed median density (close to film base: fog, rebate, gap fringe); ties go to the symmetric split.
11. **Confidence and fallback.** The detection is *confident* if the format snapped, at least one edge was trimmed or one gap was found, and the frame covers 25–98 % of the film mask. Otherwise the bounding box of the film mask is used as the frame (`crop=uncertain` in the description).
11a. **Edge profiles.** For the frame found, two profiles are kept over the bounding rectangle of the film mask, per column and per row of the preview: the median of the density step to the next column or row (clearly different from 0 only where a straight edge runs across most of the film; positive where unexposed film turns into picture, i.e. at the beginning of a frame, negative at its end) and whether the column or row is unexposed film (along the film the gaps of step 8, across it the border rows of step 7). The roll context needs them to place a frame of known size (step 3.7).
12. **Crop** (region 2). The frame is scaled to the resolution in use and pulled in by 1 % of its longer side on every side.
13. **Inner window** (region 3). The crop from step 12 without `measure_inset` (10 %) of its height and width on each side.
14. **Film base `d_min`** (region 1). Per channel the `dmin_percentile` (0.2 %) percentile of the density over the whole deskewed film mask (frames, gaps, rebate; no holder). Signature = (d_min_R − d_min_G, d_min_B − d_min_G): the hue of the film base, used for roll grouping.
15. **White point `d_white`** (region 3). Per channel the `white_percentile` (99.5 %) percentile of the density in the inner window. *Bright picture borders:* skies and bright foregrounds often lie in the outer ring of a picture and, measured in the inner window only, would lie above the white point and clip. With a confident crop the same percentile is therefore also measured on nearly the whole crop (3 % left out on every side, pixels of the film mask only); it may raise the white point per channel by at most `edge_white` (0.10) and never lowers it. More than that is more likely a holder fringe or a dense rim than picture; such a rim then darkens the picture by no more than that amount. `edge_white = 0` switches this off.
16. **Colour or BW** (region 2). The density of the crop is normalised as in pass 2, step 3 (with this frame's own `d_min` and `d_white`), averaged over blocks of 4 × 4 pixels; per block the mean absolute deviation of the three channels from their mean. If the 99.9th percentile of these deviations is < `bw_threshold` (0.03), the frame is BW; so even a small share of clearly coloured details decides for colour.
17. **Look statistics** (region 3). The crop of the preview is developed exactly as in pass 2, steps 3, 4 and 7–10 (this frame's own `d_min`, `d_white`, gamma by its own colour/BW result, black point on the inner window, camera → sRGB or channel mean for BW, sRGB curve). Film base and colour/BW are always the frame's own values from pass 1, even if the roll context changes them later (high-key fallback, majority for colour/BW); the group median damps this difference. On the inner window, every 4th pixel in both directions: **spread** = 95th minus 5th percentile of the luminance (Rec. 709 weights 0.2126, 0.7152, 0.0722), **chroma** = mean of (largest − smallest channel) per pixel (0 for BW). All values are clipped to 0–1 beforehand.
18. **Samples for the crossover and the look** (region 3). The density of the inner window is thinned in raster order to every s-th pixel, s = ⌈pixel count / 87,381⌉ (at most 1 MiB per frame), together with the density of the look grid from step 17 (inner window, every 4th pixel). Both are kept until the roll context (steps 3.4 and 3.5) and dropped afterwards. Until then the run needs about 1.3–2.3 MiB extra per file in the folder (100 files ≈ 130–230 MiB).

### 3. Roll context

Applies to the files of one batch that passed pass 1, in name order.

1. **Grouping by film base.** Two frames are neighbours if their signatures (step 2.14) are closer than `hue_tol` (0.06, Euclidean distance). Groups are formed by chaining (single linkage): if A–B and B–C are neighbours, A, B and C form one group. Frames of the same film under the same light end up in one group.
2. **High-key fallback** (groups with ≥ 2 frames). The `d_min` values are compared on a common scale: a scan exposed longer measures every density lower by the logarithm of the factor; if the scan exposure (step 2.1) is known for all frames of the group, it is therefore added to `d_min` (and subtracted again when the baseline is taken over). If one frame lacks it, the measured values are compared. Baseline = 25 % quantile per channel of these values of the group. A frame uses the baseline instead of its own `d_min` only if all of these hold: in every channel its `d_min` lies more than `highkey_delta` (0.10) above the baseline; the lift is even (largest ≤ `uniform_ratio` (2.0) × smallest); its signature is closer than `hue_tol` to the median signature of the group. It is never corrected downwards. Reason: in a very bright frame (snow, sky) even the clearest pixels are not film base; the roll knows the real base. The description then says `fallback=yes`.
3. **Colour or BW per roll.** In a group with ≥ 2 frames the majority decides: more than half BW → all BW, otherwise all colour (a tie gives colour). A colourless subject on colour film thus stays colour. Single frames keep their own result. An overruled frame gets a log line.
4. **Look parameters.** They are based on the look statistics of the preview corrected for the crossover (step 3.5, determined first): with k ≠ 1 they are measured again with k on the look grid (step 2.18), otherwise those of step 2.17 apply. No exposure correction; every picture gets the base contrast `contrast` and the base saturation `saturation`, plus a top-up per group from the median spread and median chroma of its frames (frames with high-key fallback are left out as long as the group has others); single frames use their own values. Formulas: [Correction in detail](#5-correction-in-detail).
5. **Colour crossover (layer steepness).** The three dye layers of a colour negative have slightly different gradation curves: film base and white point are neutral after the channel normalisation, the mid-tones are not (typically: the whole image a little too warm). *Per colour frame:* on the sample (step 2.18), x_c = (D_c − d_min_used_c) / max(d_white_c − d_min_used_c, 0.05), i.e. measured with the film base actually used (also after the high-key fallback) and the white point actually used (step 3.6). Mid-grey are the pixels with |x_G − 0.5| < 0.05; if there are fewer than 200 (scaled to the whole inner window), nothing is measured (k_frame = 1). Otherwise mid_c is the median of x_c of these pixels and k_frame_c = ln 0.5 / ln(mid_c, clipped to 0.05–0.95) for R and B; G keeps 1. *Per roll group:* a roll value is valid only with ≥ 3 measured colour frames of which, for R and for B, ≥ 80 % lie on the same side of 0.5 as the group median; then k_roll from the group medians of the mids (same formula), else k_roll = 1. *Result:* k_c = clip(k_roll_c, 1 ± `crossover_roll_limit` (0.30)) · clip(sqrt(k_frame_c / k_roll_c), 1 ± `crossover_limit` (0.10)). Without the limits this is sqrt(k_frame_c · k_roll_c); the two parts are limited separately: the value of the roll widely (it rests on many frames), the deviation of the single frame narrowly (it may be motif colour: snow, warm evening light). A frame without a valid roll value (k_roll = 1) gets half the correction (in the logarithm), at most ± `crossover_limit`. BW frames: k = 1. `crossover_limit = 0` switches the correction off.

6. **Colour of the white point.** The white point of a frame is the density of its brightest part, per channel. Its level (mean of the three channels above the film base) belongs to the frame, but the ratio of the channels belongs to the film – unless the brightest part is coloured (blue sky, a lamp): then the frame's own ratio would turn exactly that colour into white. In a group with ≥ 3 colour frames, per frame: ratio r_c = d_hi_c / mean(d_hi) with d_hi = max(d_white − d_min_used, 0.05); roll value = median of r_c over the colour frames of the group (normalised to mean 1); used is roll value · clip(sqrt(r_frame / r_roll), 1 ± `white_limit` (0.10)), normalised to mean 1 again, times the frame's own level. BW frames, smaller groups and `white_limit = 0` keep the frame's own white point.
7. **Frame size of the roll.** All frames of a roll have the same size and format. A dark picture border (night sky, a black wall) looks like unexposed film, so a single frame is cut there, snaps to a smaller format or finds no frame at all. If a group has ≥ 3 confident frames of the same format and orientation (landscape/portrait) whose sizes lie within 3 % of their median, that median is the frame size of the roll. Two kinds of frames of the group get this size: (a) a confident frame that is smaller by more than 3 % in one direction and larger in none – it was cut; the roll's frame must contain the detected one completely; (b) an uncertain frame (whole film strip), if the roll's frame lies on a clear edge at both ends in both directions inside it (≥ 2.5 × typical edge value). It is placed per axis with the edge profiles (step 2.11a): where a rising edge at the beginning and a falling edge at the end are strongest (± 2 preview pixels), without unexposed lines in the middle (that would be the gap to the neighbouring frame). A confident frame that is larger in one direction is never changed (it may be another format); a frame that cannot be placed stays as it is. The reason of the crop then says `frame size of the roll (<format>) used instead of the frame's own (<format>)`.
8. **Hints about the whole run.** *Scan exposure:* the film base is the brightest part of a negative. If its brightest channel lies, in the median of a group, below one eighth of the sensor range (10^−min(d_min) < 0.125), the run reports „Die Scans sind dunkel belichtet (der Filmrand nutzt weniger als ein Achtel des Sensorbereichs): länger belichten verringert das Bildrauschen.“ (the scans are exposed dark: a longer exposure lowers the noise); if it reaches 0.98, „Die Scans sind zu hell belichtet (der Filmrand ist übersteuert): kürzer belichten, sonst stimmen die Farben nicht.“ (the scans are exposed too bright: expose shorter, otherwise the colours are wrong). *Camera not square:* if the median of the edge differences (step 2.5) over at least 3 frames of the run differs from 0 by more than 0.4°, „Gegenüberliegende Bildkanten sind nicht parallel (um etwa X°): Die Kamera steht nicht genau senkrecht über dem Film.“ (opposite frame edges are not parallel: the camera does not stand exactly square above the film). The hints appear in the log (WARNING), in the console and, for „Negative entwickeln“, as additional lines in the result window; they change nothing in the pictures.

### 4. Pass 2: development and output of every file

At full resolution, in parallel; the steps of one file run in this order.

1. **Loading.** As in pass 1, step 1 (flat field included), but at full resolution and with balanced channels: for the demosaicing every channel is raised to the level of the strongest one (factor = transmission of the film base `d_min_used` in the strongest channel divided by that in the channel, at most 16) and scaled back afterwards. The values stay the same; but next to strong channels the demosaicing reconstructs a weak one with errors as large as its signal, which show as single wrong pixels after the inversion. Values up to the film base are untouched; brighter ones (bare light beside the film) may be limited in the raised channels.
2. **Density and deskew.** D = −log10(max(T, 1/65535)) per channel. The density image is rotated by the angle from pass 1 around the centre (Lanczos over 8 × 8 pixels, edges continued): grain and fine detail stay as sharp as in frames that need no rotation. The densities are rotated and not the positive, because dust and the holder are only a few density units from the picture there, but thousands of times brighter in the unclipped positive; every result is also limited to the range of the 3 × 3 source pixels around its place, so the sharp filter puts no fringes or patterns around such spots.
3. **Neutralisation and channel normalisation.** `d_min_used` = film base from the roll context, `d_white` = white point from the roll context (step 3.6), else the one from pass 1. Per channel d_hi = max(d_white − d_min_used, 0.05), D_target = mean of the three d_hi, D_norm = max(D − d_min_used, 0) · D_target / d_hi. Subtracting the film base removes the orange mask; the scaling gives all three channels the same density range, so film base and white point become neutral.
4. **Crossover and linear light.** x = D_norm / D_target per channel, x' = x^k_c with k from step 3.5 (film base 0 and white point 1 stay fixed, only the mid-tones move), then Y = 10^((x' · D_target − D_target) / γ) with γ = `gamma_color` (0.6) or `gamma_bw` (0.65) according to the roll decision. The white point becomes 1.0, the film base the darkest value. The correction is part of the inversion, not of the look: DNG, TIFF and JPEG all contain it.
5. **Frame.** The frame is the one from the roll context (step 3.7), else the one from pass 1.
6. **Orientation.** First mirror horizontally (`mirror`), then rotate clockwise by `rotate`; the crop rectangle follows.
7. **Black point** (region 3). b = 0.5th percentile of the luminance (mean of the channels, every 4th pixel) in the inner window of the oriented crop. If 0 < b < 0.99: Y = (Y − b) / (1 − b), the same offset for all channels. The values are not limited here: what lies above the white point stays above 1, what lies below the black point below 0 (for the DNG).
8. **BW.** For BW frames the three channels are combined into one, weighted by the transmission of the film base per channel: weight_c = 10^−d_min_used_c, normalised to sum 1. The three channels of a silver image show the same picture, but a channel that gets less light through film base, lamp and sensor is noisier.
9. **Colour space** (crop only, for TIFF and JPEG). Colour: the values are limited to 0–1, then camera RGB → linear sRGB with the camera matrix (dcraw method: (XYZ → camera) · (sRGB → XYZ, D65), rows normalised so that neutral stays neutral, inverted; unusable matrix → identity matrix and a warning). Negative values become 0. BW: the grey value of step 8 (mean of the unlimited channels) goes on without matrix; it is limited only in step 10.
10. **sRGB curve** (crop only). Values limited to 0–1, then the standard sRGB transfer function (IEC 61966-2-1). The result is the sRGB picture before the correction.
11. **Description.** One line, e.g. `rffilmlab 26.11.1 | color | dmin=0.415,0.437,0.908 | fallback=no | crop=1:1 | crossover: R x1.102 B x0.874 (frame+roll) | crop: …` (colour/BW, film base used, roll fallback, snapped format or `uncertain`; crossover with k for R and B and its source `frame+roll`, `frame only`, `roll only` or `none` (no correction), left out with `crossover_limit = 0`; at the end `| crop: …` with the reason for the crop). The log line from `-v` reads `<file>: crop <W>×<H>, crossover R x… B x… (…) — <reason>`. It is written into all three files (`ImageDescription`) and into the log.
12. **DNG** (if `dng = true`). The *whole* deskewed and oriented picture after steps 3–8 (linear, camera RGB, black point 0, white point 1; BW as three identical channels) with the correction (section 5), not cut. **Correction in the DNG:** per pixel the value is converted to linear sRGB with the camera matrix of step 9 (BW: the grey value, without matrix), the part within 0–1 is encoded with the sRGB curve, corrected exactly like the TIFF and linearised again, the part outside 0–1 is added back unchanged (slope 1), and the result is brought back to camera RGB with the inverse matrix. Converted to sRGB with ColorMatrix1 and encoded, the DNG gives the TIFF's values within 0–1: exactly for BW (up to float16 rounding), likewise for colour, except for pixels in which a camera channel lies outside 0–1 – the TIFF limits the camera values before the colour matrix, the DNG keeps them. On real frames the mean difference within 0–1 is below 0.0001 on the 0–1 scale. Outside 0–1 the curve continues with slope 1, not limited: highlights above the white point and shadows below the black point stay unchanged and available for later editing. At the ends 0 and 1 the curve is continuous, its slope there is 1 − contrast. **Formats:** `dng_finder_preview = false` (default): float16, not limited, Deflate with floating-point predictor, tiles 256 × 256 (only NaN/infinity are replaced and values limited to the float16 range ±65504; editors may set values below 0 to 0 when opening). `true`: uint16 uncompressed, limited to 0–1 (0–65535, BlackLevel 0, WhiteLevel 65535), so that Finder and Quick Look display it. The first image of the file is an 8-bit sRGB preview of the corrected, cropped picture (the same picture as the TIFF, long edge ≤ 1024 px), the main image follows as a SubIFD. Tags: DNGVersion 1.4.0.0, UniqueCameraModel (make and model via exiftool, otherwise `real-fast-filmlab`), ColorMatrix1 = camera matrix, scaled row by row so that D65 white gives the camera values (1, 1, 1) (the developed data are neutral at equal camera values; a program following the DNG rules derives D65 as the white point from this and gets the colours of the TIFF), CalibrationIlluminant1 = D65, AsShotNeutral = (1, 1, 1), BaselineExposure = 0, Orientation = 1, plus an embedded profile for data that are already developed: ProfileName `rffilmlab linear`, ProfileToneCurve linear (0,0 – 1,1), DefaultBlackRender = none, BaselineExposureOffset = 0, ProfileEmbedPolicy without restrictions. The crop travels as embedded Camera Raw XMP (`crs:ProcessVersion 11.0`, `HasCrop`, `CropTop/Left/Bottom/Right` relative 0–1, `CropAngle 0`, `AlreadyApplied False`): in Lightroom or Camera Raw it can be reset or widened up to the full scan.
13. **TIFF.** The cropped sRGB picture with the correction (section 5). 16 bit, Deflate with predictor; colour as RGB with embedded sRGB profile, BW as one grey channel with an embedded grey profile (sRGB curve, D50): without a profile, colour-managed programs assume their own grey space and show BW pictures darker or lighter than the colour files.
14. **JPEG.** The same corrected picture as the TIFF, only compressed (no second computation). 8 bit, quality `jpeg_quality` (95); colour with sRGB profile and colour at full resolution (4:4:4; the usual halving of the colour channels smears colour grain and fine coloured detail), BW as greyscale with the grey profile. With `jpeg_sharpen = true` only the JPEG is sharpened slightly beforehand: y = x + 0.5 · (x − Gaussian blur(x, sigma 1 pixel)), limited to 0–1.
15. **EXIF.** If exiftool is available, all metadata of the RAW is copied into every output (`-TagsFromFile … -all:all`), except MakerNotes, Orientation, ImageDescription, Software, ImageWidth/ImageHeight, Camera Raw settings (`XMP-crs`) and the DNG-specific colour, rendering and raw-data tags (`DNG_TAGS` in `fileio/exiftool.py`), so that a DNG used as input never writes its camera matrix, profile, calibration, black/white levels or crop into our DNG: DNGVersion, DNGBackwardVersion, DNGPrivateData, DNGAdobeData, UniqueCameraModel, LocalizedCameraModel, ColorMatrix1, ColorMatrix2, ColorMatrix3, CameraCalibration1, CameraCalibration2, CameraCalibration3, CameraCalibrationSig, ReductionMatrix1, ReductionMatrix2, ReductionMatrix3, ForwardMatrix1, ForwardMatrix2, ForwardMatrix3, CalibrationIlluminant1, CalibrationIlluminant2, CalibrationIlluminant3, IlluminantData1, IlluminantData2, IlluminantData3, AnalogBalance, AsShotNeutral, AsShotWhiteXY, AsShotICCProfile, AsShotPreProfileMatrix, AsShotProfileName, BaselineExposure, BaselineExposureOffset, BaselineNoise, BaselineSharpness, LinearResponseLimit, DefaultBlackRender, NoiseProfile, ProfileName, ProfileCopyright, ProfileEmbedPolicy, ProfileCalibrationSig, ProfileDynamicRange, ProfileGroupName, ProfileType, ProfileGainTableMap, ProfileGainTableMap2, ProfileHueSatMapDims, ProfileHueSatMapData1, ProfileHueSatMapData2, ProfileHueSatMapData3, ProfileHueSatMapEncoding, ProfileLookTableDims, ProfileLookTableData, ProfileLookTableEncoding, ProfileToneCurve, RawToPreviewGain, MakerNoteSafety, OpcodeList1, OpcodeList2, OpcodeList3, ActiveArea, MaskedAreas, BlackLevel, BlackLevelRepeatDim, BlackLevelDeltaH, BlackLevelDeltaV, WhiteLevel, LinearizationTable, ShadowScale, BayerGreenSplit, AntiAliasStrength, ChromaBlurRadius, BestQualityScale, DefaultScale, DefaultCropOrigin, DefaultCropSize, DefaultUserCrop, ColumnInterleaveFactor, RowInterleaveFactor, RawImageDigest, NewRawImageDigest, OriginalRawFileData, OriginalRawFileDigest, RawImageSegmentation, ColorimetricReference, CacheVersion, EnhanceParams, DepthFormat, DepthNear, DepthFar, DepthUnits, DepthMeasureType, SemanticName, SemanticInstanceID, JXLDistance, JXLEffort, JXLDecodeSpeed; thumbnails and previews of the RAW are not copied, Orientation is set to 1. A failure here only gives a warning.
16. **Writing.** Every file is first written as `.<name>.tmp.<pid>.<random><extension>` next to the target and then renamed in one step; a half-written file never has the final name.
17. **Archive.** The original is moved to `Archiv/` (`<name>_2.<ext>` etc. if the name is taken). On the same drive this is a rename. To another drive the file is first copied as `.<name>.<ext>.tmp.<pid>.<random>` into `Archiv/`, flushed to the disk (fsync), then renamed and only then deleted at its old place; if deleting fails, the copy is removed again. So a half-copied file never has the final name. Only now does the file count as done (log line `OK <name> - <description>`).
18. **Errors.** If something in steps 1–17 fails, the outputs of this file already written are deleted again. If the file itself is at fault (unreadable or damaged RAW, a JPEG that cannot be encoded, any other error in analysis or development), the original moves to `Negative/_Fehler/` with a text file `<name>.txt`: „<name> konnte nicht verarbeitet werden.“, „Grund: …“ (plain German: unreadable or damaged RAW, otherwise „Unerwarteter Fehler.“), „Technisch: …“ (exception text) and „Zeitpunkt: …“. If the cause lies in the environment – a file system error (no space left, no permission, read-only, read/write error, folder or drive gone) or too little memory (also in LibRaw) –, the original stays unchanged in `Negative/`; this also applies when the RAW could not be read for one of these reasons. One faulty file never stops the batch; only a full disk or a folder or drive that disappears during the batch (e.g. a disconnected external drive; before each file the batch checks that all three folders are still there) ends the batch: the remaining files stay untouched in `Negative/`, finished files stay finished. The message is then „Kein Speicherplatz mehr frei. Verarbeitung angehalten: …“ (no space left, processing stopped) or „Ordner oder Laufwerk nicht mehr erreichbar – ist das Laufwerk angeschlossen? Verarbeitung angehalten: …“ (folder or drive no longer reachable – is the drive connected? processing stopped). A RAW deleted from `Negative/` during the batch is skipped quietly (only a log line `SKIPPED <name>`; no error, no notice). Any other error that occurs while one of the three folders is missing also counts as an error of the environment; `_Fehler/` is never re-created in a folder that has disappeared. If the program is ended in the middle of a file (update, logout, power loss), its RAW stays in `Negative/`; the next run deletes the outputs already written for this file and develops it again under the same name (one marker per file in work in the app data folder under `pending/`).

After the batch: log summary, console output `N converted, M failed` (exit code 1 if anything failed) and, for files that stayed in `Negative/` because of the environment, a line with the reason, e.g. „Kein Speicherplatz mehr frei. Verarbeitung angehalten: 3 Fotos fertig, die übrigen Negative bleiben im Ordner „Negative“.“ (no space left; processing stopped, 3 pictures done, the other negatives stay in the Negative folder) or „Keine Berechtigung zum Schreiben/Lesen. 1 Negativ bleibt unverändert im Ordner „Negative“; 11 Fotos fertig.“ (no permission; 1 negative stays unchanged, 11 pictures done). Notification „N Fotos fertig, M Fehler“ (with that reason, if any) if `notify = true` and something was processed; watch mode does not show the same reason again as long as no picture gets done.

### 5. Correction in detail

Contained in TIFF and JPEG, identically in both (a picture is corrected once and written twice), and in the DNG (step 4.12: the same correction on the linear data, values outside 0–1 are kept). In the code it is called "look" (`core/look.py`). It never changes the brightness: no brightening or darkening, no exposure correction. It has two parts:

- **Base value** for every picture: `contrast` (0.30) and `saturation` (1.15). The neutral picture is scene-linear and looks flat without a rendering curve; camera JPEGs and raw developers put a contrast curve on top for the same reason.
- **Top-up** for flat or pale rolls, from the measurements below.

**Inputs of the top-up.** Two measurements per picture, taken on the neutral sRGB preview of the crop (after crossover, black point, camera matrix and sRGB curve; step 2.17, or step 3.4 with a re-measured k) in the inner window (`measure_inset`), every 4th pixel (`SAMPLE_STEP`), values clipped to 0–1:

- **Spread** = 95 % minus 5 % percentile of the luminance (weights 0.2126, 0.7152, 0.0722).
- **Chroma** = mean of (largest − smallest channel) per pixel; 0 for BW.

**Roll group.** The spread and chroma the top-up is derived from are the median over all pictures of the group (pictures with a high-key fallback do not count as long as the group has others); a single picture uses its own values. All pictures of a group therefore get the same parameters, and a roll looks consistent.

**Formulas and constants** (all in `core/look.py`):

| Step | Formula | Constants |
|------|---------|-----------|
| Contrast | s = min(`MAX_TOTAL_CONTRAST`, `contrast` + strength · clip(`SPREAD_TARGET` − spread, 0, `MAX_CONTRAST`)) | `SPREAD_TARGET` = 0.70, `MAX_CONTRAST` = 0.35, `MAX_TOTAL_CONTRAST` = 0.8 |
| Strength of the top-up | colour 1.0, BW 0.5 | `COLOR_STRENGTH`, `BW_STRENGTH` |
| S-curve | y = (1 − s) · x + s · x² / (x² + (1 − x)²), per channel | – |
| Saturation (colour only) | sat = min(`MAX_TOTAL_SATURATION`, `saturation` · clip(1 + `SAT_GAIN` · (`CHROMA_TARGET` − chroma), 1, `MAX_SATURATION`)) | `CHROMA_TARGET` = 0.10, `SAT_GAIN` = 1.5, `MAX_SATURATION` = 1.15, `MAX_TOTAL_SATURATION` = 1.6 |
| Chroma weighting | c = largest − smallest channel; factor = 1 + (sat − 1) · (1 − clip(c / `CHROMA_FULL`, 0, 1)); y = L + (x − L) · factor | `CHROMA_FULL` = 0.5 |

Finally all values are clipped to 0–1. The S-curve leaves 0, 0.5 and 1 unchanged; its slope is 1 + s in the middle and 1 − s at both ends (never 0: shadows and highlights keep their detail). The saturation acts fully only on pale pixels (small c); vivid ones keep their colour.

**What it never does:** no exposure change, no brightening of dark or darkening of bright shots, no hue change and no dependency on the output format (TIFF, JPEG and DNG get the same correction). The normalisation to the white and black point per frame (steps 4.4 and 4.7) is not part of the correction but of the inversion; it applies to the DNG as well. `contrast = 0` and `saturation = 1` leave only the top-up.

**Effect on example pictures** with the default values (described only by their measurements; numbers from the formulas above):

| Example picture | Spread | Chroma | Contrast s | Saturation |
|-----------------|--------|--------|------------|------------|
| Normal colour negative with full tonal range | 0.75 | 0.15 | 0.30 (base value only) | 1.15 |
| Slightly flat colour negative | 0.60 | 0.08 | 0.40 | 1.18 |
| Flat, pale colour negative | 0.50 | 0.04 | 0.50 | 1.25 |
| Very flat, low-colour negative | 0.30 | 0.02 | 0.65 | 1.29 |
| Flat BW negative (half top-up) | 0.50 | – | 0.40 | – |

With s = 0.30 the grey value 0.25 becomes 0.205 and 0.75 becomes 0.795, 0.50 stays 0.50. With saturation 1.15 the distance of a pale pixel (c = 0.05) from its grey value L grows by a factor of 1.135; a vivid one (c ≥ 0.5) is unchanged.

### What the program does not do

- No AI, no trained models, no cloud. The only network access is the question for a new version (`update_check`, can be switched off).
- No automatic upright detection: `rotate`/`mirror` apply to all files alike (one value per scanning setup).
- No dust, scratch or noise removal. Without an infrared channel (as on flatbed scanners with ICE), dust cannot be told apart reliably from picture details such as light reflections or stars, and grain is part of the film. Image editors in which the result can be checked are suited for this. Tip: dust off the negatives before photographing them and expose the scan so that the film base does not get too dark (underexposed scans show noticeably more noise after inversion).
- No sharpening of TIFF and DNG; the JPEG only on request (`jpeg_sharpen`).
- No correction of a tilted camera (frame edges that are not parallel): it is only reported (step 3.8).
- No per-picture manual adjustments and no user interface; fine-tuning is done afterwards in the DNG with an editor of your choice.
- No slide film (positives) and no film-stock profiles.
- If one scan shows several frames, only the widest frame is output.
- Visible perforation (35 mm) and masks with a rounded opening are not cropped reliably; the DNG contains the full picture. Large areas of bare light inside the film (perforation) may also be measured as the film base; the reason of the crop says so (step 2.4).
- No subfolders: only files directly in `Negative/` are processed.
- No XMP sidecar files are written or read.

## Outputs

Per RAW `<name>.<ext>` three files appear in `Fotos/` (without DNG with `dng = false`, without TIFF with `tiff = false`; the JPEG always):

| File | Content | Crop | Colour | Correction | Size per megapixel |
|------|---------|------|--------|------------|--------------------|
| `<name>.dng` | linear, float16 Deflate not limited to 0–1 (or uint16 uncompressed, 0–1), embedded preview | full scan, crop as resettable setting | camera RGB with colour matrix and linear profile | like the TIFF; float16: values outside 0–1 kept, not limited | about 3.6 MB (uint16: about 6.1 MB) |
| `<name>.tif` | 16 bit, sRGB curve, Deflate | cut | sRGB (BW: grey with profile) | section 5 | about 3.3 MB |
| `<name>.jpg` | 8 bit, quality 95, colour 4:4:4 | cut | sRGB (BW: grey with profile) | same as the TIFF | about 0.3–0.5 MB |

Sizes grow with the pixel count and depend on the picture content (grain and noise enlarge TIFF and JPEG); the table gives rough values per megapixel. The three files of a RAW always share the same name. If `<name>.dng`, `.tif` or `.jpg` already exists in `Fotos/` (or two RAWs in a batch have the same name), `<name>_2`, `<name>_3` … is used for all three. Nothing is overwritten.

### Contact sheet

With `contact_sheet = true` every run that produced new pictures (also a batch of the service) writes an overview into `Fotos/`: `_Kontaktabzug JJJJ-MM-TT HH-MM.jpg` (YYYY-MM-DD HH-MM, local time at the end of the run; if the name exists, `_2`, `_3` …). It shows all JPEGs of this run as thumbnails with their file name below: fixed grid with 6 columns, sorted by file name, each picture fitted into a box of 320 × 240 pixels, the font is Pillow's built-in default font (the same on every system), long names are shortened with „…“. Pictures worth a look get an orange frame and, below the name, the reason: „Beschnitt unsicher“ (crop uncertain: no frame found, whole film strip), „Beschnitt aus der Rolle“ (crop from the roll, step 3.7), „Filmbasis aus der Rolle“ (film base from the roll: high-key fallback, step 3.2); a contact sheet without such pictures looks as it always did. The file is first written under a temporary name and renamed only when complete. If a run has more than 300 pictures, several contact sheets of at most 300 pictures each are written in name order: `_Kontaktabzug JJJJ-MM-TT HH-MM Teil 1.jpg` (part 1), `… Teil 2.jpg` and so on. A contact sheet appears in no later contact sheet. If it cannot be written, the log says so; the pictures of the run are not affected.

### Why this crop?

Every frame states the reason for its crop and rotation, in the log and in the files. With `-v` the console shows one line per file, the log file always has it (INFO):

```
scan_0001.ARW: crop 6178×6178 — rotated 0.54° (frame edges); snapped to 1:1; width: left edge + right edge anchored, excess 4.3 % of the width taken from the left
```

The size is the output size in pixels. The reason lists, in this order and only what applies: the rotation (`rotated 0.54° (frame edges)`, `rotated 0.21° (film outline)`, `not rotated (abs angle 0.12° < 0.2°)`, `rotated pass uncertain, kept unrotated`), `bare light (no film) ignored for the film base`, `translucent holder strips removed (left 4.2 %, right 7.3 % of the image side)`, `patches of bare light inside the film (perforation?): …`, the format (`snapped to 3:2` or `no format (crop uncertain, full film area kept)`) and per axis which frame borders were anchored and where the excess was taken (`height: bottom edge anchored, excess 3.2 % of the height taken from the top`). If the roll context replaced the frame, `frame size of the roll (3:2) used instead of the frame's own (6x7)` follows. Sizes in the reason are percent of the image side along that axis. The same text is written into the image description of the DNG, TIFF and JPEG after `crop: ` (e.g. in the exiftool `ImageDescription`; the degree sign appears as `deg` there).

## Commands and options

| Command / option | Description |
|------------------|-------------|
| `rffilmlab` | Without a command: process `Negative/` once (like `run`) |
| `rffilmlab run` | Process `Negative/` once |
| `rffilmlab watch` | Keep running and process new files (Ctrl+C ends) |
| `rffilmlab service install` | Install and start the background service |
| `rffilmlab service status` | Show whether the service is installed and running, both log files and which exiftool is used |
| `rffilmlab service uninstall` | Remove the background service |
| `rffilmlab config init --negative PATH --photos PATH --archive PATH [--off SWITCH]… [--expert-reset]` | Write the complete configuration with these folders; an existing one keeps its folders and values and only gets missing keys. `--off` (repeatable) sets `dng`, `tiff`, `contact_sheet`, `service` or `update_check` to `false`; `--expert-reset` sets every [expert threshold](#expert-thresholds) to its default. Creates the configured folders; prints `config=`, `status=created\|completed\|kept` (newly written, completed, unchanged), `negative=`, `photos=`, `archive=` and per switch `<switch>=true\|false` |
| `--config PATH` | Config file path |
| `-Q`, `--silent` | No console output (the log file is still written) |
| `-v`, `--verbose` | More output (per file the crop size and the reason for the crop) |
| `-vv`, `--debug` | Debug output (also in the log file) |
| `-V`, `--version` | Show version and exit |
| `--help` | Help (also after every command) |
| `run --negative PATH` | Input folder (overrides `negative_dir`) |
| `run --archive PATH` | Archive folder (overrides `archive_dir`) |
| `run --photos PATH` | Output folder (overrides `photos_dir`) |
| `run --dng` / `--no-dng` | Overrides `dng` |
| `run --dng-finder-preview` / `--no-dng-finder-preview` | Overrides `dng_finder_preview` |
| `run --summary` | For launchers: prints the line `processed=<n> failed=<m> busy=<0\|1>` (processed, failed, folder busy), before it only when needed one `check=<text>` per self-check problem and `update=<version>` for a new version; no desktop notification. If files stayed in `Negative/` because of the environment (e.g. storage full), `Error: <reason>` with exit code 1 instead of the line |

Every run (`run`, no command) first reconciles the background service with the switch `service`, checks itself quietly (problems as lines of their own, not with `-Q`; if a folder cannot be used, `Error: …` and no run) and prints a line `New version X available: https://github.com/jcmx9/real-fast-filmlab#update` for a new version. Global options (`--config`, `-Q`, `-v`, `-vv`) come before the command, e.g. `rffilmlab -v run --photos ~/Film/Fotos --no-dng`. Exit codes: 0 = everything done (also when the folder was busy), 1 = at least one file failed or a configuration or folder error. With `run --summary` the result is in the line; the exit code is then 1 only for an error before processing (e.g. configuration, folder not reachable) or for files that stayed in `Negative/` because of the environment. Operating system errors always appear as one line `Error: …`, never as a Python traceback.

## Supported cameras and formats

Everything LibRaw 0.22 reads, with the extensions `.arw .sr2 .raf .nef .nrw .cr2 .cr3 .orf .rw2 .pef .srw .dng`. The camera's sensor format does not matter: the frame on the film is detected.

## Troubleshooting

- **A file is in `Negative/_Fehler/`:** the `.txt` next to it gives the reason. After fixing the cause, move the RAW back into `Negative/`.
- **„Ordner nicht erreichbar“, „Ordner oder Laufwerk nicht mehr erreichbar“, „Kein Speicherplatz mehr frei“ or „Keine Berechtigung“** (folder not reachable, folder or drive no longer reachable, no space left, no permission): connect the drive, free space or check the permission (macOS: System Settings › Privacy & Security, e.g. „Full Disk Access“ or „Removable Volumes“ for the service). The RAW files are unchanged in `Negative/`; then start „Negative entwickeln“. After „Kein Speicherplatz mehr frei“ the service retries them automatically once at least 1 GB more is free (after 10 minutes at the latest), after „Ordner oder Laufwerk nicht mehr erreichbar“ at the next batch once the folders are reachable again; otherwise it picks them up again only when they change or it is restarted.
- **Nothing happens:** `rffilmlab service status` shows whether the service is running and where the log file is. Without the service: start `rffilmlab run` by hand.
- **Error message about the configuration:** it names the missing or wrong key and the path of the configuration file.
- **„Der Dienst verarbeitet gerade …“:** another run is working on the folder; try again later.
- **Pictures upside down, lying on their side or mirrored:** set `rotate` and/or `mirror` and process again. The camera's orientation flag is not used; one value per scanning setup is enough.
- **Pictures look too harsh or too flat, too colourful or too pale:** change `contrast` and `saturation` (section 5) and process again.
- **Picture corners brighter than the centre:** lamp or lens give less light at the border; enter a RAW of the empty holder as `flatfield`.
- **Hint „Die Scans sind dunkel belichtet“ or „… zu hell belichtet“:** adjust the exposure when photographing the negatives (step 3.8); the pictures of this run are developed all the same.
- **Crop wrong:** in the DNG the crop can be reset in Lightroom/Camera Raw. `crop=uncertain` in the description means: the detection was not sure and used the whole film strip.
- **No camera data in the files:** exiftool is not installed or not found (warning in the log; `rffilmlab service status` shows the exiftool found). If `exiftool_path` is set, only that path counts (if the file is missing there, the program runs without exiftool); otherwise the `PATH` is searched, then the installer's copy in the app data folder. Run the installer again, install exiftool or set `exiftool_path`.

Log files: `rffilmlab.log` (background service) and `rffilmlab-run.log` (single runs: „Negative entwickeln“, `rffilmlab run`), separate so that two processes running at the same time do not get in each other's way; 5 files of 5 MB each in rotation per log. On macOS also `service.out.log`/`service.err.log` of the service.

| System | Folder |
|--------|--------|
| macOS | `~/Library/Logs/real-fast-filmlab/` |
| Linux | `~/.local/state/real-fast-filmlab/log/` |
| Windows | `%LOCALAPPDATA%\real-fast-filmlab\Logs\` |

## Development

```bash
git clone git@github.com:jcmx9/real-fast-filmlab.git
```

```bash
cd real-fast-filmlab && uv sync
```

```bash
uv run ruff check --fix . && uv run ruff format . && uv run mypy src/
```

Development runs always use an isolated app folder so that a real installation stays untouched (configuration, logs, data, exiftool and service files then live below it; service commands such as `launchctl` are only printed, not run):

```bash
RFFILMLAB_HOME=.devhome uv run rffilmlab --help
```

The environment variable `RFFILMLAB_HOME` moves all program folders to `<RFFILMLAB_HOME>/config`, `log`, `data` and `service`. The folder `.devhome/` is excluded from Git. Never use `uv tool install` for development: it would overwrite a real installation.

The test suite is maintained separately and is not published; this repository contains only the source code.

## Versioning

This project uses [CalVer](https://calver.org/) in the format `YY.M.MICRO` (e.g. `26.11.1`); development versions carry `.devN`. Releases are made with [bump-my-version](https://github.com/callowayproject/bump-my-version) and `scripts/release.sh`.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). In short: branch from `dev`, commit with Conventional Commits, open a pull request against `dev`.

## Security

Please do **not** report security vulnerabilities via public issues. See [SECURITY.md](SECURITY.md).

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

## License

MIT, see [LICENSE](LICENSE).
