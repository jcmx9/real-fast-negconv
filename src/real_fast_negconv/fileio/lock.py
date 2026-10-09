"""Exclusive, non-blocking lock file so only one batch works on a folder."""

import errno
import logging
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

log = logging.getLogger(__name__)

LOCK_NAME = ".rfnegconv.lock"
_BUSY_ERRNOS = frozenset({errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK})


@contextmanager
def folder_lock(directory: Path) -> Iterator[bool]:
    """Hold `directory/.rfnegconv.lock`; yields False if another holder has it.

    Filesystems without lock support (some network shares) yield True with a
    warning: processing then works as it did without the lock.
    """
    fd = os.open(directory / LOCK_NAME, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        acquired = _acquire(fd)
        try:
            yield acquired
        finally:
            if acquired:
                _release(fd)
    finally:
        os.close(fd)


def _acquire(fd: int) -> bool:
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
        log.warning("Folder lock not supported here (%s); continuing without", exc)
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
