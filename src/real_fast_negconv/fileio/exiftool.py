"""Thin wrapper around the external exiftool binary (optional at runtime)."""

import logging
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from real_fast_negconv import paths

log = logging.getLogger(__name__)

TIMEOUT_SECONDS = 300


def copy_command(executable: Path, source: Path, target: Path) -> list[str]:
    """exiftool arguments copying all metadata except tags we set ourselves."""
    return [
        str(executable),
        "-q",
        "-q",
        "-overwrite_original",
        "-TagsFromFile",
        str(source),
        "-all:all",
        "--MakerNotes",
        "--Orientation",
        "--ImageDescription",
        "--Software",
        "--ImageWidth",
        "--ImageHeight",
        "--XMP-crs:all",
        "-ThumbnailImage=",
        "-PreviewImage=",
        "-Orientation#=1",
        str(target),
    ]


def private_exiftool_path(platform: str = sys.platform) -> Path:
    """Where the installer puts its own exiftool (app data dir)."""
    data_dir = paths.data_dir()
    name = "exiftool.exe" if platform == "win32" else "exiftool"
    return data_dir / "exiftool" / name


class ExifTool:
    """Read camera names and copy EXIF; silently degrades when not installed."""

    def __init__(self, executable: Path | None) -> None:
        self.executable = executable

    @classmethod
    def locate(cls, configured: Path | None = None) -> "ExifTool":
        """Use the configured binary, else PATH, else the installer's copy."""
        if configured is not None:
            return cls(configured if configured.is_file() else None)
        found = shutil.which("exiftool")
        if found:
            return cls(Path(found))
        private = private_exiftool_path()
        return cls(private if private.is_file() else None)

    @property
    def available(self) -> bool:
        return self.executable is not None

    def camera_name(self, source: Path) -> str | None:
        """'<Make> <Model>' of a file, or None."""
        if self.executable is None:
            return None
        try:
            done = subprocess.run(
                [str(self.executable), "-s3", "-Make", "-Model", str(source)],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=TIMEOUT_SECONDS,
            )
        except Exception as exc:  # best effort: metadata must never fail a file
            log.warning("exiftool could not read %s: %s", source.name, exc)
            return None
        name = " ".join(
            line.strip() for line in done.stdout.splitlines() if line.strip()
        )
        return name or None

    def copy_metadata(self, source: Path, targets: Sequence[Path]) -> bool:
        """Copy metadata from `source` into every target; False if any failed."""
        if self.executable is None:
            return False
        ok = True
        for target in targets:
            try:
                subprocess.run(
                    copy_command(self.executable, source, target),
                    check=True,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=TIMEOUT_SECONDS,
                )
            except Exception as exc:  # best effort: metadata must never fail a file
                log.warning("exiftool failed for %s: %s", target.name, exc)
                ok = False
        return ok
