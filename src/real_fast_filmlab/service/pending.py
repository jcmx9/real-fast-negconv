"""Markers for frames in work, so an interrupted run leaves no duplicates.

Outputs get their final names before the RAW is archived. If the process is
killed in between (update, logout, power loss), the RAW is still in Negative
and the next run would develop it again under a second name. A marker in the
app data folder names the outputs of each frame in work; the next batch
removes the outputs of every marked frame whose RAW is still waiting.
"""

import hashlib
import json
import logging
from collections.abc import Iterable
from pathlib import Path

from real_fast_filmlab import paths

log = logging.getLogger(__name__)

PENDING_DIR_NAME = "pending"


def pending_dir() -> Path:
    return paths.data_dir() / PENDING_DIR_NAME


def _marker(source: Path) -> Path:
    digest = hashlib.sha256(str(source).encode("utf-8", "surrogatepass")).hexdigest()
    return pending_dir() / f"{digest[:24]}.json"


def _identity(source: Path) -> tuple[int, int] | None:
    """Size and modification time: tells a file from another of its name."""
    try:
        stat = source.stat()
    except OSError:
        return None
    return stat.st_size, stat.st_mtime_ns


def mark(source: Path, outputs: Iterable[Path] = ()) -> None:
    """Record that `source` is in work; `outputs` are those written so far.

    The marker keeps the size and modification time of `source`: a later
    file of the same name is another picture, whose outputs are not ours.
    """
    identity = _identity(source)
    data: dict[str, object] = {
        "source": str(source),
        "outputs": [str(p) for p in outputs],
    }
    if identity is not None:
        data["size"], data["mtime_ns"] = identity
    _write(source, data)


def add(source: Path, output: Path) -> None:
    """Record that `output` was written for the marked `source`."""
    marker = _marker(source)
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
        data["outputs"] = [*data["outputs"], str(output)]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        log.debug("Cannot read the in-work marker for %s: %s", source.name, exc)
        return
    _write(source, data)


def _write(source: Path, data: dict[str, object]) -> None:
    marker = _marker(source)
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(json.dumps(data), encoding="utf-8")
    except OSError as exc:  # only a safety net: the frame is developed anyway
        log.debug("Cannot write the in-work marker for %s: %s", source.name, exc)


def clear(source: Path) -> None:
    """Forget the marker of `source` (frame finished, or its outputs removed)."""
    try:
        _marker(source).unlink(missing_ok=True)
    except OSError as exc:
        log.debug("Cannot remove the in-work marker for %s: %s", source.name, exc)


def recover(negative: Path, photos: Path) -> list[Path]:
    """Remove the outputs of interrupted frames of `negative`; returns them.

    Only markers of RAWs directly in `negative` are handled, and only outputs
    directly in `photos` are ever deleted. A marker whose RAW is gone (it was
    archived before the marker could be removed) is just forgotten, and so
    is one whose RAW is no longer the file it was written for (another size
    or modification time): the outputs then belong to another picture.
    """
    removed: list[Path] = []
    try:
        markers = sorted(pending_dir().glob("*.json"))
    except OSError:
        return removed
    for marker in markers:
        try:
            data = json.loads(marker.read_text(encoding="utf-8"))
            source = Path(data["source"])
            outputs = [Path(p) for p in data["outputs"]]
            identity = (data.get("size"), data.get("mtime_ns"))
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            log.debug("Unreadable in-work marker %s removed", marker.name)
            marker.unlink(missing_ok=True)
            continue
        if source.parent != negative:
            continue  # another Negative folder: its own batch handles it
        try:
            if source.is_file() and _identity(source) == identity:
                for output in outputs:
                    if output.parent == photos and output.is_file():
                        output.unlink()
                        removed.append(output)
                        log.info(
                            "Removed %s of an interrupted run; %s is developed again",
                            output.name,
                            source.name,
                        )
            marker.unlink(missing_ok=True)
        except OSError as exc:
            log.warning("Cannot clean up after an interrupted run: %s", exc)
    return removed
