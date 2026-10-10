"""Batch orchestration: analyse every file, decide per roll, render, archive."""

import errno
import logging
import os
import secrets
import shutil
import stat
import sys
import threading
import time
from collections.abc import Callable, Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
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
from real_fast_negconv.exceptions import EncodeError, FolderError, RawLoadError
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
# leftovers of interrupted writes: ours (atomic_write, archive copy) and
# exiftool's -overwrite_original
STALE_TEMP_PATTERNS = (f".*{TEMP_MARKER}*", "*_exiftool_tmp")
DISK_FULL_ERRNOS = frozenset({errno.ENOSPC, getattr(errno, "EDQUOT", errno.ENOSPC)})
# copystat refused by file systems without permissions (FAT, some shares)
STAT_UNSUPPORTED_ERRNOS = frozenset(
    {errno.EPERM, errno.ENOTSUP, getattr(errno, "EOPNOTSUPP", errno.ENOTSUP)}
)
# OS errors behind an unreadable RAW that are not the file's fault
READ_ENVIRONMENT_ERRNOS = DISK_FULL_ERRNOS | {
    errno.EIO,
    errno.EACCES,
    errno.EPERM,
    errno.EROFS,
}
BUSY_MESSAGE = "Der Dienst verarbeitet gerade – bitte später erneut versuchen."  # noqa: RUF001  # German typographic dash is intended


@dataclass
class BatchResult:
    """Outcome of one batch; `busy` = skipped because another batch runs.

    `failed` lists every failure; `kept` the failed files left in Negative
    because the cause was not the file itself (disk full, permissions, memory),
    `problem` the plain German reason of the first of them and `stopped`
    whether a full disk ended the batch early (the rest stays untouched).
    """

    succeeded: list[Path] = field(default_factory=list)
    failed: list[tuple[Path, str]] = field(default_factory=list)
    busy: bool = False
    kept: list[Path] = field(default_factory=list)
    problem: str | None = None
    stopped: bool = False


def problem_message(result: BatchResult) -> str | None:
    """Plain German text about failures that were not the files' fault."""
    if result.problem is None:
        return None
    done = len(result.succeeded)
    photos = "Foto" if done == 1 else "Fotos"
    if result.stopped:
        return (
            f"{result.problem} Verarbeitung angehalten: {done} {photos} fertig, "
            "die übrigen Negative bleiben im Ordner „Negative“."
        )
    count = len(result.kept)
    noun = "Negativ bleibt" if count == 1 else "Negative bleiben"
    return (
        f"{result.problem} {count} {noun} unverändert im Ordner „Negative“; "
        f"{done} {photos} fertig."
    )


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


def _cause_chain(exc: BaseException) -> Iterator[BaseException]:
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def plain_reason(exc: BaseException) -> str:
    """Plain German explanation of a failure (cause chain included)."""
    for current in _cause_chain(exc):
        if isinstance(current, RawLoadError) and environment_failure(current) is None:
            return "Die Datei ist keine lesbare RAW-Datei oder beschädigt."
        if isinstance(current, MemoryError):
            return "Nicht genug Arbeitsspeicher frei."
        if isinstance(current, OSError):
            if current.errno in DISK_FULL_ERRNOS:
                return "Kein Speicherplatz mehr frei."
            if isinstance(current, PermissionError) or current.errno in (
                errno.EACCES,
                errno.EPERM,
            ):
                return "Keine Berechtigung zum Schreiben/Lesen."
            if current.errno == errno.EROFS:
                return "Der Ordner ist schreibgeschützt."
            if current.errno == errno.EIO:
                return "Lese- oder Schreibfehler – ist das Laufwerk noch angeschlossen?"  # noqa: RUF001  # German typographic dash is intended
    return "Unerwarteter Fehler."


def environment_failure(exc: BaseException) -> BaseException | None:
    """The cause of a failure that is not the file's fault, else None.

    The file's fault (it goes to _Fehler/): a RAW that cannot be decoded, an
    image that cannot be encoded, a failed analysis. Not the file's fault
    (it stays in Negative): running out of memory and OS errors such as disk
    full, no permission, a read-only or failing volume - also when they are
    the reason a RAW could not be read (EIO, EACCES, EPERM, EROFS, ENOSPC).
    """
    for current in _cause_chain(exc):
        if isinstance(current, EncodeError):
            return None
        if isinstance(current, RawLoadError):
            cause = current.__cause__
            if isinstance(cause, MemoryError) or (
                isinstance(cause, OSError) and cause.errno in READ_ENVIRONMENT_ERRNOS
            ):
                return cause
            return None
        if isinstance(current, OSError | MemoryError):
            return current
    return None


def folder_error(path: Path, exc: OSError) -> FolderError:
    """Plain German/English error for a folder the batch cannot use."""
    detail = exc.strerror or str(exc) or type(exc).__name__
    if exc.errno in DISK_FULL_ERRNOS:
        text = f"Kein Speicherplatz mehr frei: {path} (disk full)"
    elif isinstance(exc, PermissionError) or exc.errno in (errno.EACCES, errno.EPERM):
        text = f"Keine Berechtigung für den Ordner: {path} (permission denied)"
    elif exc.errno == errno.EROFS:
        text = f"Der Ordner ist schreibgeschützt: {path} (read-only)"
    else:
        text = (
            f"Ordner nicht erreichbar: {path} – ist das Laufwerk angeschlossen? "  # noqa: RUF001  # German typographic dash is intended
            f"(folder not reachable: {detail})"
        )
    return FolderError(text)


def ensure_folder(path: Path) -> None:
    """Create a missing configured folder, but never missing parent folders.

    A parent that does not exist usually means an unmounted drive: creating
    the tree would put the pictures on the system disk instead.
    """
    try:
        if path.is_dir():
            return
        if not path.parent.is_dir():
            raise FileNotFoundError(
                errno.ENOENT, "parent folder does not exist", str(path.parent)
            )
        path.mkdir(exist_ok=True)
    except OSError as exc:
        raise folder_error(path, exc) from exc


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
    """Delete leftovers of interrupted writes older than `max_age`.

    Matches `.<name>.tmp.<pid>.<token>...` (our temp files) and
    `<name>_exiftool_tmp` (exiftool killed while rewriting a file).
    """
    cutoff = time.time() - max_age
    for pattern in STALE_TEMP_PATTERNS:
        for path in directory.glob(pattern):
            try:
                if path.is_file() and path.stat().st_mtime < cutoff:
                    path.unlink()
                    log.info("Removed leftover temp file %s", path.name)
            except OSError as exc:
                log.warning("Cannot remove leftover temp file %s: %s", path.name, exc)


def move_to_archive(source: Path, archive: Path) -> Path:
    """Move `source` into `archive` under a free name; returns the new path.

    Within one drive this is a rename. Across drives the file is copied to a
    hidden temp name in `archive`, flushed, renamed to its final name and only
    then removed from its old place: an interrupted copy never leaves a
    partial file under the real name, and the original is never lost.
    """
    destination = unique_destination(archive, source.name)
    try:
        os.rename(source, destination)
        return destination
    except OSError:
        pass  # another drive (or rename refused): copy instead
    token = f"{os.getpid()}.{secrets.token_hex(4)}"
    tmp = archive / f".{source.name}{TEMP_MARKER}{token}"
    try:
        shutil.copyfile(source, tmp)  # contents only: the copy stays writable
        with tmp.open("rb+") as handle:
            os.fsync(handle.fileno())
        _copy_stat(source, tmp)
        destination = unique_destination(archive, source.name)
        os.replace(tmp, destination)
    except BaseException:
        _remove_file(tmp)
        raise
    try:
        _remove_file(source)
    except BaseException:
        _remove_file(destination)  # the original stays the only copy
        raise
    return destination


def _copy_stat(source: Path, target: Path) -> None:
    """Copy times and mode (read-only included) where the file system can.

    File systems without permissions (FAT, some network shares) refuse
    chmod; the copy is still complete, so that is only logged.
    """
    try:
        shutil.copystat(source, target)
    except OSError as exc:
        if exc.errno not in STAT_UNSUPPORTED_ERRNOS:
            raise
        log.debug("Times/permissions not copied to %s: %s", target.name, exc)


def _remove_file(path: Path) -> None:
    """Delete `path` if it exists, also when it is read-only on Windows.

    Windows refuses to delete a read-only file: the attribute is cleared
    only if it is set, and restored if the file still cannot be deleted.
    """
    try:
        path.unlink(missing_ok=True)
    except PermissionError:
        if sys.platform != "win32":
            raise
        mode = path.stat().st_mode
        if mode & stat.S_IWRITE:
            raise  # not read-only: something else holds the file
        path.chmod(mode | stat.S_IWRITE)
        try:
            path.unlink()
        except BaseException:
            path.chmod(mode)  # leave the file as it was
            raise


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
    Raises FolderError when a folder is missing (and cannot be created
    without creating its parents), unreachable or not writable.
    """
    negative, archive, photos = cfg.require_dirs()
    for directory in (negative, archive, photos):
        ensure_folder(directory)
    with ExitStack() as stack:
        try:
            acquired = stack.enter_context(folder_lock(negative))
        except OSError as exc:
            raise folder_error(negative, exc) from exc
        if not acquired:
            log.info("Another batch is processing %s; skipped", negative)
            return BatchResult(busy=True)
        remove_stale_temp_files(photos)
        remove_stale_temp_files(archive)
        try:
            # files listed before the lock was taken may be gone (another
            # batch's work)
            todo = (
                list_inputs(negative)
                if files is None
                else [p for p in files if p.exists()]
            )
        except OSError as exc:
            raise folder_error(negative, exc) from exc
        return _run_locked(cfg, negative, archive, photos, todo)
    raise AssertionError("unreachable")  # pragma: no cover


def _run_locked(
    cfg: Config,
    negative: Path,
    archive: Path,
    photos: Path,
    todo: list[Path],
) -> BatchResult:
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

    if result.stopped:
        return _finish_log(result)
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

    stop = threading.Event()  # set when a full disk ends the batch

    def finish(path: Path) -> str | None:
        if stop.is_set():
            return None  # left untouched in Negative
        description = render(
            path, analyses[path], decisions[path], cfg, outputs[path], exiftool
        )
        try:
            move_to_archive(path, archive)
        except BaseException:
            _remove_outputs(outputs[path])
            raise
        return description

    for path, rendered in _parallel(workers, finish, ordered):
        if isinstance(rendered, Exception):
            _record_failure(result, path, negative, rendered)
            if result.stopped:
                stop.set()
        elif rendered is not None:
            result.succeeded.append(path)
            log.info("OK %s - %s", path.name, rendered.split(CROP_REASON_MARKER)[0])
    return _finish_log(result)


def _finish_log(result: BatchResult) -> BatchResult:
    if result.stopped:
        log.error("Batch stopped: %s", result.problem)
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
    """Quarantine a bad file; leave it in place if the cause lies elsewhere."""
    reason = technical_reason(exc)
    result.failed.append((path, reason))
    cause = environment_failure(exc)
    if cause is not None:
        result.kept.append(path)
        if result.problem is None:
            result.problem = plain_reason(exc)
        if isinstance(cause, OSError) and cause.errno in DISK_FULL_ERRNOS:
            result.stopped = True
        log.error("FAILED %s - %s (left in %s)", path.name, reason, negative)
        return
    log.error("FAILED %s - %s", path.name, reason)
    try:
        quarantine(path, negative, exc)
    except Exception:  # one bad file must never stop the batch
        log.error("could not move %s to %s", path.name, ERROR_DIR, exc_info=True)


def _remove_outputs(outputs: OutputPaths) -> None:
    for target in (outputs.dng, outputs.tiff, outputs.jpeg):
        if target is not None:
            target.unlink(missing_ok=True)
