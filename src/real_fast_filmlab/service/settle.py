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
# A file that is being copied keeps the whole set waiting: the frames of a
# roll belong into one batch. Not for ever: after this time without the copy
# ending (a file that is locked for good) the others go on without it.
COPY_WAIT_SECONDS = 600.0
COPYING = (-1, -1)  # state of a file that is still being copied

type Snapshot = dict[Path, tuple[int, int]]


def finder_busy(stat: os.stat_result, platform: str = sys.platform) -> bool:
    """True for a file the macOS Finder is still copying (its busy date)."""
    if platform != "darwin":
        return False
    birth = getattr(stat, "st_birthtime", None)
    return birth is not None and FINDER_BUSY_DAY[0] <= birth <= FINDER_BUSY_DAY[1]


def snapshot_files(files: list[Path]) -> Snapshot:
    """(size, mtime_ns) per file; COPYING for a file still being copied.

    On Windows a file that is still being copied cannot be opened for reading;
    on macOS the Finder marks it with its busy date. Such a file is in the
    snapshot with the state COPYING (see `complete`). A file that cannot be
    read for another reason is left out.
    """
    states: Snapshot = {}
    for path in files:
        try:
            stat = path.stat()
        except OSError:
            continue  # gone
        if finder_busy(stat):
            log.debug("%s is still being copied by the Finder", path.name)
            states[path] = COPYING
            continue
        try:
            with open(path, "rb"):
                pass
        except FileNotFoundError:
            continue
        except OSError as exc:
            log.debug("%s not readable yet: %s", path.name, exc)
            if _may_be_copying(path):
                states[path] = COPYING
            continue
        states[path] = (stat.st_size, stat.st_mtime_ns)
    return states


def complete(snapshot: Snapshot) -> list[Path]:
    """The files of `snapshot` that are not being copied, sorted."""
    return sorted(path for path, state in snapshot.items() if state != COPYING)


def wait_until_stable(
    snapshot: Callable[[], Snapshot],
    settle_seconds: float,
    *,
    stop: threading.Event,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    poll: float = POLL_SECONDS,
) -> list[Path]:
    """Block until the file set, sizes and mtimes are unchanged for settle_seconds.

    While a file is being copied nothing counts as settled: the frames of a
    roll are developed together, and a batch that starts without the last
    ones has no roll to compare them with. A copy that has not ended after
    COPY_WAIT_SECONDS no longer holds the others back. Returns the complete
    files; those still being copied are left out.
    """
    last = snapshot()
    stable_since = clock()
    copying: frozenset[Path] = frozenset()
    copying_since = stable_since
    while not stop.is_set():
        sleep(poll)
        current = snapshot()
        now = clock()
        in_copy = frozenset(p for p, state in current.items() if state == COPYING)
        if in_copy != copying:  # another copy: its own time to end
            copying, copying_since = in_copy, now
        if current != last:
            last, stable_since = current, now
            continue
        if copying and now - copying_since < COPY_WAIT_SECONDS:
            stable_since = now  # the roll is not complete yet
            continue
        if now - stable_since >= settle_seconds:
            return complete(current)
    return []


def settled_files(
    list_files: Callable[[], list[Path]],
    settle_seconds: float,
    *,
    stop: threading.Event | None = None,
    now: Callable[[], float] = time.time,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> list[Path]:
    """The files that are complete, for a run that starts right away.

    Files untouched for settle_seconds and not marked as being copied are
    taken at once. If one was changed more recently (or is marked busy), a
    copy may still be going on: then the run waits until nothing has changed
    for settle_seconds, and for a file that is being copied until that has
    ended (at most COPY_WAIT_SECONDS; it is left out after that).
    """
    files = list_files()
    seen = snapshot_files(files)
    ready = set(complete(seen))
    current = now()
    fresh = any(
        abs(current - mtime_ns / 1e9) < settle_seconds
        for state in seen.values()
        if state != COPYING
        for mtime_ns in (state[1],)
    )
    if fresh or len(ready) < len(seen):
        log.info("Files are still arriving; waiting until copying has finished")
        stable = wait_until_stable(
            lambda: snapshot_files(list_files()),
            settle_seconds,
            stop=stop or threading.Event(),
            sleep=sleep,
            clock=clock,
            poll=min(POLL_SECONDS, settle_seconds / 2),
        )
        if stop is not None and stop.is_set():
            return []
        files, ready = list_files(), set(stable)
    # a file that cannot be read and is not being copied is the batch's
    # business: it reports the reason (no permission) and leaves it in place
    return sorted(p for p in files if p in ready or not _may_be_copying(p))


def _may_be_copying(path: Path, platform: str | None = None) -> bool:
    """True if `path` is unreadable because a copy may still be going on.

    The Finder's busy date says so on macOS; on Windows a file being copied
    cannot be opened, which no other system does. A vanished file is not
    waited for either.
    """
    try:
        stat = path.stat()
    except OSError:
        return False
    return finder_busy(stat) or (platform or sys.platform) == "win32"
