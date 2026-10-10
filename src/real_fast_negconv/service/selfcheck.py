"""Silent self-check before every run: only problems are reported.

Checks: the folders are reachable and writable, enough free space on the
drives of the Negative and photos folders, exiftool is found, new files in
`Negative/_Fehler` since the last check, and the background service matches
the `service` switch. The messages are plain German (dialog, notification).
"""

import errno
import json
import logging
import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from real_fast_negconv import paths
from real_fast_negconv.config import Config
from real_fast_negconv.exceptions import FolderError
from real_fast_negconv.fileio.atomic import atomic_write
from real_fast_negconv.fileio.exiftool import ExifTool
from real_fast_negconv.service import daemon
from real_fast_negconv.service.batch import ERROR_DIR, ensure_folder, folder_error
from real_fast_negconv.system import GIB

log = logging.getLogger(__name__)

LOW_SPACE_BYTES = 2 * GIB
GB = 1000**3  # the message shows decimal gigabytes, as file managers do
STATE_FILE_NAME = "selfcheck.json"

type DiskUsage = Callable[[Path], tuple[int, int, int]]


@dataclass(frozen=True)
class Problem:
    """One finding; `key` stays the same while the condition lasts.

    `fatal`: a folder cannot be used, a run cannot start.
    """

    key: str
    message: str
    fatal: bool = False


def state_path() -> Path:
    """File remembering the `_Fehler` files already reported."""
    return paths.data_dir() / STATE_FILE_NAME


def check_folders(cfg: Config) -> list[Problem]:
    """Each folder exists (or can be created) and is writable."""
    problems: list[Problem] = []
    for folder in cfg.require_dirs():
        try:
            ensure_folder(folder)
        except FolderError as exc:
            problems.append(Problem(f"folder:{folder}", str(exc), fatal=True))
            continue
        if not os.access(folder, os.W_OK):
            denied = PermissionError(errno.EACCES, "permission denied", str(folder))
            message = str(folder_error(folder, denied))
            problems.append(Problem(f"folder:{folder}", message, fatal=True))
    return problems


def check_space(cfg: Config, usage: DiskUsage = shutil.disk_usage) -> list[Problem]:
    """Warn below LOW_SPACE_BYTES on the drive of the Negative or photos folder."""
    negative, _archive, photos = cfg.require_dirs()
    problems: list[Problem] = []
    seen: set[int] = set()
    for folder in (negative, photos):
        try:
            device = folder.stat().st_dev
            free = usage(folder)[2]
        except OSError:
            continue  # unreachable folders are reported by check_folders
        if device in seen:
            continue
        seen.add(device)
        if free < LOW_SPACE_BYTES:
            amount = f"{free / GB:.1f}".replace(".", ",")
            problems.append(
                Problem(
                    f"space:{folder}",
                    f"Wenig Speicherplatz frei: {amount} GB auf dem Laufwerk "
                    f"mit dem Ordner „{folder.name}“.",
                )
            )
    return problems


def check_exiftool(cfg: Config) -> list[Problem]:
    if ExifTool.locate(cfg.exiftool_path).available:
        return []
    return [
        Problem(
            "exiftool",
            "exiftool wurde nicht gefunden – die Fotos bekommen keine Kameradaten.",  # noqa: RUF001  # German typographic dash is intended
        )
    ]


def check_service(
    cfg: Config, installed: Callable[[], bool] | None = None
) -> list[Problem]:
    """The background service is set up exactly when `service = true`."""
    have = (installed or daemon.installed)()
    if have == cfg.service:
        return []
    if cfg.service:
        message = (
            "Der Hintergrunddienst ist nicht eingerichtet, obwohl "
            "„service = true“ eingestellt ist."
        )
    else:
        message = (
            "Der Hintergrunddienst ist noch eingerichtet, obwohl "
            "„service = false“ eingestellt ist."
        )
    return [Problem("service", message)]


def _error_files(negative: Path) -> set[str] | None:
    """Files in `_Fehler` (reason files left out); None if it cannot be read."""
    folder = negative / ERROR_DIR
    try:
        if not folder.exists():
            return set()
        return {
            p.name
            for p in folder.iterdir()
            if p.is_file() and not p.name.startswith(".") and p.suffix != ".txt"
        }
    except OSError as exc:
        log.warning("Cannot list %s: %s", folder, exc)
        return None


def _load_reported(path: Path) -> set[str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    reported = data.get("reported") if isinstance(data, dict) else None
    if not isinstance(reported, list):
        return set()
    return {name for name in reported if isinstance(name, str)}


def _save_reported(path: Path, names: set[str]) -> None:
    text = json.dumps({"reported": sorted(names)}, ensure_ascii=False, indent=1)

    def write(tmp: Path) -> None:
        tmp.write_text(text, encoding="utf-8")

    try:
        atomic_write(path, write)
    except OSError as exc:
        log.warning("Cannot save the self-check state %s: %s", path, exc)


def remember_error_files(cfg: Config, state: Path | None = None) -> None:
    """Mark every file now in `_Fehler` as reported (shared by runs and service).

    Nothing is changed when the folder cannot be listed.
    """
    negative, _archive, _photos = cfg.require_dirs()
    current = _error_files(negative)
    if current is not None:
        _save_reported(state or state_path(), current)


def check_error_files(cfg: Config, state: Path | None = None) -> list[Problem]:
    """Files that arrived in `_Fehler` and were not reported yet.

    One record for single runs and the service: a file reported by one of
    them (in its result or by this check) is not reported by the other.
    """
    negative, _archive, _photos = cfg.require_dirs()
    current = _error_files(negative)
    if current is None:  # keep the record as it is
        return []
    path = state or state_path()
    new = sorted(current - _load_reported(path))
    _save_reported(path, current)
    if not new:
        return []
    count = len(new)
    files = "neue Datei" if count == 1 else "neue Dateien"
    return [
        Problem(
            "errors:" + "/".join(new),
            f"{count} {files} in {negative.name}/{ERROR_DIR} – der Grund steht "  # noqa: RUF001  # German typographic dash is intended
            "jeweils in der .txt-Datei daneben.",
        )
    ]


def self_check(
    cfg: Config, *, folders: bool = True, service: bool = True
) -> list[Problem]:
    """All checks; each problem is logged.

    `folders=False`: leave out the folder check (the service reports folder
    problems itself); `service=False`: leave out the service check (a run
    with another config file than the default one).
    """
    problems = check_folders(cfg) if folders else []
    problems += check_space(cfg)
    problems += check_exiftool(cfg)
    problems += check_error_files(cfg)
    if service:
        problems += check_service(cfg)
    for problem in problems:
        log.warning("Self-check: %s", problem.message)
    return problems


class ProblemNotifier:
    """Passes on each distinct problem once, until it is gone and comes back."""

    def __init__(self, show: Callable[[str], None]) -> None:
        self._show = show
        self._active: set[str] = set()

    def report(self, problems: list[Problem]) -> None:
        for problem in problems:
            if problem.key not in self._active:
                self._show(problem.message)
        self._active = {problem.key for problem in problems}
