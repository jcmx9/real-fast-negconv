"""Update notice: at most once per week ask GitHub for the latest release.

One HTTPS GET to api.github.com (the latest release of the project); nothing
else is sent. Offline or any error: no notice, no error. Each channel (single
runs, service) is told about a new version only once. Never updates itself.
"""

import json
import logging
import re
import time
from collections.abc import Callable
from http.client import HTTPException
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from real_fast_negconv import __version__, paths
from real_fast_negconv.fileio.atomic import atomic_write

log = logging.getLogger(__name__)

API_URL = "https://api.github.com/repos/jcmx9/real-fast-negconv/releases/latest"
UPDATE_URL = "https://github.com/jcmx9/real-fast-negconv#update"
CHECK_INTERVAL_SECONDS = 7 * 24 * 3600
TIMEOUT_SECONDS = 5.0
STATE_FILE_NAME = "update-check.json"
VERSION_PATTERN = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:\.dev(\d+))?$")

type Fetch = Callable[[], str | None]


def state_path() -> Path:
    return paths.data_dir() / STATE_FILE_NAME


def version_key(text: str) -> tuple[int, int, int, int, int] | None:
    """Sortable CalVer key; a .devN version sorts before its release."""
    match = VERSION_PATTERN.match(text.strip())
    if match is None:
        return None
    year, month, micro, dev = match.groups()
    released = (1, 0) if dev is None else (0, int(dev))
    return (int(year), int(month), int(micro), *released)


def is_newer(latest: str, installed: str = __version__) -> bool:
    new, old = version_key(latest), version_key(installed)
    return new is not None and old is not None and new > old


def fetch_latest() -> str | None:
    """Tag of the latest release without the leading "v", None on any failure."""
    request = Request(
        API_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"real-fast-negconv/{__version__}",
        },
    )
    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            data: Any = json.loads(response.read())
    except (OSError, ValueError, HTTPException) as exc:  # offline, timeout, bad reply
        log.info("Update check not possible: %s", exc)
        return None
    tag = data.get("tag_name") if isinstance(data, dict) else None
    if not isinstance(tag, str) or version_key(tag) is None:
        log.info("Update check: no usable release tag")
        return None
    return tag.strip().removeprefix("v")


def _load(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save(path: Path, data: dict[str, Any]) -> None:
    text = json.dumps(data, indent=1)

    def write(tmp: Path) -> None:
        tmp.write_text(text, encoding="utf-8")

    try:
        atomic_write(path, write)
    except OSError as exc:
        log.warning("Cannot save the update-check state %s: %s", path, exc)


def new_version(
    channel: str,
    *,
    fetch: Fetch | None = None,
    now: Callable[[], float] = time.time,
    state: Path | None = None,
) -> str | None:
    """A newer version not yet told to `channel`, else None.

    GitHub is asked at most once per CHECK_INTERVAL_SECONDS (a failed attempt
    counts too); the answer is shared by all channels.
    """
    path = state or state_path()
    data = _load(path)
    checked_at = data.get("checked_at")
    current = now()
    if not isinstance(checked_at, int | float) or not (
        0 <= current - checked_at < CHECK_INTERVAL_SECONDS
    ):
        data["checked_at"] = current
        latest = (fetch or fetch_latest)()
        if latest is not None:
            data["latest"] = latest
        _save(path, data)
    latest = data.get("latest")
    if not isinstance(latest, str) or not is_newer(latest):
        return None
    notified = data.get("notified")
    if not isinstance(notified, dict):
        notified = {}
    if notified.get(channel) == latest:
        return None
    notified[channel] = latest
    data["notified"] = notified
    _save(path, data)
    log.info("New version %s available (installed %s)", latest, __version__)
    return latest


def notice(version: str) -> str:
    """German text of the service notification."""
    return (
        f"Neue Version {version} verfügbar – siehe Update-Abschnitt "  # noqa: RUF001  # German typographic dash is intended
        "auf der Projektseite"
    )
