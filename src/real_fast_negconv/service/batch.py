"""Batch orchestration: analyse every file, decide per roll, render, archive."""

import errno
import logging
import os
import shutil
import sys
import time
from collections.abc import Callable, Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path

from real_fast_negconv.config import Config
from real_fast_negconv.core.analyzer import (
    EMPTY_LOOK_SAMPLE,
    FrameAnalysis,
    analyze,
)
from real_fast_negconv.core.crossover import EMPTY_SAMPLE
from real_fast_negconv.core.metadata import CROP_REASON_MARKER
from real_fast_negconv.core.rolls import decide
from real_fast_negconv.exceptions import RawLoadError
from real_fast_negconv.fileio import raw_loader
from real_fast_negconv.fileio.atomic import TEMP_MARKER
from real_fast_negconv.fileio.exiftool import ExifTool
from real_fast_negconv.fileio.lock import folder_lock
from real_fast_negconv.service.render import OutputPaths, assign_outputs, render

log = logging.getLogger(__name__)

ERROR_DIR = "_Fehler"
GIB = 1024**3
MEMORY_PER_WORKER = 4 * GIB
STALE_TEMP_SECONDS = 3600.0
BUSY_MESSAGE = "Der Dienst verarbeitet gerade – bitte später erneut versuchen."  # noqa: RUF001  # German typographic dash is intended


@dataclass
class BatchResult:
    """Outcome of one batch; `busy` = skipped because another batch runs."""

    succeeded: list[Path] = field(default_factory=list)
    failed: list[tuple[Path, str]] = field(default_factory=list)
    busy: bool = False


def list_inputs(negative_dir: Path) -> list[Path]:
    """RAW files directly in `negative_dir`; hidden/AppleDouble files ignored."""
    return sorted(
        p
        for p in negative_dir.iterdir()
        if p.is_file()
        and not p.name.startswith(".")
        and p.suffix.lower() in raw_loader.RAW_EXTENSIONS
    )


def unique_destination(directory: Path, name: str) -> Path:
    """`directory/name`, or `stem_2.ext`, `stem_3.ext`, ... if taken."""
    candidate = directory / name
    stem, suffix = Path(name).stem, Path(name).suffix
    n = 2
    while candidate.exists():
        candidate = directory / f"{stem}_{n}{suffix}"
        n += 1
    return candidate


def technical_reason(exc: BaseException) -> str:
    """Exception text for logs and the technical line of the reason file."""
    return str(exc) or type(exc).__name__


def plain_reason(exc: BaseException) -> str:
    """Plain German explanation of a failure (cause chain included)."""
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, RawLoadError):
            return "Die Datei ist keine lesbare RAW-Datei oder beschädigt."
        if isinstance(current, OSError):
            if current.errno == errno.ENOSPC:
                return "Kein Speicherplatz mehr frei."
            if isinstance(current, PermissionError) or current.errno in (
                errno.EACCES,
                errno.EPERM,
            ):
                return "Keine Berechtigung zum Schreiben/Lesen."
        current = current.__cause__ or current.__context__
    return "Unerwarteter Fehler."


def quarantine(path: Path, negative_dir: Path, exc: BaseException) -> Path:
    """Move a failed file to _Fehler/ with a plain-language reason file."""
    error_dir = negative_dir / ERROR_DIR
    error_dir.mkdir(parents=True, exist_ok=True)
    destination = unique_destination(error_dir, path.name)
    shutil.move(path, destination)
    destination.with_name(destination.name + ".txt").write_text(
        f"{path.name} konnte nicht verarbeitet werden.\n"
        f"Grund: {plain_reason(exc)}\n"
        f"Technisch: {technical_reason(exc)}\n"
        f"Zeitpunkt: {datetime.now():%Y-%m-%d %H:%M}\n",
        encoding="utf-8",
    )
    return destination


def remove_stale_temp_files(
    directory: Path, max_age: float = STALE_TEMP_SECONDS
) -> None:
    """Delete `.*.tmp.*` leftovers of interrupted writes older than `max_age`."""
    cutoff = time.time() - max_age
    for path in directory.glob(f".*{TEMP_MARKER}*"):
        try:
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink()
                log.info("Removed leftover temp file %s", path.name)
        except OSError as exc:
            log.warning("Cannot remove leftover temp file %s: %s", path.name, exc)


def total_memory_bytes() -> int:
    """Physical memory, or 8 GiB when the OS does not tell us."""
    if sys.platform == "win32":
        return _windows_total_memory() or 8 * GIB
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (AttributeError, ValueError, OSError):
        return 8 * GIB


def _windows_total_memory() -> int | None:
    """Total physical memory via GlobalMemoryStatusEx, None on failure."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    class MemoryStatusEx(ctypes.Structure):
        _fields_ = (
            ("dwLength", wintypes.DWORD),
            ("dwMemoryLoad", wintypes.DWORD),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        )

    status = MemoryStatusEx()
    status.dwLength = ctypes.sizeof(MemoryStatusEx)
    try:
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return None
    except (AttributeError, OSError):
        return None
    return int(status.ullTotalPhys)


def worker_count(requested: int, n_files: int) -> int:
    """Explicit request, else min(CPUs, half the RAM / 4 GiB, files)."""
    if requested > 0:
        return max(1, min(requested, n_files))
    by_memory = max(1, int(total_memory_bytes() * 0.5 // MEMORY_PER_WORKER))
    return max(1, min(os.cpu_count() or 1, by_memory, n_files))


def run_batch(cfg: Config, files: Sequence[Path] | None = None) -> BatchResult:
    """Process `files` (default: everything in negative_dir) in two passes.

    Only one batch per Negative folder runs at a time (lock file); a second
    one returns at once with `busy=True` and touches nothing.
    """
    negative, archive, photos = cfg.require_dirs()
    for directory in (negative, archive, photos):
        directory.mkdir(parents=True, exist_ok=True)
    with folder_lock(negative) as acquired:
        if not acquired:
            log.info("Another batch is processing %s; skipped", negative)
            return BatchResult(busy=True)
        remove_stale_temp_files(photos)
        return _run_locked(cfg, negative, archive, photos, files)


def _run_locked(
    cfg: Config,
    negative: Path,
    archive: Path,
    photos: Path,
    files: Sequence[Path] | None,
) -> BatchResult:
    # files listed before the lock was taken may be gone (another batch's work)
    todo = list_inputs(negative) if files is None else [p for p in files if p.exists()]
    result = BatchResult()
    if not todo:
        return result
    exiftool = ExifTool.locate(cfg.exiftool_path)
    if not exiftool.available:
        log.warning("exiftool not found - outputs will carry no camera metadata")
    workers = worker_count(cfg.parallel_jobs, len(todo))
    settings = cfg.analyzer_settings()
    log.info("Analysing %d file(s) with %d worker(s)", len(todo), workers)

    def analyse(path: Path) -> FrameAnalysis:
        raw = raw_loader.load(path, half_size=True)
        return analyze(raw.rgb, settings, raw.xyz_to_cam)

    analyses: dict[Path, FrameAnalysis] = {}
    for path, outcome in _parallel(workers, analyse, todo):
        if isinstance(outcome, Exception):
            _record_failure(result, path, negative, outcome)
        else:
            analyses[path] = outcome

    ordered = [p for p in todo if p in analyses]
    decisions = dict(
        zip(
            ordered,
            decide([analyses[p] for p in ordered], cfg.roll_settings()),
            strict=True,
        )
    )
    # the crossover and look samples are only needed by decide
    analyses = {
        p: replace(a, density_sample=EMPTY_SAMPLE, look_sample=EMPTY_LOOK_SAMPLE)
        for p, a in analyses.items()
    }
    outputs = dict(
        zip(
            ordered,
            assign_outputs([p.stem for p in ordered], photos, cfg.dng),
            strict=True,
        )
    )

    def finish(path: Path) -> str:
        description = render(
            path, analyses[path], decisions[path], cfg, outputs[path], exiftool
        )
        try:
            shutil.move(path, unique_destination(archive, path.name))
        except Exception:
            _remove_outputs(outputs[path])
            raise
        return description

    for path, rendered in _parallel(workers, finish, ordered):
        if isinstance(rendered, Exception):
            _record_failure(result, path, negative, rendered)
        else:
            result.succeeded.append(path)
            log.info("OK %s - %s", path.name, rendered.split(CROP_REASON_MARKER)[0])
    log.info(
        "Batch finished: %d ok, %d failed", len(result.succeeded), len(result.failed)
    )
    return result


def _parallel[T, R](
    workers: int, fn: Callable[[T], R], items: Sequence[T]
) -> Iterator[tuple[T, R | Exception]]:
    def safe(item: T) -> R | Exception:
        try:
            return fn(item)
        except Exception as exc:  # isolate per-file failures; logged by the caller
            log.debug("failure while processing %s", item, exc_info=True)
            return exc

    if workers <= 1:
        for item in items:
            yield item, safe(item)
        return
    with ThreadPoolExecutor(max_workers=workers) as pool:
        yield from zip(items, pool.map(safe, items), strict=True)


def _record_failure(
    result: BatchResult, path: Path, negative: Path, exc: Exception
) -> None:
    reason = technical_reason(exc)
    result.failed.append((path, reason))
    log.error("FAILED %s - %s", path.name, reason)
    try:
        quarantine(path, negative, exc)
    except Exception:  # one bad file must never stop the batch
        log.error("could not move %s to %s", path.name, ERROR_DIR, exc_info=True)


def _remove_outputs(outputs: OutputPaths) -> None:
    for target in (outputs.dng, outputs.tiff, outputs.jpeg):
        if target is not None:
            target.unlink(missing_ok=True)
