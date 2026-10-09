"""Watch the Negative folder and run a batch once copying has settled."""

import logging
import threading
import time
from collections.abc import Callable
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.api import BaseObserver

from real_fast_negconv.config import Config
from real_fast_negconv.service.batch import BatchResult, list_inputs, run_batch

log = logging.getLogger(__name__)

RESCAN_SECONDS = 60.0  # safety net for dropped filesystem events
MIN_BACKOFF = 5.0
MAX_BACKOFF = 60.0


class _WakeHandler(FileSystemEventHandler):
    def __init__(self, wake: threading.Event) -> None:
        self._wake = wake

    def on_any_event(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._wake.set()


type Snapshot = dict[Path, tuple[int, int]]
type FileState = tuple[Path, int, int]


def _snapshot(files: list[Path]) -> Snapshot:
    """(size, mtime_ns) per file; files that cannot be opened yet are left out.

    On Windows a file that is still being copied cannot be opened for reading;
    leaving it out keeps the set unstable until the copy has finished.
    """
    states: Snapshot = {}
    for path in files:
        try:
            stat = path.stat()
            with open(path, "rb"):
                pass
        except FileNotFoundError:
            continue
        except OSError as exc:
            log.debug("%s not readable yet: %s", path.name, exc)
            continue
        states[path] = (stat.st_size, stat.st_mtime_ns)
    return states


def _make_snapshot(negative: Path) -> Callable[[], Snapshot]:
    """Snapshot callable that treats an unreadable folder as empty (warns once)."""
    warned = False

    def snapshot() -> Snapshot:
        nonlocal warned
        try:
            files = list_inputs(negative)
        except OSError as exc:
            if not warned:
                log.warning("Cannot read %s: %s", negative, exc)
                warned = True
            return {}
        warned = False
        return _snapshot(files)

    return snapshot


def wait_until_stable(
    snapshot: Callable[[], Snapshot],
    settle_seconds: float,
    *,
    stop: threading.Event,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    poll: float = 0.5,
) -> list[Path]:
    """Block until the file set, sizes and mtimes are unchanged for settle_seconds."""
    last = snapshot()
    stable_since = clock()
    while not stop.is_set():
        sleep(poll)
        current = snapshot()
        if current != last:
            last, stable_since = current, clock()
            continue
        if clock() - stable_since >= settle_seconds:
            return sorted(current)
    return []


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
        for path, _reason in result.failed:
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


def _start_observer(
    negative: Path, wake: threading.Event, stop: threading.Event, backoff: float
) -> BaseObserver | None:
    """Start watching `negative`; retry with backoff (folder missing, unmounted)."""
    while not stop.is_set():
        observer = Observer()
        try:
            negative.mkdir(parents=True, exist_ok=True)
            observer.schedule(_WakeHandler(wake), str(negative), recursive=False)
            observer.start()
        except OSError as exc:
            log.warning(
                "Cannot watch %s (%s); retrying in %.0f s", negative, exc, backoff
            )
            stop.wait(backoff)
            continue
        return observer
    return None


def watch(
    cfg: Config,
    *,
    stop: threading.Event | None = None,
    on_batch: Callable[[BatchResult], None] | None = None,
) -> None:
    """Run until `stop` is set (or Ctrl+C); one batch per quiet period."""
    negative, _, _ = cfg.require_dirs()
    stop = stop or threading.Event()
    wake = threading.Event()
    wake.set()  # process files that are already waiting
    backoff = min(MAX_BACKOFF, max(MIN_BACKOFF, cfg.settle_seconds))
    observer = _start_observer(negative, wake, stop, backoff)
    if observer is None:
        return
    log.info("Watching %s", negative)
    snapshot = _make_snapshot(negative)
    stuck = _StuckFiles()
    last_scan = time.monotonic()
    try:
        while not stop.is_set():
            woken = wake.wait(timeout=1.0)
            if not woken and time.monotonic() - last_scan < RESCAN_SECONDS:
                continue
            wake.clear()
            last_scan = time.monotonic()
            try:
                files = stuck.filter(
                    wait_until_stable(snapshot, cfg.settle_seconds, stop=stop)
                )
                if not files:
                    continue
                result = run_batch(cfg, files)
                if result.busy:
                    log.info("Folder busy (another run); retrying in %.0f s", backoff)
                    stop.wait(backoff)
                    wake.set()
                    continue
                stuck.remember(result)
                if on_batch is not None:
                    on_batch(result)
            except Exception:
                log.exception("Batch failed; retrying in %.0f s", backoff)
                stop.wait(backoff)
                wake.set()
    finally:
        observer.stop()
        observer.join()
