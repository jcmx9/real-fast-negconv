"""Exclusive, non-blocking lock file so only one batch works on a folder."""

import errno
import hashlib
import logging
import os
import sys
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path

log = logging.getLogger(__name__)

LOCK_NAME = ".rffilmlab.lock"
_BUSY_ERRNOS = frozenset({errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK})


@contextmanager
def folder_lock(directory: Path, fallback_dir: Path | None = None) -> Iterator[bool]:
    """Hold `directory/.rffilmlab.lock`; yields False if another holder has it.

    On a file system without lock support (some network shares) the lock is
    taken in `fallback_dir` instead, in a file named after the folder: runs
    on this computer still exclude each other. Without `fallback_dir`, or if
    that cannot be used either, it yields True with a warning: processing
    then works without a lock.
    """
    with _lock(directory / LOCK_NAME) as acquired:
        if acquired is not None:
            yield acquired
            return
    with ExitStack() as stack:
        held = True
        if fallback_dir is None:
            log.warning("No folder lock for %s; continuing without", directory)
        else:
            name = hashlib.sha256(str(directory).encode()).hexdigest()[:16]
            try:
                fallback_dir.mkdir(parents=True, exist_ok=True)
                held = stack.enter_context(file_lock(fallback_dir / f"{name}.lock"))
            except OSError as exc:
                log.warning(
                    "No folder lock for %s (%s); continuing without", directory, exc
                )
        yield held


@contextmanager
def file_lock(path: Path) -> Iterator[bool]:
    """Hold the lock file `path`; yields False if another holder has it.

    A file system without lock support yields True.
    """
    with _lock(path) as acquired:
        yield acquired is not False


@contextmanager
def _lock(path: Path) -> Iterator[bool | None]:
    """True: held; False: another holder has it; None: locks unsupported."""
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        acquired = _acquire(fd)
        try:
            yield acquired
        finally:
            if acquired:
                _release(fd)
    finally:
        os.close(fd)


def _acquire(fd: int) -> bool | None:
    try:
        if sys.platform == "win32":
            import msvcrt

            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        if exc.errno in _BUSY_ERRNOS:
            return False
        log.info("File locks not supported here (%s)", exc)
        return None
    return True


def _release(fd: int) -> None:
    try:
        if sys.platform == "win32":
            import msvcrt

            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        log.debug("releasing folder lock failed", exc_info=True)
