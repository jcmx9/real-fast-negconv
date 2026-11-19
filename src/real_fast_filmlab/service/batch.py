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

from real_fast_filmlab import paths
from real_fast_filmlab.config import Config
from real_fast_filmlab.core.analyzer import (
    EMPTY_LOOK_SAMPLE,
    FrameAnalysis,
    analyze,
)
from real_fast_filmlab.core.crossover import EMPTY_SAMPLE
from real_fast_filmlab.core.geometry import FrameGeometry
from real_fast_filmlab.core.metadata import CROP_REASON_MARKER
from real_fast_filmlab.core.rolls import (
    ExposureFinding,
    RollDecision,
    decide,
    exposure_findings,
    keystone_finding,
    roll_frames,
)
from real_fast_filmlab.exceptions import EncodeError, FolderError, RawLoadError
from real_fast_filmlab.fileio import flatfield, raw_loader
from real_fast_filmlab.fileio.atomic import TEMP_MARKER
from real_fast_filmlab.fileio.exiftool import ExifTool
from real_fast_filmlab.fileio.lock import folder_lock
from real_fast_filmlab.service import pending
from real_fast_filmlab.service.contact_sheet import write_contact_sheet
from real_fast_filmlab.service.render import OutputPaths, assign_outputs, render
from real_fast_filmlab.service.settle import settled_files
from real_fast_filmlab.system import automatic_workers

log = logging.getLogger(__name__)

ERROR_DIR = "_Fehler"
LOCK_DIR = "locks"  # app data: locks for folders whose drive cannot lock
STALE_TEMP_SECONDS = 3600.0
# leftovers of interrupted writes: ours (atomic_write, archive copy) and
# exiftool's -overwrite_original
STALE_TEMP_PATTERNS = (f".*{TEMP_MARKER}*", "*_exiftool_tmp")
DISK_FULL_ERRNOS = frozenset({errno.ENOSPC, getattr(errno, "EDQUOT", errno.ENOSPC)})
# copystat refused by file systems without permissions (FAT, some shares)
STAT_UNSUPPORTED_ERRNOS = frozenset(
    {errno.EPERM, errno.ENOTSUP, getattr(errno, "EOPNOTSUPP", errno.ENOTSUP)}
)
# the device behind a folder vanished (unplugged, unmounted): stops the batch
DEVICE_GONE_ERRNOS = frozenset(
    code
    for code in (getattr(errno, "ENXIO", None), getattr(errno, "ENODEV", None))
    if code is not None
)
# a file, folder or drive vanished while the batch ran: not the file's fault;
# a lone ENOENT stops the batch only if a configured folder is gone
DRIVE_GONE_ERRNOS = DEVICE_GONE_ERRNOS | {errno.ENOENT}
# OS errors behind an unreadable RAW that are not the file's fault
READ_ENVIRONMENT_ERRNOS = (
    DISK_FULL_ERRNOS
    | DRIVE_GONE_ERRNOS
    | {
        errno.EIO,
        errno.EACCES,
        errno.EPERM,
        errno.EROFS,
    }
)
DRIVE_GONE_REASON = (
    "Ordner oder Laufwerk nicht mehr erreichbar – "  # noqa: RUF001  # German typographic dash is intended
    "ist das Laufwerk angeschlossen?"
)
EXPOSURE_HINTS: dict[ExposureFinding, str] = {
    "under": (
        "Die Scans sind dunkel belichtet (der Filmrand nutzt weniger als ein "
        "Achtel des Sensorbereichs): länger belichten verringert das Bildrauschen."
    ),
    "over": (
        "Die Scans sind zu hell belichtet (der Filmrand ist übersteuert): "
        "kürzer belichten, sonst stimmen die Farben nicht."
    ),
}
KEYSTONE_HINT = (
    "Gegenüberliegende Bildkanten sind nicht parallel (um etwa {degrees:.1f}°): "
    "Die Kamera steht nicht genau senkrecht über dem Film."
)
# contact sheet: why a picture deserves a look
NOTE_CROP_UNCERTAIN = "Beschnitt unsicher"
NOTE_CROP_FROM_ROLL = "Beschnitt aus der Rolle"
NOTE_BASE_FROM_ROLL = "Filmbasis aus der Rolle"
BUSY_MESSAGE = "Der Dienst verarbeitet gerade – bitte später erneut versuchen."  # noqa: RUF001  # German typographic dash is intended


@dataclass
class BatchResult:
    """Outcome of one batch; `busy` = skipped because another batch runs.

    `failed` lists every failure; `kept` the failed files left in Negative
    because the cause was not the file itself (disk full, permissions, memory),
    `problem` the plain German reason of the first of them (of a vanished
    folder/drive, if that stopped the batch) and `stopped` whether a full disk
    or a vanished folder/drive ended the batch early (the rest stays
    untouched); `disk_full` tells a full disk apart. RAWs deleted mid-run are
    skipped and appear in none of the lists.
    `jpegs` are the JPEGs this batch wrote, `contact_sheets` its contact sheet(s).
    `hints` are plain German remarks about the scans as a whole (exposure);
    `notes` name, per JPEG, what the roll or an uncertain crop decided, for
    the contact sheet. `folder` is the name of the Negative folder as the
    messages show it.
    """

    succeeded: list[Path] = field(default_factory=list)
    failed: list[tuple[Path, str]] = field(default_factory=list)
    busy: bool = False
    kept: list[Path] = field(default_factory=list)
    problem: str | None = None
    stopped: bool = False
    disk_full: bool = False
    jpegs: list[Path] = field(default_factory=list)
    contact_sheets: list[Path] = field(default_factory=list)
    hints: list[str] = field(default_factory=list)
    notes: dict[Path, str] = field(default_factory=dict)
    folder: str = "Negative"


def problem_message(result: BatchResult) -> str | None:
    """Plain German text about failures that were not the files' fault."""
    if result.problem is None:
        return None
    done = len(result.succeeded)
    photos = "Foto" if done == 1 else "Fotos"
    if result.stopped:
        return (
            f"{result.problem} Verarbeitung angehalten: {done} {photos} fertig, "
            f"die übrigen Negative bleiben im Ordner „{result.folder}“."
        )
    count = len(result.kept)
    noun = "Negativ bleibt" if count == 1 else "Negative bleiben"
    return (
        f"{result.problem} {count} {noun} unverändert im Ordner „{result.folder}“; "
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
            if current.errno in DEVICE_GONE_ERRNOS:
                return DRIVE_GONE_REASON
            if current.errno == errno.EIO:
                return "Lese- oder Schreibfehler – ist das Laufwerk noch angeschlossen?"  # noqa: RUF001  # German typographic dash is intended
    return "Unerwarteter Fehler."


def environment_failure(exc: BaseException) -> BaseException | None:
    """The cause of a failure that is not the file's fault, else None.

    The file's fault (it goes to _Fehler/): a RAW that cannot be decoded, an
    image that cannot be encoded, a failed analysis. Not the file's fault
    (it stays in Negative): running out of memory and OS errors such as disk
    full, no permission, a read-only, failing or vanished volume - also when
    they are the reason a RAW could not be read (EIO, EACCES, EPERM, EROFS,
    ENOSPC, ENOENT, ENXIO, ENODEV).
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
    """Plain German error for a folder the batch cannot use.

    The question comes before the (possibly long) path, so a notification
    that cuts the text still shows it. The technical detail goes to the log.
    """
    log.debug("Folder %s unusable: %s", path, technical_reason(exc))
    if exc.errno in DISK_FULL_ERRNOS:
        text = f"Kein Speicherplatz mehr frei: {path}"
    elif isinstance(exc, PermissionError) or exc.errno in (errno.EACCES, errno.EPERM):
        text = f"Keine Berechtigung für den Ordner: {path}"
    elif exc.errno == errno.EROFS:
        text = f"Der Ordner ist schreibgeschützt: {path}"
    else:
        text = (
            "Ordner nicht erreichbar – ist das Laufwerk angeschlossen? "  # noqa: RUF001  # German typographic dash is intended
            f"({path})"
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
    """Move a failed file to _Fehler/ with a plain-language reason file.

    A vanished Negative folder is never re-created (FileNotFoundError).
    """
    error_dir = negative_dir / ERROR_DIR
    error_dir.mkdir(exist_ok=True)
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


def worker_count(requested: int, n_files: int) -> int:
    """Explicit request, else min(CPUs, half the RAM / 4 GiB, files)."""
    if requested > 0:
        return max(1, min(requested, n_files))
    return max(1, min(automatic_workers(), n_files))


def run_batch(
    cfg: Config,
    files: Sequence[Path] | None = None,
    *,
    stop: threading.Event | None = None,
) -> BatchResult:
    """Process `files` (default: everything in negative_dir) in two passes.

    Only one batch per Negative folder runs at a time (lock file); a second
    one returns at once with `busy=True` and touches nothing.
    Without `files` the batch takes the complete files only: while files are
    still being copied it waits until nothing has changed for
    `settle_seconds`. Outputs left by an interrupted run are removed first.
    Once `stop` is set no further file is started; the files in work are
    finished and the rest stays untouched in Negative.
    Raises FolderError when a folder is missing (and cannot be created
    without creating its parents), unreachable or not writable.
    """
    negative, archive, photos = cfg.require_dirs()
    for directory in (negative, archive, photos):
        ensure_folder(directory)
    with ExitStack() as stack:
        try:
            acquired = stack.enter_context(
                folder_lock(negative, fallback_dir=paths.data_dir() / LOCK_DIR)
            )
        except OSError as exc:
            raise folder_error(negative, exc) from exc
        if not acquired:
            log.info("Another batch is processing %s; skipped", negative)
            return BatchResult(busy=True)
        remove_stale_temp_files(photos)
        remove_stale_temp_files(archive)
        pending.recover(negative, photos)
        try:
            # files listed before the lock was taken may be gone (another
            # batch's work)
            todo = (
                settled_files(
                    lambda: list_inputs(negative), cfg.settle_seconds, stop=stop
                )
                if files is None
                else [p for p in files if p.exists()]
            )
        except OSError as exc:
            raise folder_error(negative, exc) from exc
        result = _run_locked(cfg, negative, archive, photos, todo, stop)
        result.folder = negative.name
        if cfg.contact_sheet and result.jpegs:
            try:
                write_contact_sheet(
                    result.jpegs,
                    photos,
                    written=result.contact_sheets,
                    notes=result.notes,
                )
            except Exception:  # the pictures are done; the sheet is an extra
                log.warning("Contact sheet could not be written", exc_info=True)
        return result
    raise AssertionError("unreachable")  # pragma: no cover


def _run_locked(
    cfg: Config,
    negative: Path,
    archive: Path,
    photos: Path,
    todo: list[Path],
    external_stop: threading.Event | None = None,
) -> BatchResult:
    result = BatchResult()
    if not todo:
        return result
    exiftool = ExifTool.locate(cfg.exiftool_path)
    if not exiftool.available:
        log.warning("exiftool not found - outputs will carry no camera metadata")
    workers = worker_count(cfg.parallel_jobs, len(todo))
    settings = cfg.analyzer_settings()
    folders = (negative, archive, photos)
    log.info("Analysing %d file(s) with %d worker(s)", len(todo), workers)
    # set when a full disk or a vanished folder ends the batch: the files not
    # started yet stay untouched in Negative
    stop = threading.Event()

    def halted() -> bool:
        return stop.is_set() or (external_stop is not None and external_stop.is_set())

    frames: dict[Path, FrameGeometry] = {}  # the roll's frame replaces the own

    def analyse(path: Path) -> FrameAnalysis | None:
        if halted():
            return None
        raw = raw_loader.load(path, half_size=True)
        flatfield.apply(raw, cfg.flatfield)
        return analyze(
            raw.rgb, settings, raw.xyz_to_cam, raw.exposure, frame=frames.get(path)
        )

    analyses: dict[Path, FrameAnalysis] = {}

    def analyse_all(paths: Sequence[Path]) -> None:
        for path, outcome in _parallel(workers, analyse, paths):
            if isinstance(outcome, Exception):
                analyses.pop(path, None)
                _record_failure(result, path, folders, outcome)
                if result.stopped:
                    stop.set()
            elif outcome is not None:
                analyses[path] = outcome

    analyse_all(todo)
    if result.stopped or halted():
        return _finish_log(result)
    ordered = [p for p in todo if p in analyses]
    roll_settings = cfg.roll_settings()
    fitted = roll_frames([analyses[p] for p in ordered], roll_settings)
    frames.update((p, frame) for p, frame in zip(ordered, fitted, strict=True) if frame)
    if frames:
        # white point, colour/BW, crossover and look belong to the final crop
        log.info("Measuring %d file(s) again in the roll's frame", len(frames))
        analyse_all(list(frames))
        if result.stopped or halted():
            return _finish_log(result)
        ordered = [p for p in ordered if p in analyses]
    decisions = dict(
        zip(
            ordered,
            decide(
                [analyses[p] for p in ordered],
                roll_settings,
                [frames.get(p) for p in ordered],
            ),
            strict=True,
        )
    )
    result.hints = [
        EXPOSURE_HINTS[finding]
        for finding in exposure_findings(
            [analyses[p] for p in ordered], [decisions[p] for p in ordered]
        )
    ]
    keystone = keystone_finding([analyses[p] for p in ordered])
    if keystone is not None:
        result.hints.append(KEYSTONE_HINT.format(degrees=keystone))
    for hint in result.hints:
        log.warning("%s", hint)
    # the crossover and look samples are only needed by decide
    analyses = {
        p: replace(a, density_sample=EMPTY_SAMPLE, look_sample=EMPTY_LOOK_SAMPLE)
        for p, a in analyses.items()
    }
    outputs = dict(
        zip(
            ordered,
            assign_outputs([p.stem for p in ordered], photos, cfg.dng, cfg.tiff),
            strict=True,
        )
    )

    def finish(path: Path) -> str | None:
        if halted():
            return None  # left untouched in Negative
        # writing into a vanished folder would recreate it (on the system
        # disk instead of the unplugged drive)
        for folder in folders:
            if not folder.is_dir():
                raise FileNotFoundError(
                    errno.ENOENT, "folder or drive gone", str(folder)
                )
        targets = outputs[path]
        pending.mark(path, _output_files(targets))
        try:
            description = render(
                path, analyses[path], decisions[path], cfg, targets, exiftool
            )
            try:
                move_to_archive(path, archive)
            except BaseException:
                _remove_outputs(targets)
                raise
        except BaseException:
            if not _outputs_left(targets):
                pending.clear(path)  # nothing left that a later run must remove
            raise
        pending.clear(path)
        return description

    for path, rendered in _parallel(workers, finish, ordered):
        if isinstance(rendered, Exception):
            _record_failure(result, path, folders, rendered)
            if result.stopped:
                stop.set()
        elif rendered is not None:
            result.succeeded.append(path)
            result.jpegs.append(outputs[path].jpeg)
            note = _review_note(analyses[path], decisions[path])
            if note:
                result.notes[outputs[path].jpeg] = note
            log.info("OK %s - %s", path.name, rendered.split(CROP_REASON_MARKER)[0])
    return _finish_log(result)


def _review_note(analysis: FrameAnalysis, decision: RollDecision) -> str:
    """What the contact sheet says under a picture worth checking, or ""."""
    parts: list[str] = []
    if decision.geometry is not None:
        parts.append(NOTE_CROP_FROM_ROLL)
    elif not analysis.geometry.confident:
        parts.append(NOTE_CROP_UNCERTAIN)
    if decision.fallback_applied:
        parts.append(NOTE_BASE_FROM_ROLL)
    return ", ".join(parts)


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
    result: BatchResult, path: Path, folders: Sequence[Path], exc: Exception
) -> None:
    """Quarantine a bad file; leave it in place if the cause lies elsewhere.

    `folders` are negative, archive and photos. A full disk, a vanished
    device (ENXIO, ENODEV) or a configured folder that is no longer a
    directory stops the batch (a vanished folder or device: with the drive
    message as `problem`). A RAW that no longer exists while all folders are
    there (deleted mid-run) is skipped: neither failed nor kept.
    """
    negative = folders[0]
    reason = technical_reason(exc)
    folder_gone = _folder_gone(folders)
    cause = environment_failure(exc)
    if cause is None and folder_gone:
        # whatever failed, it failed while a folder or drive was gone: not the
        # file's fault, and _Fehler must not be created in place of the drive
        cause = exc
    errno_ = cause.errno if isinstance(cause, OSError) else None
    if errno_ == errno.ENOENT and not folder_gone and not path.exists():
        log.info("SKIPPED %s - no longer in %s", path.name, negative)
        return
    result.failed.append((path, reason))
    if cause is not None:
        result.kept.append(path)
        if result.stopped:
            pass  # the first stop cause wins: problem and disk_full stay
        elif errno_ in DISK_FULL_ERRNOS:
            result.stopped = result.disk_full = True
        elif errno_ in DEVICE_GONE_ERRNOS or folder_gone:
            result.stopped = True
            result.problem = DRIVE_GONE_REASON  # the reason the batch stopped
        if result.problem is None:
            result.problem = plain_reason(exc)
        log.error("FAILED %s - %s (left in %s)", path.name, reason, negative)
        return
    log.error("FAILED %s - %s", path.name, reason)
    try:
        quarantine(path, negative, exc)
    except Exception:  # one bad file must never stop the batch
        log.error("could not move %s to %s", path.name, ERROR_DIR, exc_info=True)


def _folder_gone(folders: Sequence[Path]) -> bool:
    """True if one of the configured folders is no longer a directory."""
    return any(not folder.is_dir() for folder in folders)


def _output_files(outputs: OutputPaths) -> list[Path]:
    return [
        target
        for target in (outputs.dng, outputs.tiff, outputs.jpeg)
        if target is not None
    ]


def _outputs_left(outputs: OutputPaths) -> bool:
    """True if an output still exists, or that cannot be told (drive gone)."""
    try:
        return any(target.exists() for target in _output_files(outputs))
    except OSError:
        return True


def _remove_outputs(outputs: OutputPaths) -> None:
    for target in _output_files(outputs):
        target.unlink(missing_ok=True)
