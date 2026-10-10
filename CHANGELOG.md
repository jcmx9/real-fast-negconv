# Changelog

All notable changes are documented in this file.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

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

[Unreleased]: https://github.com/jcmx9/real-fast-negconv/compare/v26.10.7...HEAD
[26.10.7]: https://github.com/jcmx9/real-fast-negconv/compare/v26.10.6...v26.10.7
[26.10.6]: https://github.com/jcmx9/real-fast-negconv/releases/tag/v26.10.6
