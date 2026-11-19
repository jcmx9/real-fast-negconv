"""Atomic file writes and names that are taken exclusively, never replaced."""

import errno
import os
import secrets
from collections.abc import Callable, Iterator
from pathlib import Path

TEMP_MARKER = ".tmp."


def candidate_names(directory: Path, name: str) -> Iterator[Path]:
    """`directory/name`, then `stem_2.ext`, `stem_3.ext`, ..."""
    yield directory / name
    stem, suffix = Path(name).stem, Path(name).suffix
    n = 2
    while True:
        yield directory / f"{stem}_{n}{suffix}"
        n += 1


def claim(path: Path) -> bool:
    """Create `path` as an empty file; False if the name is taken.

    The check and the creation are one step of the file system (O_EXCL), so
    two processes never both get the name.
    """
    try:
        os.close(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644))
    except FileExistsError:
        return False
    return True


def claim_free_name(directory: Path, name: str) -> Path:
    """Reserve the first free of `name`, `stem_2.ext`, ...: an empty file."""
    for candidate in candidate_names(directory, name):
        if claim(candidate):
            return candidate
    raise AssertionError("unreachable")  # pragma: no cover


def place_exclusive(source: Path, target: Path) -> None:
    """Give the finished file `source` the name `target`, never replacing one.

    FileExistsError if `target` exists; `source` then stays. A hard link is
    exclusive by itself; where the file system has none (exFAT, some
    shares), the name is reserved first and the reservation replaced.
    Both files must be on one drive.
    """
    try:
        os.link(source, target)
    except FileExistsError:
        raise
    except OSError:
        if not claim(target):
            raise FileExistsError(
                errno.EEXIST, os.strerror(errno.EEXIST), str(target)
            ) from None
        try:
            os.replace(source, target)
        except BaseException:
            target.unlink(missing_ok=True)  # give the reserved name back
            raise
        return
    source.unlink()


def atomic_write(
    path: Path,
    write: Callable[[Path], None],
    *,
    create_parents: bool = True,
    exclusive: bool = False,
) -> None:
    """Call `write(tmp)` and move the result to `path`; never leave partial files.

    The temp name carries pid and a random token, so concurrent writers never
    share a temp file: `.<stem>.tmp.<pid>.<token><suffix>`. The temp file is
    flushed to the disk before it gets its name: after a power failure the
    name never stands for an empty file. With `create_parents=False` a
    missing folder is never created (outputs: a vanished folder or drive
    must not reappear on another disk); the write then fails with
    FileNotFoundError. With `exclusive` an existing `path` is never replaced
    (FileExistsError), whoever created it in the meantime.
    """
    if create_parents:
        path.parent.mkdir(parents=True, exist_ok=True)
    token = f"{os.getpid()}.{secrets.token_hex(4)}"
    tmp = path.with_name(f".{path.stem}{TEMP_MARKER}{token}{path.suffix}")
    try:
        write(tmp)
        _flush(tmp)
        if exclusive:
            place_exclusive(tmp, path)
        else:
            os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _flush(path: Path) -> None:
    """Force the file's data to the disk."""
    with path.open("rb+") as handle:
        os.fsync(handle.fileno())
