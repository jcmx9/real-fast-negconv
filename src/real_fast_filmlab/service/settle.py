"""Settle gate: tell RAW files that are still being copied from finished ones."""

import logging
import os
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path

log = logging.getLogger(__name__)

# macOS Finder gives a file it is still copying the creation date 1984-01-24
# ("busy" date); such a file is not ready, however long its size stays put.
FINDER_BUSY_DAY = (443750400 - 43200, 443750400 + 86400 + 43200)  # UTC, +-12 h
POLL_SECONDS = 0.5

type Snapshot = dict[Path, tuple[int, int]]


def finder_busy(stat: os.stat_result, platform: str = sys.platform) -> bool:
    """True for a file the macOS Finder is still copying (its busy date)."""
    if platform != "darwin":
        return False
    birth = getattr(stat, "st_birthtime", None)
    return birth is not None and FINDER_BUSY_DAY[0] <= birth <= FINDER_BUSY_DAY[1]


def snapshot_files(files: list[Path]) -> Snapshot:
    """(size, mtime_ns) per file; files still being copied are left out.

    On Windows a file that is still being copied cannot be opened for reading;
    on macOS the Finder marks it with its busy date. Leaving such files out
    keeps the set unstable until the copy has finished.
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
        if finder_busy(stat):
            log.debug("%s is still being copied by the Finder", path.name)
            continue
        states[path] = (stat.st_size, stat.st_mtime_ns)
    return states


def wait_until_stable(
    snapshot: Callable[[], Snapshot],
    settle_seconds: float,
    *,
    stop: threading.Event,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    poll: float = POLL_SECONDS,
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


def settled_files(
    list_files: Callable[[], list[Path]],
    settle_seconds: float,
    *,
    stop: threading.Event | None = None,
    now: Callable[[], float] = time.time,
    sleep: Callable[[float], None] = time.sleep,
) -> list[Path]:
    """The files that are complete, for a run that starts right away.

    Files untouched for settle_seconds and not marked as being copied are
    taken at once. If one was changed more recently (or is marked busy), a
    copy may still be going on: then the run waits until nothing has changed
    for settle_seconds. Files still being copied after that are left out.
    """
    files = list_files()
    ready = snapshot_files(files)
    current = now()
    fresh = any(
        abs(current - mtime_ns / 1e9) < settle_seconds for _, mtime_ns in ready.values()
    )
    waiting = [p for p in files if p not in ready and _may_be_copying(p)]
    if fresh or waiting:
        log.info("Files are still arriving; waiting until copying has finished")
        stable = wait_until_stable(
            lambda: snapshot_files(list_files()),
            settle_seconds,
            stop=stop or threading.Event(),
            sleep=sleep,
            poll=min(POLL_SECONDS, settle_seconds / 2),
        )
        if stop is not None and stop.is_set():
            return []
        files, ready = list_files(), dict.fromkeys(stable, (0, 0))
    # a file that cannot be read and is not being copied is the batch's
    # business: it reports the reason (no permission) and leaves it in place
    return sorted(p for p in files if p in ready or not _may_be_copying(p))


def _may_be_copying(path: Path, platform: str = sys.platform) -> bool:
    """True if `path` is unreadable because a copy may still be going on.

    The Finder's busy date says so on macOS; on Windows a file being copied
    cannot be opened, which no other system does. A vanished file is not
    waited for either.
    """
    try:
        stat = path.stat()
    except OSError:
        return False
    return finder_busy(stat) or platform == "win32"
