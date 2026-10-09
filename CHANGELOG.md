# Changelog

All notable changes are documented in this file.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [26.10.6] - 2026-10-09

First public release.

### Added
- Fully automatic conversion of camera RAW scans of film negatives (colour and black and white) into DNG, TIFF and JPEG positives; no AI, only classical image processing with fixed, documented rules and thresholds
- Two-pass batch processing with roll context: frames of the same film share film base, white point and contrast
- Automatic detection of the film base, the frame, the holder and the rotation; crop snapped to the film format, with the reason written into every output
- Gentle correction (roll-group contrast and saturation rule) applied identically to TIFF and JPEG; the DNG stays neutral
- Deterministic output; RAW files are only read and then archived, existing outputs are never overwritten, files are written atomically
- Background service (macOS LaunchAgent, Windows startup script, Linux systemd user unit) watching the `Negative` folder, plus double-click starters
- One-line installer and uninstaller for macOS, Linux and Windows (sets up uv and exiftool if missing, creates folders, configuration and desktop shortcuts)
- TOML configuration with `rfnegconv config init`, expert thresholds and the `RFNEGCONV_HOME` variable for isolated development runs
- Camera metadata copied with exiftool when available

[Unreleased]: https://github.com/jcmx9/real-fast-negconv/compare/v26.10.6...HEAD
[26.10.6]: https://github.com/jcmx9/real-fast-negconv/releases/tag/v26.10.6
