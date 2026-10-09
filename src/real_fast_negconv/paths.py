"""Per-user app locations; the only module that talks to platformdirs.

When the environment variable ``RFNEGCONV_HOME`` is set (non-empty), every
location resolves under that folder instead of the real user directories, so
development and test runs cannot touch an installed copy of the program.
"""

import os
from pathlib import Path

import platformdirs

APP_NAME = "real-fast-negconv"
HOME_ENV = "RFNEGCONV_HOME"


def dev_home() -> Path | None:
    """Isolated app root from RFNEGCONV_HOME, or None for a normal run."""
    value = os.environ.get(HOME_ENV, "").strip()
    return Path(value).expanduser().resolve() if value else None


def config_dir() -> Path:
    """Folder of the config file."""
    root = dev_home()
    if root is not None:
        return root / "config"
    return Path(platformdirs.user_config_dir(APP_NAME, appauthor=False))


def log_dir() -> Path:
    """Folder of the log files."""
    root = dev_home()
    if root is not None:
        return root / "log"
    return Path(platformdirs.user_log_dir(APP_NAME, appauthor=False))


def data_dir() -> Path:
    """App data folder (private exiftool)."""
    root = dev_home()
    if root is not None:
        return root / "data"
    return Path(platformdirs.user_data_dir(APP_NAME, appauthor=False))


def service_dir() -> Path | None:
    """Folder for the service files under RFNEGCONV_HOME, else None."""
    root = dev_home()
    return root / "service" if root is not None else None
