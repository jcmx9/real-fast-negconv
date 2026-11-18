"""Atomic file writes: temp file next to the target, then rename."""

import os
import secrets
from collections.abc import Callable
from pathlib import Path

TEMP_MARKER = ".tmp."


def atomic_write(
    path: Path, write: Callable[[Path], None], *, create_parents: bool = True
) -> None:
    """Call `write(tmp)` and move the result to `path`; never leave partial files.

    The temp name carries pid and a random token, so concurrent writers never
    share a temp file: `.<stem>.tmp.<pid>.<token><suffix>`. With
    `create_parents=False` a missing folder is never created (outputs: a
    vanished folder or drive must not reappear on another disk); the write
    then fails with FileNotFoundError.
    """
    if create_parents:
        path.parent.mkdir(parents=True, exist_ok=True)
    token = f"{os.getpid()}.{secrets.token_hex(4)}"
    tmp = path.with_name(f".{path.stem}{TEMP_MARKER}{token}{path.suffix}")
    try:
        write(tmp)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
