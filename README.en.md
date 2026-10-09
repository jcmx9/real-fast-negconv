# real-fast-negconv

**Version 26.10.6** · [Deutsch](README.md)

> Automatically converts camera RAW scans of film negatives (colour and black and white) into DNG, TIFF and JPEG positives.

[![CI](https://github.com/jcmx9/real-fast-negconv/actions/workflows/ci.yml/badge.svg)](https://github.com/jcmx9/real-fast-negconv/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

## Principles

- **Fully automatic.** Drop RAW files into a folder, get finished pictures. No user interface, and no settings are needed for daily use; the configuration is written once (three folders, optionally orientation).
- **Traceable and transparent.** Every decision follows fixed, documented rules and thresholds; all of them are described below, with the names of the constants in the code. Every output file carries a line saying how it was processed (colour/BW, film base, roll fallback, crop).
- **Deterministic.** The same RAW files in the same batch, the same configuration and the same program version give bit-identical DNG, TIFF and JPEG files (checked on real files, including the EXIF copy). Note: within a batch, frames of the same film influence each other (roll context), so the result of a frame also depends on which frames were processed together with it.
- **No AI.** No neural networks, no trained models, no machine learning, no cloud. Only classical image processing (logarithms, percentiles, morphology, contours, rotation) with fixed numbers.
- **Safe for originals.** RAW files are only read and then moved to the archive. Existing outputs are never overwritten. Every file is written to a temporary file first and only renamed when complete.

## Requirements

- macOS, Windows 10/11 or Linux and an internet connection for the installation. No administrator rights needed.
- The installer sets up everything else (see below). Only for the manual installation: [uv](https://docs.astral.sh/uv/) (installs a suitable Python ≥ 3.12 on its own), git and [exiftool](https://exiftool.org/) (recommended, copies camera metadata): `brew install exiftool` (macOS), `winget install OliverBetz.ExifTool` (Windows) or your distribution's package manager (Linux). Without exiftool everything works, the outputs just carry no camera data.
- Linux only: Perl for exiftool (usually present) and, for notifications, `notify-send` (e.g. package `libnotify-bin` on Debian/Ubuntu)

## Installation and update

One command sets up everything. macOS and Linux (Terminal):

```bash
curl -LsSf https://raw.githubusercontent.com/jcmx9/real-fast-negconv/main/install.sh | sh
```

Windows (PowerShell):

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/jcmx9/real-fast-negconv/main/install.ps1 | iex"
```

**Update:** run the same command again. An existing configuration, folders and images are never changed.

The installer

1. sets up [uv](https://docs.astral.sh/uv/) if it is missing (uv brings its own Python),
2. installs real-fast-negconv in the version that belongs to the installer,
3. sets up exiftool if it is missing (macOS with Homebrew via `brew`, otherwise the official package from exiftool.org with a verified checksum in the app data folder; on Linux only if Perl is present),
4. creates the folders `Pictures/rfnegconv/Negative`, `Fotos` and `Archiv` and writes the configuration – only if none exists yet (otherwise the folders entered there apply),
5. starts the background service,
6. puts the shortcuts „Negative“ and „Fotos“ on the desktop (your own shortcuts of the same name are left alone),
7. shows the version, the service status and where the folders are. If `rfnegconv` is not found in the terminal afterwards, open a new terminal window.

After that it is enough to put scans into the „Negative“ folder; the pictures appear in „Fotos“ automatically.

### For advanced users: manually with uv

Install uv (once), macOS and Linux:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Windows (PowerShell):

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Install real-fast-negconv (needs git):

```bash
uv tool install git+https://github.com/jcmx9/real-fast-negconv.git
```

Update to the latest version (the configuration is kept):

```bash
uv tool install --force git+https://github.com/jcmx9/real-fast-negconv.git
```

Create the folders and the configuration (written only if no configuration exists yet) and start the service:

```bash
rfnegconv config init --negative ~/Pictures/rfnegconv/Negative --photos ~/Pictures/rfnegconv/Fotos --archive ~/Pictures/rfnegconv/Archiv
```

```bash
rfnegconv service install
```

## Uninstall

macOS and Linux:

```bash
curl -LsSf https://raw.githubusercontent.com/jcmx9/real-fast-negconv/main/install.sh | sh -s -- --uninstall
```

Windows (PowerShell):

```powershell
powershell -ExecutionPolicy ByPass -c "& ([scriptblock]::Create((irm https://raw.githubusercontent.com/jcmx9/real-fast-negconv/main/install.ps1))) -Uninstall"
```

This removes the background service , the program  and the desktop shortcuts the installer created (only if they still point to the folders); exiftool and uv only if the installer set them up itself (recorded in the file `installer-state` in the app data folder). uv's managed Python is removed only if the installer set up uv itself and no other uv tools remain. **The folders, the images and the configuration are never deleted.** Manually: `rfnegconv service uninstall`, then `uv tool uninstall real-fast-negconv`.

## Folders and daily use

The program works with three folders that you choose once in the configuration (the names are up to you; here: `Negative`, `Fotos`, `Archiv`):

| Folder | Key | Purpose |
|--------|-----|---------|
| `Negative/` | `negative_dir` | Inbox: put RAW files here |
| `Fotos/` | `photos_dir` | Results: `<name>.dng`, `<name>.tif`, `<name>.jpg` |
| `Archiv/` | `archive_dir` | Originals after successful processing |

Daily use:

1. Copy the RAW files of a film into `Negative/` – ideally the whole film at once, because frames of the same film are matched to each other.
2. Start processing (double-click starter, `rfnegconv run`, or nothing at all when the background service runs).
3. The pictures appear in `Fotos/`, the originals move to `Archiv/`.
4. If a file cannot be processed, it moves to `Negative/_Fehler/`; next to it is a `.txt` file with the reason in plain words.
5. To create a picture again (e.g. after changing the configuration), move the RAW from `Archiv/` back into `Negative/`. Existing results are kept; the new ones are called `<name>_2` and so on.

### Without a terminal: double-click starters

`scripts/rfnegconv.command` (macOS) and `scripts/rfnegconv.bat` (Windows) process the `Negative/` folder once and keep the window open until you press a key. Copy the file from the repository to the desktop, for example. Starting it while the background service is working is harmless: a lock file in `Negative/` prevents double processing, and the starter reports „Der Dienst verarbeitet gerade – bitte später erneut versuchen.“ (the service is busy, try again later).

### Background service

The service watches `Negative/`, waits until copying has finished and then processes the files on its own. It starts at every login. At the end of each batch a desktop notification shows „N Fotos fertig, M Fehler“ (N pictures done, M errors).

```bash
rfnegconv service install
```

```bash
rfnegconv service status
```

```bash
rfnegconv service uninstall
```

Implementation: macOS LaunchAgent `~/Library/LaunchAgents/io.github.jcmx9.rfnegconv.plist` (restarted after a crash), Windows `rfnegconv.vbs` in the startup folder (no admin rights needed), Linux systemd user unit `~/.config/systemd/user/rfnegconv.service` (`Restart=on-failure`). The service runs `rfnegconv -Q watch`; the `PATH` at installation time is taken over so that exiftool is found.

## Configuration

### Location of the configuration file

| System | Path |
|--------|------|
| macOS | `~/Library/Application Support/real-fast-negconv/config.toml` |
| Linux | `~/.config/real-fast-negconv/config.toml` |
| Windows | `%LOCALAPPDATA%\real-fast-negconv\config.toml` |

A different file can be given with `--config PATH`. If the file is missing or a folder is not set, the program says which key is missing and where it expects the file. Unknown keys are an error (protection against typos).

### Example

```toml
negative_dir = "~/Film/Negative"
archive_dir  = "~/Film/Archiv"
photos_dir   = "~/Film/Fotos"
rotate = 0                    # 0 | 90 | 180 | 270 (clockwise)
mirror = false                # true when shot from the emulsion side
dng = true                    # false: only TIFF + JPEG
dng_finder_preview = false    # true: larger DNG that Finder and Quick Look display
```

`~` stands for the home folder. The three folders must be different; missing folders are created.

### All keys

Every key is optional except the three folders. Types: `path` = text in quotes, `bool` = `true`/`false`, `int`/`float` = number.

#### Folders

| Key | Type | Default | Allowed | Effect |
|-----|------|---------|---------|--------|
| `negative_dir` | path | – (required) | existing or creatable folder | Inbox for RAW files; only files directly in it are processed |
| `photos_dir` | path | – (required) | different from the other two | Output folder for DNG, TIFF, JPEG |
| `archive_dir` | path | – (required) | different from the other two | Originals are moved here after success |

#### Outputs

| Key | Type | Default | Allowed | Effect |
|-----|------|---------|---------|--------|
| `dng` | bool | `true` | `true`, `false` | Write the DNG |
| `dng_finder_preview` | bool | `false` | `true`, `false` | `false`: float16 DNG with Deflate (smaller). `true`: uncompressed uint16 DNG that macOS Finder and Quick Look display (larger). Both lossless |
| `jpeg_quality` | int | `95` | 1–100 | JPEG quality |

#### Orientation

| Key | Type | Default | Allowed | Effect |
|-----|------|---------|---------|--------|
| `rotate` | int | `0` | `0`, `90`, `180`, `270` | Rotate clockwise (per scanning setup, applies to all files) |
| `mirror` | bool | `false` | `true`, `false` | Mirror horizontally, before rotating (film shot from the emulsion side) |

#### Correction

TIFF and JPEG contain the corrected picture (gentle correction, section 5), the DNG the neutral linear data.

#### Service and operation

| Key | Type | Default | Allowed | Effect |
|-----|------|---------|---------|--------|
| `notify` | bool | `true` | `true`, `false` | Desktop notification after each batch |
| `parallel_jobs` | int | `0` | ≥ 0 | Files processed at the same time; `0` = automatic: min(CPU cores, ⌊half the RAM / 4 GiB⌋, number of files), at least 1 |
| `settle_seconds` | float | `5.0` | > 0 | Watch mode: files must be unchanged this long before a batch starts; also the retry wait (limited to 5–60 s) |
| `exiftool_path` | path | empty | path to the program | Empty = search `exiftool` on the `PATH` |
| `verbosity` | int | `1` | 0–3 | Set by `-Q`/`-v`/`-vv` on the command line; a value in the file has no effect |

#### Expert thresholds

Only needed if detection fails on unusual material. Names as in the code (`AnalyzerSettings`, `RollSettings`); the steps are explained in [Processing step by step](#processing-step-by-step).

| Key | Type | Default | Allowed | Effect |
|-----|------|---------|---------|--------|
| `measure_inset` | float | `0.10` | 0–0.25 | Inner measurement window: share of the crop's height/width left out on each side (0.10 = inner 80 %) |
| `holder_delta` | float | `1.8` | > 0 | Film mask: density above the clearest base up to which a pixel counts as film |
| `holder_min` | float | `1.0` | 0.3–`holder_delta` | Translucent holder: minimum density above the clearest base from which a border strip can count as holder (step 4); default min(1.0, holder_delta), at least 0.3 |
| `gap_delta` | float | `0.10` | > 0 | Strict base pixel (gap between frames): density limit above the base |
| `gap_std` | float | `0.03` | > 0 | Strict base pixel: limit of the local standard deviation |
| `loose_delta` | float | `0.15` | > 0 | Loose base pixel (edge trimming): density limit above the base |
| `loose_std` | float | `0.08` | > 0 | Loose base pixel: limit of the local standard deviation |
| `aspect_tol` | float | `0.08` | > 0 and < 1 | Snap to a film format if the aspect ratio deviates by less than this (relative) |
| `min_skew_deg` | float | `0.2` | 0–45 | Smallest skew angle that is corrected (degrees) |
| `max_skew_deg` | float | `5.0` | 0–45 | Largest skew angle that is corrected (degrees) |
| `dmin_percentile` | float | `0.2` | 0–100 | Percentile (in %) of the density over the film mask that counts as film base |
| `white_percentile` | float | `99.5` | > 0 and ≤ 100 | Percentile (in %) of the density in the inner window that counts as white point |
| `bw_threshold` | float | `0.03` | > 0 | Colour/BW decision: limit for the channel deviation (99.9th percentile) |
| `gamma_color` | float | `0.6` | > 0 | Gradation of colour film in the conversion to linear light |
| `gamma_bw` | float | `0.65` | > 0 | Gradation of black-and-white film |
| `hue_tol` | float | `0.06` | > 0 | Roll grouping: largest distance of the film-base hue |
| `highkey_delta` | float | `0.10` | ≥ 0 | High-key fallback: minimum lift of the film base in every channel |
| `uniform_ratio` | float | `2.0` | ≥ 1 | High-key fallback: largest lift at most this times the smallest |
| `crossover_limit` | float | `0.15` | 0–0.5 | Colour crossover correction: exponent k per channel at most this far from 1; `0` switches it off (step 3.5) |

### Fixed values (not configurable)

| Constant | Value | Module | Meaning |
|----------|-------|--------|---------|
| `PREVIEW_EDGE` | 1000 | `core/analyzer.py` | Analysis preview: step n = max(1, ⌊long edge / 1000⌋) |
| `EDGE_BAND_FRACTION` | 0.6 | `core/analyzer.py` | Trimming: remove column/row while > 60 % loose base pixels |
| `GAP_FRACTION` | 0.9 | `core/analyzer.py` | Gap: column/row with > 90 % strict base pixels |
| `EDGE_FACTOR` | 2.5 | `core/analyzer.py` | Anchored edge: edge score ≥ 2.5 × typical score |
| `EDGE_WINDOW` | 0.06 | `core/analyzer.py` | Search window around an end: ±6 % of the axis length |
| `ASPECTS` | 1:1 = 1.00, 6x7 = 1.24, 6x4.5 = 1.35, 3:2 = 1.50 | `core/analyzer.py` | Film formats for snapping |
| `crop_rect(inset)` | 0.01 | `core/geometry.py` | Crop pulled in by 1 % of its longer side on every side |
| `MEASURE_INSET` | 0.10 | `core/geometry.py` | Default of `measure_inset` |
| `MIN_SPREAD` | 0.05 | `core/converter.py` | Smallest density range per channel |
| `black_point(percentile)` | 0.5 | `core/converter.py` | Black point: 0.5th percentile of the luminance |
| `EPS` | 1/65535 | `core/converter.py` | Smallest value before the logarithm |
| `COLOR_STRENGTH`, `BW_STRENGTH` | 1.0, 0.5 | `core/look.py` | Strength of the correction for colour and BW |
| `SPREAD_TARGET`, `MAX_CONTRAST` | 0.70, 0.35 | `core/look.py` | Contrast rule (group) |
| `CHROMA_TARGET`, `SAT_GAIN`, `MAX_SATURATION`, `CHROMA_FULL` | 0.10, 1.5, 1.15, 0.5 | `core/look.py` | Saturation rule |
| `SAMPLE_STEP` | 4 | `core/look.py` | Look statistics on every 4th pixel |
| `MID_BAND`, `MIN_MID_PIXELS` | 0.05, 200 | `core/crossover.py` | Crossover: mid-grey pixels with \|x_G − 0.5\| < 0.05; fewer than 200 in the inner window: no measurement |
| `MID_CLIP` | 0.05–0.95 | `core/crossover.py` | Crossover: mids are clipped to this range before the logarithm |
| `ROLL_MIN_FRAMES`, `ROLL_AGREEMENT` | 3, 0.8 | `core/crossover.py` | Crossover per roll: at least 3 measured colour frames, ≥ 80 % of them on the same side for R and for B |
| `SAMPLE_MAX_PIXELS` | 87,381 | `core/crossover.py` | Density sample of the inner window per frame (at most 1 MiB) |
| `PREVIEW_LONG_EDGE` | 1024 | `service/render.py` | Long edge of the preview embedded in the DNG |
| `MEMORY_PER_WORKER` | 4 GiB | `service/batch.py` | RAM budget per parallel job |
| `STALE_TEMP_SECONDS` | 3600 | `service/batch.py` | Leftover temporary files older than 1 h are deleted |
| `RESCAN_SECONDS` | 60 | `service/watcher.py` | Watch mode: rescan the folder at least once a minute |

## Processing step by step

### Overview

Each run processes all files of a batch in two passes: **pass 1** analyses every file on a small preview, then the **roll context** compares the files with each other, and **pass 2** develops every file at full resolution and writes the outputs. Three regions of the scan are distinguished, and they are determined in this order:

1. **Film mask** – the whole film strip in the picture (frames, gaps between frames, rebate), without the holder. The film base `d_min` is measured here.
2. **Crop** – the detected frame, determined first and completely (deskew, edges, gaps, format snapping, 1 % pull-in). TIFF and JPEG are cut to it; the DNG carries it as a resettable crop setting. Colour/BW is measured here.
3. **Inner window** – the crop without `measure_inset` (10 %) of its height/width on every side (inner 80 % × 80 %), always placed relative to the *final* crop. White point, black point, crossover and all look statistics are measured here, so that a sliver of rebate or holder at the edge cannot shift them.

### 1. Trigger and batch start

1. **Trigger.** `rfnegconv run` (or `rfnegconv` without a command, or a double-click starter) processes the folder once. In watch mode (`rfnegconv watch`, background service) a file system event or, at the latest, a rescan every 60 s wakes the program; files already waiting are processed at start.
2. **Settle gate (watch mode only).** Every 0.5 s the size and modification time (`mtime_ns`) of all candidate files are read; a file that cannot be opened for reading yet (Windows while copying) counts as unstable. The batch starts once this state has not changed for `settle_seconds` (5 s). Files that failed and could not be moved are skipped until their size or time changes.
3. **Folders.** All three folders must be set and different; missing ones are created.
4. **Lock.** Exclusive, non-blocking lock on `Negative/.rfnegconv.lock`. If another run holds it, this run ends immediately without touching anything („Der Dienst verarbeitet gerade – bitte später erneut versuchen.“, exit code 0); watch mode retries after min(60, max(5, `settle_seconds`)) s. File systems without lock support: warning, run without lock.
5. **Cleanup.** Temporary files of interrupted runs (`.<name>.tmp.*`) in `Fotos/` that are older than 1 h are deleted.
6. **Input list.** Files directly in `Negative/` (no subfolders, so `_Fehler/` is ignored) whose extension is a known RAW format (case does not matter), excluding names starting with `.` (hidden files, macOS `._` AppleDouble files). Sorted by name.
7. **exiftool and parallelism.** exiftool is looked up (`exiftool_path`, otherwise `PATH`; if missing: one warning). Number of parallel jobs: see `parallel_jobs`. Parallel jobs are threads; they do not change the result.

### 2. Pass 1: analysis of every file

On a preview of the half-resolution RAW. A file that fails here goes to `_Fehler/` immediately.

1. **Loading.** LibRaw (via rawpy) decodes the RAW at half resolution with 16 bit, linear (gamma 1), without white balance (all multipliers 1), without auto brightness, in the camera's own RGB colour space; demosaicing is LibRaw's default. LibRaw applies the orientation stored in the RAW, so all outputs carry `Orientation = 1`. Values are divided by 65535 (0–1). The camera colour matrix (XYZ → camera) is read along; if it is missing, the identity matrix is used.
2. **Preview.** Every n-th pixel in both directions, n = max(1, ⌊long edge / 1000⌋), so the long edge of the preview is 1000–1999 pixels.
3. **Density.** Per channel D = −log10(max(T, 1/65535)), T = linear value. On a negative the film base has the lowest density, the brightest parts of the scene the highest. For detection the channel mean `lum` is used.
4. **Film mask** (region 1). Reference `d_ref` = 0.5th percentile of `lum` (the clearest film base), measured without *bare light*: pixels more than 0.2 below the 0.5th percentile of the image interior (without a 2 % of the long edge border on each side) are a strip of light at the image border (no film) and count neither for `d_ref`, nor for the film mask, nor for `d_min`. This works only while the part of the strip inside the interior is below 0.5 % of the interior pixels; above that the strip itself sets the percentile and the result equals the behaviour without bare-light handling. Pixels with `lum < d_ref + holder_delta` (1.8) are film, denser pixels are holder. Then morphological opening and closing with a square kernel of max(3, long edge / 100) pixels (odd), and only the largest connected region is kept. If there is none, the whole picture counts as film. *Translucent holder:* if the detection with this fixed threshold is not confident (step 11), border strips are searched that are less dense than `holder_delta` but clearly denser than the base. Per image side, the columns (left/right) or rows (top/bottom) from the image border inwards count whose density above `d_ref` has, over the whole side length, a median ≥ `holder_min` (1.0) and a 10th percentile ≥ 0.8 × `holder_min` (uniformly dense along ≥ 90 % of the side). Such a strip only counts as holder if a base-like line (median ≤ `d_ref` + `loose_delta`, the rebate) follows within max(2, 0.5 % of the long edge) lines; the strip then reaches up to that line. A bright motif area at the border (sky) has no such line after it and stays film. The strips are taken out of the film mask, steps 6–11 run again, and the result is used only if it is confident; otherwise everything stays as with the fixed threshold. A confident detection with the fixed threshold is never changed (dense film holders).
5. **Skew** (from the outer edges of the frame). Steps 6–11 first run without rotation and give a rough frame rectangle: the edges of the segment found *before* format snapping and shortening (steps 9–10), or the bounding box of the film mask if the detection is not confident. So the angle does not depend on which end is shortened. Edge map = magnitude of the gradient of `lum`, only on film pixels (film mask shrunk by max(3, long edge / 100) pixels, odd; the film/holder edge does not count) and only in four bands around the outer edges of this rectangle: per edge 4 % of its longer side inwards and outwards. The interior of the frame does not count, so lines in the motif do not influence the angle. The band pixels are rotated by a trial angle θ (counter-clockwise, around the image centre, as in deskewing); score = sum of the squared row profiles of the top and bottom bands plus sum of the squared column profiles of the left and right bands (profile step 1 pixel, linear split onto the two neighbouring cells after a fixed random offset of ±0.5 pixel per pixel, so that the pixel grid does not favour 0°). θ runs from −`max_skew_deg` to +`max_skew_deg` (5°) in steps of 0.25°, then in steps of 0.02° within ±0.25° around the best coarse result (13 steps per side); on a tie the smaller |θ| wins, for ±θ the negative one. If the best score is less than 1 % above the one at θ = 0 (no noticeable edge), `cv2.minAreaRect` around the outline of the film mask gives the angle instead, normalised to −45° to +45°. Only if `min_skew_deg` (0.2°) ≤ abs angle ≤ `max_skew_deg` (5°) are preview and mask rotated around the centre by this angle and steps 6–11 run again on the rotated image; otherwise the angle is 0 and the result of the first run applies. If the first run was confident but the second (rotated) one is not, the unrotated result of the first run applies as well (angle 0).
6. **Base pixels.** Local standard deviation of `lum` in a window of max(3, long edge / 100) pixels (odd: `max(3, edge // 100) | 1`), over film pixels only (the holder cannot raise it at the film edge). *Strict* base pixel: `lum < d_ref + gap_delta` (0.10) and standard deviation < `gap_std` (0.03). *Loose* base pixel: `lum < d_ref + loose_delta` (0.15) and standard deviation < `loose_std` (0.08), or outside the film mask. The following steps work inside the bounding box of the film mask; its longer side is the long axis of the strip.
7. **Trimming the edges.** For every column (and row) the share of loose base pixels is computed; from both ends, columns/rows are removed while the share is > 60 % (rebate, gap fringe, holder edge). If less than 10 % of the axis would remain, nothing is trimmed.
8. **Splitting at gaps** (long axis only). Within the trimmed range, runs of columns with > 90 % strict base pixels that are at least max(2, long side of the box / 100) wide are gaps between frames. The widest segment between them is the frame. Deep shadows in the scene practically never meet the strict criteria.
9. **Format snapping.** The ratio long/short side is compared with 1:1 (1.00), 6×7 (1.24), 6×4.5 (1.35) and 3:2 (1.50); the format with the smallest relative deviation wins if that deviation is < `aspect_tol` (8 %). The side that is too long is shortened to the exact ratio. Otherwise the format stays "free".
10. **Which end is shortened** (only after snapping; first along the columns, then along the rows). Edge score of a column = median over the frame's rows of the absolute density difference to the next column. An end is *anchored* (a sharp frame border) if the highest edge score within ±6 % of the axis length around it reaches 2.5 × (`EDGE_FACTOR`) the median edge score inside the segment. Both ends anchored: the edge is the position of the highest edge score in the window; whatever lies between the segment end and the edge is an outer band (fog, rebate). The excess is removed half from each end, unless an outer band would remain: then the split is shifted just far enough to remove it. If both outer bands together are wider than the excess, the crop is centred between the two edges (at most the whole excess at one end); if the frame is shorter than the format, the crop may then extend a few rows past one edge. Known failure mode: the steepest step within the ±6 % window may be a straight motif edge instead of the frame border; the damage is bounded by the excess. One end anchored: the whole excess is removed at the other end. No end anchored: of all possible splits, the one is taken whose removed bands have the lowest summed median density (close to film base: fog, rebate, gap fringe); ties go to the symmetric split.
11. **Confidence and fallback.** The detection is *confident* if the format snapped, at least one edge was trimmed or one gap was found, and the frame covers 25–98 % of the film mask. Otherwise the bounding box of the film mask is used as the frame (`crop=uncertain` in the description).
12. **Crop** (region 2). The frame is scaled to the resolution in use and pulled in by 1 % of its longer side on every side.
13. **Inner window** (region 3). The crop from step 12 without `measure_inset` (10 %) of its height and width on each side.
14. **Film base `d_min`** (region 1). Per channel the `dmin_percentile` (0.2 %) percentile of the density over the whole deskewed film mask (frames, gaps, rebate; no holder). Signature = (d_min_R − d_min_G, d_min_B − d_min_G): the hue of the film base, used for roll grouping.
15. **White point `d_white`** (region 3). Per channel the `white_percentile` (99.5 %) percentile of the density in the inner window.
16. **Colour or BW** (region 2). The density of the crop is normalised as in pass 2, step 3 (with this frame's own `d_min` and `d_white`), averaged over blocks of 4 × 4 pixels; per block the mean absolute deviation of the three channels from their mean. If the 99.9th percentile of these deviations is < `bw_threshold` (0.03), the frame is BW; so even a small share of clearly coloured details decides for colour.
17. **Look statistics** (region 3). The crop of the preview is developed exactly as in pass 2, steps 3, 4 and 7–10 (this frame's own `d_min`, `d_white`, gamma by its own colour/BW result, black point on the inner window, camera → sRGB or channel mean for BW, sRGB curve). On the inner window, every 4th pixel in both directions: **spread** = 95th minus 5th percentile of the luminance (Rec. 709 weights 0.2126, 0.7152, 0.0722), **chroma** = mean of (largest − smallest channel) per pixel (0 for BW). All values are clipped to 0–1 beforehand.
18. **Samples for the crossover and the look** (region 3). The density of the inner window is thinned in raster order to every s-th pixel, s = ⌈pixel count / 87,381⌉ (at most 1 MiB per frame), together with the density of the look grid from step 17 (inner window, every 4th pixel). Both are kept until the roll context (steps 3.4 and 3.5) and dropped afterwards. Until then the run needs about 1.3–2.3 MiB extra per file in the folder (100 files ≈ 130–230 MiB).

### 3. Roll context

Applies to the files of one batch that passed pass 1, in name order.

1. **Grouping by film base.** Two frames are neighbours if their signatures (step 2.14) are closer than `hue_tol` (0.06, Euclidean distance). Groups are formed by chaining (single linkage): if A–B and B–C are neighbours, A, B and C form one group. Frames of the same film under the same light end up in one group.
2. **High-key fallback** (groups with ≥ 2 frames). Baseline = 25 % quantile per channel of the group's `d_min` values. A frame uses the baseline instead of its own `d_min` only if all of these hold: in every channel its `d_min` lies more than `highkey_delta` (0.10) above the baseline; the lift is even (largest ≤ `uniform_ratio` (2.0) × smallest); its signature is closer than `hue_tol` to the median signature of the group. It is never corrected downwards. Reason: in a very bright frame (snow, sky) even the clearest pixels are not film base; the roll knows the real base. The description then says `fallback=yes`.
3. **Colour or BW per roll.** In a group with ≥ 2 frames the majority decides: more than half BW → all BW, otherwise all colour (a tie gives colour). A colourless subject on colour film thus stays colour. Single frames keep their own result. An overruled frame gets a log line.
4. **Look parameters.** They are based on the look statistics of the preview corrected for the crossover (step 3.5, determined first): with k ≠ 1 they are measured again with k on the look grid (step 2.18), otherwise those of step 2.17 apply. No exposure correction; contrast and saturation per group from the median spread and median chroma of its frames (frames with high-key fallback are left out as long as the group has others); single frames use their own values. Formulas: [Gentle correction in detail](#5-gentle-correction-in-detail).
5. **Colour crossover (layer steepness).** The three dye layers of a colour negative have slightly different gradation curves: film base and white point are neutral after the channel normalisation, the mid-tones are not (typically: the whole image a little too warm). *Per colour frame:* on the sample (step 2.18), x_c = (D_c − d_min_used_c) / max(d_white_c − d_min_used_c, 0.05), i.e. measured with the film base actually used (also after the high-key fallback). Mid-grey are the pixels with |x_G − 0.5| < 0.05; if there are fewer than 200 (scaled to the whole inner window), nothing is measured (k_frame = 1). Otherwise mid_c is the median of x_c of these pixels and k_frame_c = ln 0.5 / ln(mid_c, clipped to 0.05–0.95) for R and B; G keeps 1. *Per roll group:* a roll value is valid only with ≥ 3 measured colour frames of which, for R and for B, ≥ 80 % lie on the same side of 0.5 as the group median; then k_roll from the group medians of the mids (same formula), else k_roll = 1. *Result:* k_c = sqrt(k_frame_c · k_roll_c), clipped to 1 ± `crossover_limit` (0.15). The roll thus damps frames dominated by a motif colour (snow, warm evening light); a frame without a valid roll value gets half the correction (in the logarithm). BW frames: k = 1. `crossover_limit = 0` switches the correction off.

### 4. Pass 2: development and output of every file

At full resolution, in parallel; the steps of one file run in this order.

1. **Loading.** As in pass 1, step 1, but at full resolution.
2. **Density.** D = −log10(max(T, 1/65535)) per channel.
3. **Neutralisation and channel normalisation.** `d_min_used` = film base from the roll context, `d_white` from pass 1. Per channel d_hi = max(d_white − d_min_used, 0.05), D_target = mean of the three d_hi, D_norm = max(D − d_min_used, 0) · D_target / d_hi. Subtracting the film base removes the orange mask; the scaling gives all three channels the same density range, so film base and white point become neutral.
4. **Crossover and linear light.** x = D_norm / D_target per channel, x' = x^k_c with k from step 3.5 (film base 0 and white point 1 stay fixed, only the mid-tones move), then Y = 10^((x' · D_target − D_target) / γ) with γ = `gamma_color` (0.6) or `gamma_bw` (0.65) according to the roll decision. The white point becomes 1.0, the film base the darkest value. The correction is part of the inversion, not of the look: DNG, TIFF and JPEG all contain it.
5. **Deskew.** Rotation by the angle from pass 1 around the centre (bilinear, edges continued).
6. **Orientation.** First mirror horizontally (`mirror`), then rotate clockwise by `rotate`; the crop rectangle follows.
7. **Black point** (region 3). b = 0.5th percentile of the luminance (mean of the channels, every 4th pixel) in the inner window of the oriented crop. If 0 < b < 0.99: Y = (Y − b) / (1 − b), the same offset for all channels. Then all values of the whole picture are clipped to 0–1.
8. **BW.** For BW frames the three channels are averaged into one.
9. **Colour space** (crop only). Camera RGB → linear sRGB with the camera matrix (dcraw method: (XYZ → camera) · (sRGB → XYZ, D65), rows normalised so that neutral stays neutral, inverted; unusable matrix → identity matrix and a warning). Negative values become 0.
10. **sRGB curve** (crop only). Standard sRGB transfer function (IEC 61966-2-1). The result is the neutral sRGB picture.
11. **Description.** One line, e.g. `rfnegconv 26.10.6 | color | dmin=0.415,0.437,0.908 | fallback=no | crop=1:1 | crossover: R x1.102 B x0.874 (frame+roll) | crop: …` (colour/BW, film base used, roll fallback, snapped format or `uncertain`; crossover with k for R and B and its source `frame+roll`, `frame only`, `roll only` or `none` (no correction), left out with `crossover_limit = 0`; at the end `| crop: …` with the reason for the crop). The log line from `-v` reads `<file>: crop <W>×<H>, crossover R x… B x… (…) — <reason>`. It is written into all three files (`ImageDescription`) and into the log.
12. **DNG** (if `dng = true`). The *whole* deskewed and oriented picture after steps 3–8 (neutral, linear, camera RGB, 0–1; BW as three identical channels), not cut. `dng_finder_preview = false`: float16, Deflate with floating-point predictor, tiles 256 × 256. `true`: uint16 uncompressed (0–65535, BlackLevel 0, WhiteLevel 65535). The first image of the file is an 8-bit sRGB preview of the neutral cropped picture (long edge ≤ 1024 px), the main image follows as a SubIFD. Tags: DNGVersion 1.4.0.0, UniqueCameraModel (make and model via exiftool, otherwise `real-fast-negconv`), ColorMatrix1 = camera matrix, CalibrationIlluminant1 = D65, AsShotNeutral = (1, 1, 1), BaselineExposure = 0, Orientation = 1. The crop travels as embedded Camera Raw XMP (`crs:ProcessVersion 11.0`, `HasCrop`, `CropTop/Left/Bottom/Right` relative 0–1, `CropAngle 0`, `AlreadyApplied False`): in Lightroom or Camera Raw it can be reset or widened up to the full scan.
13. **TIFF.** The cropped sRGB picture with the gentle correction (section 5). 16 bit, Deflate with predictor; colour as RGB with embedded sRGB profile, BW as one grey channel.
14. **JPEG.** The same corrected picture as the TIFF, only compressed (no second computation). 8 bit, quality `jpeg_quality` (95); colour with sRGB profile, BW as greyscale.
15. **EXIF.** If exiftool is available, all metadata of the RAW is copied into every output (`-TagsFromFile … -all:all`), except MakerNotes, Orientation, ImageDescription, Software, ImageWidth/ImageHeight and Camera Raw settings (`XMP-crs`); thumbnails and previews of the RAW are not copied, Orientation is set to 1. A failure here only gives a warning.
16. **Writing.** Every file is first written as `.<name>.tmp.<pid>.<random><extension>` next to the target and then renamed in one step; a half-written file never has the final name.
17. **Archive.** The original is moved to `Archiv/` (`<name>_2.<ext>` etc. if the name is taken). Only now does the file count as done (log line `OK <name> - <description>`).
18. **Errors.** If something in steps 1–17 fails, the outputs of this file already written are deleted again, and the original moves to `Negative/_Fehler/` with a text file `<name>.txt`: „<name> konnte nicht verarbeitet werden.“, „Grund: …“ (plain German: unreadable or damaged RAW, no space left, no permission, otherwise „Unerwarteter Fehler.“), „Technisch: …“ (exception text) and „Zeitpunkt: …“. One faulty file never stops the batch.

After the batch: log summary, console output `N converted, M failed` (exit code 1 if anything failed), notification „N Fotos fertig, M Fehler“ if `notify = true` and something was processed.

### 5. Gentle correction in detail

Contained in TIFF and JPEG, identically in both (a picture is corrected once and written twice); the DNG stays neutral. In the code it is called "look" (`core/look.py`). It never changes the brightness: no brightening or darkening, no exposure correction. It only corrects what film, scan and inversion make flat: contrast and, for pale colour pictures, saturation.

**Inputs.** Two measurements per picture, taken on the neutral sRGB preview of the crop (after crossover, black point, camera matrix and sRGB curve; step 2.17, or step 3.4 with a re-measured k) in the inner window (`measure_inset`), every 4th pixel (`SAMPLE_STEP`), values clipped to 0–1:

- **Spread** = 95th minus 5th percentile of the luminance (weights 0.2126, 0.7152, 0.0722).
- **Chroma** = mean of (largest − smallest channel) per pixel; 0 for BW.

**Roll group.** The spread and chroma the parameters are derived from are the median over all pictures of the group (pictures with a high-key fallback do not count as long as the group has others); a single picture uses its own values. All pictures of a group therefore get the same parameters, and a roll looks consistent.

**Formulas and constants** (all in `core/look.py`):

| Step | Formula | Constants |
|------|---------|-----------|
| Contrast | s = strength · clip(`SPREAD_TARGET` − spread, 0, `MAX_CONTRAST`) | `SPREAD_TARGET` = 0.70, `MAX_CONTRAST` = 0.35 |
| Strength | colour 1.0, BW 0.5 | `COLOR_STRENGTH`, `BW_STRENGTH` |
| S-curve | y = (1 − s) · x + s · (3x² − 2x³), per channel | – |
| Saturation (colour only) | sat = clip(1 + `SAT_GAIN` · (`CHROMA_TARGET` − chroma), 1, `MAX_SATURATION`) | `CHROMA_TARGET` = 0.10, `SAT_GAIN` = 1.5, `MAX_SATURATION` = 1.15 |
| Chroma weighting | c = largest − smallest channel; factor = 1 + (sat − 1) · (1 − clip(c / `CHROMA_FULL`, 0, 1)); y = L + (x − L) · factor | `CHROMA_FULL` = 0.5 |

Finally all values are clipped to 0–1. The S-curve leaves 0, 0.5 and 1 unchanged; it deepens shadows and lifts highlights slightly while the midtone stays. The saturation acts fully only on pale pixels (small c); vivid ones keep their colour.

**What it never does:** no exposure change, no brightening of dark or darkening of bright shots, no hue change, no effect on the DNG and no dependency on the output format.

**Effect on example pictures** (described only by their measurements; numbers from the formulas above):

| Example picture | Spread | Chroma | Contrast s | Saturation |
|-----------------|--------|--------|------------|------------|
| Normal colour negative with full tonal range | 0.75 | 0.15 | 0 (no change) | 1.00 |
| Slightly flat colour negative | 0.60 | 0.08 | 0.10 | 1.03 |
| Flat, pale colour negative | 0.50 | 0.04 | 0.20 | 1.09 |
| Very flat, low-colour negative | 0.30 | 0.02 | 0.35 (upper limit) | 1.12 |
| Flat BW negative (half strength) | 0.50 | – | 0.10 | – |

With s = 0.20 the grey value 0.25 becomes 0.231 and 0.75 becomes 0.769, 0.50 stays 0.50. With saturation 1.09 the distance of a pale pixel (c = 0.05) from its grey value L grows by a factor of 1.081; a vivid one (c ≥ 0.5) is unchanged.

### What the program does not do

- No AI, no trained models, no cloud or network access.
- No automatic upright detection: `rotate`/`mirror` apply to all files alike (one value per scanning setup).
- No dust or scratch removal, no sharpening, no noise reduction.
- No per-picture manual adjustments and no user interface; fine-tuning is done afterwards in the DNG with an editor of your choice.
- No slide film (positives) and no film-stock profiles.
- If one scan shows several frames, only the widest frame is output.
- No subfolders: only files directly in `Negative/` are processed.
- No XMP sidecar files are written or read.

## Outputs

Per RAW `<name>.<ext>` three files appear in `Fotos/` (without DNG with `dng = false`):

| File | Content | Crop | Colour | Correction | Size per megapixel |
|------|---------|------|--------|------------|--------------------|
| `<name>.dng` | linear, float16 Deflate (or uint16 uncompressed), embedded preview | full scan, crop as resettable setting | camera RGB with colour matrix | neutral | about 3.6 MB (uint16: about 6.1 MB) |
| `<name>.tif` | 16 bit, sRGB curve, Deflate | cut | sRGB (BW: grey) | gentle (section 5) | about 3.3 MB |
| `<name>.jpg` | 8 bit, quality 95 | cut | sRGB (BW: grey) | gentle, same as the TIFF | about 0.2–0.4 MB |

Sizes grow with the pixel count and depend on the picture content (grain and noise enlarge TIFF and JPEG); the table gives rough values per megapixel. The three files of a RAW always share the same name. If `<name>.dng`, `.tif` or `.jpg` already exists in `Fotos/` (or two RAWs in a batch have the same name), `<name>_2`, `<name>_3` … is used for all three. Nothing is overwritten.

**Why this crop?** Every frame states the reason for its crop and rotation, in the log and in the files. With `-v` the console shows one line per file, the log file always has it (INFO):

```
scan_0001.ARW: crop 6178×6178 — rotated 0.54° (frame edges); snapped to 1:1; width: left edge + right edge anchored, excess 4.3 % of the width taken from the left
```

The size is the output size in pixels. The reason lists, in this order and only what applies: the rotation (`rotated 0.54° (frame edges)`, `rotated 0.21° (film outline)`, `not rotated (abs angle 0.12° < 0.2°)`, `rotated pass uncertain, kept unrotated`), `bare light (no film) ignored for the film base`, `translucent holder strips removed (left 4.2 %, right 7.3 % of the image side)`, the format (`snapped to 3:2` or `no format (crop uncertain, full film area kept)`) and per axis which frame borders were anchored and where the excess was taken (`height: bottom edge anchored, excess 3.2 % of the height taken from the top`). Sizes in the reason are percent of the image side along that axis. The same text is written into the image description of the DNG, TIFF and JPEG after `crop: ` (e.g. in the exiftool `ImageDescription`; the degree sign appears as `deg` there).

## Commands and options

| Command / option | Description |
|------------------|-------------|
| `rfnegconv` | Without a command: process `Negative/` once (like `run`) |
| `rfnegconv run` | Process `Negative/` once |
| `rfnegconv watch` | Keep running and process new files (Ctrl+C ends) |
| `rfnegconv service install` | Install and start the background service |
| `rfnegconv service status` | Show whether the service is installed and running, the log file and which exiftool is used |
| `rfnegconv service uninstall` | Remove the background service |
| `rfnegconv config init --negative PATH --photos PATH --archive PATH` | Write a configuration with these folders only if none exists yet; create the configured folders; prints `config=`, `status=created\|kept`, `negative=`, `photos=`, `archive=` |
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

Global options (`--config`, `-Q`, `-v`, `-vv`) come before the command, e.g. `rfnegconv -v run --photos ~/Film/Fotos --no-dng`. Exit codes: 0 = everything done (also when the folder was busy), 1 = at least one file failed or configuration error.

## Supported cameras and formats

Everything LibRaw 0.22 reads, with the extensions `.arw .sr2 .raf .nef .nrw .cr2 .cr3 .orf .rw2 .pef .srw .dng`. The camera's sensor format does not matter: the frame on the film is detected.

## Troubleshooting

- **A file is in `Negative/_Fehler/`:** the `.txt` next to it gives the reason. After fixing the cause, move the RAW back into `Negative/`.
- **Nothing happens:** `rfnegconv service status` shows whether the service is running and where the log file is. Without the service: start `rfnegconv run` by hand.
- **Error message about the configuration:** it names the missing or wrong key and the path of the configuration file.
- **„Der Dienst verarbeitet gerade …“:** another run is working on the folder; try again later.
- **Pictures upside down or mirrored:** set `rotate` and/or `mirror` and process again.
- **Crop wrong:** in the DNG the crop can be reset in Lightroom/Camera Raw. `crop=uncertain` in the description means: the detection was not sure and used the whole film strip.
- **No camera data in the files:** exiftool is not installed or not found (warning in the log; `rfnegconv service status` shows the exiftool found). The lookup order is `exiftool_path`, then the `PATH`, then the installer's copy in the app data folder. Run the installer again, install exiftool or set `exiftool_path`.

Log files (`rfnegconv.log`, 5 files of 5 MB each in rotation; on macOS also `service.out.log`/`service.err.log` of the service):

| System | Folder |
|--------|--------|
| macOS | `~/Library/Logs/real-fast-negconv/` |
| Linux | `~/.local/state/real-fast-negconv/log/` |
| Windows | `%LOCALAPPDATA%\real-fast-negconv\Logs\` |

## Development

```bash
git clone git@github.com:jcmx9/real-fast-negconv.git
```

```bash
cd real-fast-negconv && uv sync
```

```bash
uv run ruff check --fix . && uv run ruff format . && uv run mypy src/
```

Development runs always use an isolated app folder so that a real installation stays untouched (configuration, logs, data, exiftool and service files then live below it; service commands such as `launchctl` are only printed, not run):

```bash
RFNEGCONV_HOME=.devhome uv run rfnegconv --help
```

The environment variable `RFNEGCONV_HOME` moves all program folders to `<RFNEGCONV_HOME>/config`, `log`, `data` and `service`. The folder `.devhome/` is excluded from Git. Never use `uv tool install` for development: it would overwrite a real installation.

The test suite is maintained separately and is not published; this repository contains only the source code.

## Versioning

This project uses [CalVer](https://calver.org/) in the format `YY.M.MICRO` (e.g. `26.10.6`); development versions carry `.devN`. Releases are made with [bump-my-version](https://github.com/callowayproject/bump-my-version) and `scripts/release.sh`.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). In short: branch from `dev`, commit with Conventional Commits, open a pull request against `dev`.

## Security

Please do **not** report security vulnerabilities via public issues. See [SECURITY.md](SECURITY.md).

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

## License

MIT, see [LICENSE](LICENSE).
