# Contributing

Thanks for your interest. Workflow:

## Setup

```bash
git clone git@github.com:jcmx9/real-fast-negconv.git
cd real-fast-negconv
uv sync
uv run pre-commit install
```

## Isolated dev runs

All dev runs use their own app folder so a real installation is never touched: `RFNEGCONV_HOME=.devhome uv run rfnegconv ...` (config, logs, data, exiftool and service files live below it; service commands are printed, not executed). Never run `uv tool install` or the installed `rfnegconv` for development. `.devhome/` is gitignored.

## Workflow

1. Branch from `dev`: `git checkout -b feature/<short-desc> dev`
2. Implement + docs
3. `uv run ruff check --fix . && uv run ruff format .`
4. `uv run mypy src/`
5. Conventional Commit message (`feat: ...`, `fix: ...`)
6. PR targeting `dev`

The test suite is maintained separately and is not published; the maintainer runs it against your PR.

## Rules

- Every threshold is a named constant or config key and is documented in both READMEs; no learned or hidden parameters.
- Outputs must stay deterministic: the same inputs and configuration give bit-identical files.
- `README.md` (German) and `README.en.md` (English) must have identical content and structure; change both in the same commit.

## Manual Acceptance: Watch Mode on Windows

CI does not cover Windows. Before merging changes to `watcher.py`:

1. On a Windows machine, clone the repository, run `uv sync` and set `$env:RFNEGCONV_HOME = ".devhome"` (isolated app folder; never `uv tool install` over a real installation).
2. Write `.devhome\config\config.toml` with `negative_dir`, `archive_dir` and `photos_dir`.
3. Run: `uv run rfnegconv watch`
4. Drag a RAW into the Negative folder; verify that DNG, TIFF and JPEG appear in the photos folder and the RAW is moved to the archive.
5. Press Ctrl-C; verify clean shutdown.

## PR Checklist

- [ ] No lint errors (`uv run ruff check`, `uv run ruff format --check`)
- [ ] Type check passes (`uv run mypy src/`)
- [ ] Both READMEs updated and in sync (if behaviour or options changed)
- [ ] CHANGELOG updated under `[Unreleased]`
