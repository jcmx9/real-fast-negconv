"""Watch the Negative folder and run a batch once copying has settled."""

import logging
import shutil
import threading
import time
from collections.abc import Callable
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.api import BaseObserver

from real_fast_filmlab.config import Config
from real_fast_filmlab.exceptions import FolderError
from real_fast_filmlab.service.batch import (
    BatchResult,
    ensure_folder,
    folder_error,
    list_inputs,
    run_batch,
    technical_reason,
)
from real_fast_filmlab.service.settle import (
    Snapshot,
    snapshot_files,
    wait_until_stable,
)

log = logging.getLogger(__name__)

RESCAN_SECONDS = 60.0  # safety net for dropped filesystem events
MIN_BACKOFF = 5.0
MAX_BACKOFF = 60.0
# after a full disk no new batch starts until space grows or this has passed
DISK_FULL_PAUSE = 600.0
# ... or until at least this much more space is free than at the stop
DISK_FULL_RESUME_BYTES = 1024**3


class _WakeHandler(FileSystemEventHandler):
    def __init__(self, wake: threading.Event) -> None:
        self._wake = wake

    def on_any_event(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._wake.set()


type FileState = tuple[Path, int, int]


def _make_snapshot(
    negative: Path, on_problem: Callable[[str], None] | None = None
) -> Callable[[], Snapshot]:
    """Snapshot callable that treats an unreadable folder as empty.

    The condition is logged and reported once until the folder is readable
    again.
    """
    warned = False

    def snapshot() -> Snapshot:
        nonlocal warned
        try:
            files = list_inputs(negative)
        except OSError as exc:
            if not warned:
                message = str(folder_error(negative, exc))
                log.warning("%s", message)
                if on_problem is not None:
                    on_problem(message)
                warned = True
            return {}
        warned = False
        return snapshot_files(files)

    return snapshot


def _state(path: Path) -> FileState | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return path, stat.st_size, stat.st_mtime_ns


class _StuckFiles:
    """Files that failed but stayed in place; skipped until they change."""

    def __init__(self) -> None:
        self._states: set[FileState] = set()

    def remember(self, result: BatchResult) -> None:
        """Mark the failed files; not those kept by a stopped batch.

        A full disk or a vanished folder/drive stopped it: those files are
        retried at the next batch (after a full disk: once the pause is over).
        """
        retry = set(result.kept) if result.stopped else set()
        for path, _reason in result.failed:
            if path in retry:
                continue
            state = _state(path)
            if state is not None and state not in self._states:
                self._states.add(state)
                log.warning(
                    "%s could not be processed or moved; skipped until it changes",
                    path.name,
                )

    def filter(self, files: list[Path]) -> list[Path]:
        current = {state for p in files if (state := _state(p)) is not None}
        self._states &= current  # forget files that changed or disappeared
        return [p for p in files if _state(p) not in self._states]


class _Reported:
    """A recurring condition is logged and reported once until it changes."""

    def __init__(self, on_problem: Callable[[str], None] | None) -> None:
        self._on_problem = on_problem
        self._last: str | None = None

    def is_new(self, key: str) -> bool:
        if key == self._last:
            return False
        self._last = key
        return True

    def problem(self, message: str, backoff: float) -> None:
        """Folder problem: log and notify once, then only at debug level."""
        if not self.is_new(message):
            log.debug("Still: %s", message)
            return
        log.error("%s; retrying every %.0f s", message, backoff)
        if self._on_problem is not None:
            self._on_problem(message)

    def clear(self) -> None:
        self._last = None


def _free_space(path: Path) -> int:
    return shutil.disk_usage(path).free


class _DiskFullPause:
    """No new batch after a full disk until 1 GiB more is free or time is up.

    Free space unknown (unreadable drive) counts as "no more space": then only
    the timer ends the pause.
    """

    def __init__(
        self,
        photos: Path,
        clock: Callable[[], float],
        disk_free: Callable[[Path], int],
    ) -> None:
        self._photos = photos
        self._clock = clock
        self._disk_free = disk_free
        self._since = clock()
        self._free = self._read_free()

    def _read_free(self) -> int | None:
        try:
            return self._disk_free(self._photos)
        except OSError as exc:
            log.debug("Free space of %s unknown: %s", self._photos, exc)
            return None

    def over(self) -> bool:
        if self._clock() - self._since >= DISK_FULL_PAUSE:
            return True
        if self._free is None:
            return False
        free = self._read_free()
        return free is not None and free >= self._free + DISK_FULL_RESUME_BYTES


def _start_observer(
    negative: Path,
    wake: threading.Event,
    stop: threading.Event,
    backoff: float,
    reported: _Reported,
) -> BaseObserver | None:
    """Start watching `negative`; retry with backoff (folder missing, unmounted)."""
    while not stop.is_set():
        observer = Observer()
        try:
            ensure_folder(negative)
            observer.schedule(_WakeHandler(wake), str(negative), recursive=False)
            observer.start()
        except FolderError as exc:
            reported.problem(str(exc), backoff)
        except OSError as exc:
            reported.problem(str(folder_error(negative, exc)), backoff)
        else:
            reported.clear()
            return observer
        stop.wait(backoff)
    return None


def _backoff(settle_seconds: float) -> float:
    """Wait before a new attempt: settle_seconds, limited to 5-60 s."""
    return min(MAX_BACKOFF, max(MIN_BACKOFF, settle_seconds))


def watch(
    cfg: Config,
    *,
    stop: threading.Event | None = None,
    on_batch: Callable[[BatchResult], None] | None = None,
    on_problem: Callable[[str], None] | None = None,
    before_batch: Callable[[], None] | None = None,
    after_batch: Callable[[], None] | None = None,
    current_config: Callable[[], Config] | None = None,
    stop_requested: Callable[[], bool] | None = None,
    clock: Callable[[], float] = time.monotonic,
    disk_free: Callable[[Path], int] = _free_space,
) -> None:
    """Run until `stop` is set (or Ctrl+C); one batch per quiet period.

    `on_batch` gets every batch result except a repeat of the previous
    batch's problem without any success (one notice per condition);
    `on_problem` gets a plain message once when a folder becomes unusable.
    `before_batch` runs right before each batch (self-check), `after_batch`
    after each batch that was not skipped as busy. `current_config` gives
    the config for each batch and each wait (re-read by the caller): its
    switches and `settle_seconds` apply from the next wait or batch on; the
    folders watched stay those of `cfg`. `stop_requested` is asked about
    once a second between batches: True ends the watch. A batch running when
    `stop` is set finishes the files in work and starts no further one.

    After a batch stopped by a full disk no new batch starts until the
    photos folder's drive has DISK_FULL_RESUME_BYTES more free space than
    then (`disk_free`) or
    DISK_FULL_PAUSE seconds have passed (`clock`).
    """
    negative, _, _ = cfg.require_dirs()
    stop = stop or threading.Event()
    wake = threading.Event()
    wake.set()  # process files that are already waiting
    backoff = _backoff(cfg.settle_seconds)
    reported = _Reported(on_problem)
    observer = _start_observer(negative, wake, stop, backoff, reported)
    if observer is None:
        return
    log.info("Watching %s", negative)
    snapshot = _make_snapshot(negative, on_problem)
    stuck = _StuckFiles()
    last_scan = time.monotonic()
    pause: _DiskFullPause | None = None
    try:
        while not stop.is_set():
            woken = wake.wait(timeout=1.0)
            if stop_requested is not None and stop_requested():
                log.info("Stop requested; watching ends")
                break
            if pause is not None:
                if not pause.over():
                    wake.clear()  # file events wait until the pause is over
                    continue
                log.info("Disk-full pause over; looking for files again")
                pause = None
                woken = True
            if not woken and time.monotonic() - last_scan < RESCAN_SECONDS:
                continue
            wake.clear()
            last_scan = time.monotonic()
            settle = (
                cfg if current_config is None else current_config()
            ).settle_seconds
            backoff = _backoff(settle)
            try:
                files = stuck.filter(wait_until_stable(snapshot, settle, stop=stop))
                if not files:
                    continue
                if before_batch is not None:
                    before_batch()
                batch_cfg = cfg if current_config is None else current_config()
                result = run_batch(batch_cfg, files, stop=stop)
                if result.busy:
                    log.info("Folder busy (another run); retrying in %.0f s", backoff)
                    stop.wait(backoff)
                    wake.set()
                    continue
                if after_batch is not None:
                    after_batch()
                stuck.remember(result)
                if result.stopped and result.disk_full:
                    pause = _DiskFullPause(
                        batch_cfg.require_dirs()[2], clock, disk_free
                    )
                    log.info(
                        "Disk full: no new batch for up to %.0f s or until "
                        "space is freed",
                        DISK_FULL_PAUSE,
                    )
                if result.problem is None:
                    reported.clear()
                elif not result.succeeded and not reported.is_new(result.problem):
                    log.debug("Same problem again: %s", result.problem)
                    continue
                if on_batch is not None:
                    on_batch(result)
            except FolderError as exc:
                reported.problem(str(exc), backoff)
                stop.wait(backoff)
                wake.set()
            except Exception as exc:
                if reported.is_new(technical_reason(exc)):
                    log.exception("Batch failed; retrying every %.0f s", backoff)
                else:
                    log.debug("Batch failed again: %s", exc)
                stop.wait(backoff)
                wake.set()
    finally:
        observer.stop()
        observer.join()
