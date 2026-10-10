# Changelog

All notable changes are documented in this file.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [26.10.8] - 2026-10-10

### Added
- Switches `tiff`, `contact_sheet`, `service` and `update_check` (all `true` by default, like `dng`); the JPEG is always written
- `rfnegconv config init` writes the complete configuration (every key with its value and a short German comment); on an existing configuration it adds only missing keys, with the values that applied so far (a missing `service` with the current state of the service), and keeps every value; `--off SWITCH` sets a switch to `false`
- `rfnegconv config init --expert-reset` sets every expert threshold to its default; without it, changed values stay as they are
- Installer options `--ohne-dng`, `--ohne-tiff`, `--ohne-kontaktabzug`, `--ohne-dienst` (Windows: `-OhneDng`, `-OhneTiff`, `-OhneKontaktabzug`, `-OhneDienst`) set those switches to `false`; a run without an option leaves the switches as they are
- The background service follows the switch `service`: every run and every installer run sets it up or removes it accordingly
- Silent self-check before every run and service batch (folders reachable and writable, free space below 2 GiB, exiftool, new files in `Negative/_Fehler`, service matches the switch); only problems are shown (launcher dialog, console, one notification per problem for the service)
- Contact sheet `_Kontaktabzug JJJJ-MM-TT HH-MM.jpg` in the photos folder after each run with new pictures (more than 300 pictures: several parts)
- The background service re-reads the configuration before each batch (switches apply without a restart)
- Update notice: at most once a week one HTTPS request to the GitHub releases API; a newer version is reported once (service notification, launcher button „Projektseite öffnen“ to the README's Update section, one line for `rfnegconv run`); never updates itself
- README: Update section at the top

### Changed
- The DNG carries the same gentle correction (contrast, saturation) as TIFF and JPEG; values outside 0–1 are kept unchanged (slope 1), the DNG preview shows the corrected picture
- Black-and-white TIFF and JPEG average the unlimited camera channels and limit afterwards, so they match the black-and-white DNG within 0–1
- `holder_min` larger than `holder_delta` is accepted: the effective value is max(0.3, min(holder_min, holder_delta))
- The config comment of `parallel_jobs` names the automatic value of the computer

## [26.10.7] - 2026-10-10

### Added
- Program „Negative entwickeln“ created by the installer (macOS `~/Applications`, Windows Start menu, Linux application menu): processes the `Negative` folder once, shows a short start notice and then the result in a dialog
- Installer option `--ohne-dienst` / `-OhneDienst`: no background service (an existing one is removed); processing starts only via „Negative entwickeln“
- `rfnegconv run --summary`: one machine-readable line `processed=<n> failed=<m> busy=<0|1>` for launchers
- `constraints.txt` (exported from `uv.lock`): both installers install exactly these library versions, so every install of a version gets the same libraries
- CI check that all version strings agree and that `constraints.txt` matches `uv.lock`; a release is only published after CI passes

### Changed
- The float16 DNG keeps values above the white point and below the black point; TIFF, JPEG, the DNG preview and the uint16 DNG stay limited to 0–1
- Only files that are themselves faulty go to `Negative/_Fehler/`; on a full disk, missing permission, a read-only or disconnected drive or too little memory the RAW stays in `Negative/`, and a full disk stops the batch with a notice
- A missing configured folder is created only if its parent folder exists (an unmounted drive never gets a folder tree on the system disk)
- Single runs log to `rfnegconv-run.log`, the background service to `rfnegconv.log`
- Installer: downloads time out (unreachable host after seconds), exiftool is set up last with a note on the duration, and a failure there only prints a hint
- Windows installer: an update stops only the background service, never a run in progress
- The config key `verbosity` is ignored; the amount of output is set with `-Q`, `-v`, `-vv`

### Fixed
- Unreachable, unwritable or full folders give one plain error line (`Error: …`), never a traceback; „Negative entwickeln“ shows that reason; the service reports it once per condition
- Moving to an archive on another drive never leaves a partial file under the final name
- Leftover `*_exiftool_tmp` files and archive temp files are cleaned up
- The uninstaller keeps uv's data when `uv tool list` fails
- macOS: files the Finder is still copying are not processed before the copy has finished
- Metadata from a DNG input never overwrites the DNG colour and rendering tags of our DNG (camera model, colour matrices, profiles, calibration, levels, crop)

## [26.10.6] - 2026-10-09

First public release.

### Added
- Fully automatic conversion of camera RAW scans of film negatives (colour and black and white) into DNG, TIFF and JPEG positives; no AI, only classical image processing with fixed, documented rules and thresholds
- Two-pass batch processing with roll context: frames of the same film share contrast and saturation; high-key frames borrow the film base of their roll; white and black point are measured per frame
- Automatic detection of the film base, the frame, the holder and the rotation; crop snapped to the film format, with the reason written into every output
- Gentle correction (roll-group contrast and saturation rule) applied identically to TIFF and JPEG; the DNG stays neutral
- Deterministic output; RAW files are only read and then archived, existing outputs are never overwritten, files are written atomically
- Background service (macOS LaunchAgent, Windows startup script, Linux systemd user unit) watching the `Negative` folder, plus double-click starters
- One-line installer and uninstaller for macOS, Linux and Windows (sets up uv and exiftool if missing, creates folders, configuration and desktop shortcuts)
- TOML configuration with `rfnegconv config init`, expert thresholds and the `RFNEGCONV_HOME` variable for isolated development runs
- Camera metadata copied with exiftool when available

[Unreleased]: https://github.com/jcmx9/real-fast-negconv/compare/v26.10.8...HEAD
[26.10.8]: https://github.com/jcmx9/real-fast-negconv/compare/v26.10.7...v26.10.8
[26.10.7]: https://github.com/jcmx9/real-fast-negconv/compare/v26.10.6...v26.10.7
[26.10.6]: https://github.com/jcmx9/real-fast-negconv/releases/tag/v26.10.6
