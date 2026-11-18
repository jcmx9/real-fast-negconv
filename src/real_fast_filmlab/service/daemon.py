"""Install the watch-folder service: launchd, Windows startup folder, systemd user."""

import logging
import os
import plistlib
import shlex
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import typer

from real_fast_filmlab import paths
from real_fast_filmlab.exceptions import ServiceError
from real_fast_filmlab.fileio.lock import file_lock

log = logging.getLogger(__name__)

LABEL = "io.github.jcmx9.rffilmlab"
UNIT_NAME = "rffilmlab.service"
STARTUP_SCRIPT = "rffilmlab.vbs"
NO_SERVICE_ENV = "RFFILMLAB_NO_SERVICE"  # installer tests: never change the service
WATCHER_LOCK_NAME = "watcher.lock"  # held by the running watcher
WATCHER_STOP_NAME = "watcher.stop"  # asks the running watcher to end

type Runner = Callable[..., subprocess.CompletedProcess[Any]]


def _dry_run(command: list[str], **_: Any) -> subprocess.CompletedProcess[bytes]:
    """Stand-in runner for RFFILMLAB_HOME runs: report, never execute."""
    typer.echo(f"[{paths.HOME_ENV}] would run: {shlex.join(command)}")
    return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")


def _quiet_dry_run(command: list[str], **_: Any) -> subprocess.CompletedProcess[bytes]:
    """Dry run for automatic changes: only logged, never printed or executed."""
    log.info("[%s] would run: %s", paths.HOME_ENV, shlex.join(command))
    return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")


def _default_runner() -> Runner:
    """Real subprocess runner, except in an isolated RFFILMLAB_HOME run."""
    return _dry_run if paths.dev_home() is not None else subprocess.run


def watcher_lock_path() -> Path:
    """Lock file the running watcher holds: only one watcher per user."""
    return paths.data_dir() / WATCHER_LOCK_NAME


def stop_request_path() -> Path:
    """File that asks the running watcher to end after its current batch."""
    return paths.data_dir() / WATCHER_STOP_NAME


def watcher_running() -> bool:
    """True if a watcher holds its lock (unknown counts as not running)."""
    try:
        with file_lock(watcher_lock_path()) as free:
            return not free
    except OSError:
        return False


def request_stop() -> None:
    """Ask a running watcher to end (Windows has no service manager for it)."""
    path = stop_request_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("stop\n", encoding="utf-8")


def withdraw_stop() -> None:
    """Take back a stop request nobody has followed yet."""
    stop_request_path().unlink(missing_ok=True)


def service_command() -> list[str]:
    """Command line the service runs."""
    executable = shutil.which("rffilmlab")
    base = [executable] if executable else [sys.executable, "-m", "real_fast_filmlab"]
    return [*base, "-Q", "watch"]


def launchd_plist(command: list[str], log_dir: Path, path_env: str) -> bytes:
    return plistlib.dumps(
        {
            "Label": LABEL,
            "ProgramArguments": command,
            "RunAtLoad": True,
            "KeepAlive": {"SuccessfulExit": False},
            "ProcessType": "Adaptive",
            "EnvironmentVariables": {"PATH": path_env},
            "StandardOutPath": str(log_dir / "service.out.log"),
            "StandardErrorPath": str(log_dir / "service.err.log"),
        }
    )


def systemd_unit(command: list[str], path_env: str) -> str:
    # Escape % as %% in systemd ExecStart and Environment
    exec_start = shlex.join(command).replace("%", "%%")
    path_escaped = path_env.replace("%", "%%")
    return (
        "[Unit]\n"
        "Description=rffilmlab watch folder\n\n"
        "[Service]\n"
        f"ExecStart={exec_start}\n"
        f'Environment="PATH={path_escaped}"\n'
        "Restart=on-failure\n"
        "RestartSec=10\n\n"
        "[Install]\n"
        "WantedBy=default.target\n"
    )


def startup_vbs(command: list[str]) -> str:
    """VBScript that starts the command without a console window."""
    # Double embedded quotes in each part for VBScript string escaping
    line = " ".join(f'""{part.replace('"', '""')}""' for part in command)
    return (
        f'Set shell = CreateObject("WScript.Shell")\r\nshell.Run "{line}", 0, False\r\n'
    )


def install(
    *,
    log_dir: Path,
    platform: str = sys.platform,
    home: Path | None = None,
    runner: Runner | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    """Install and start the service."""
    runner = runner or _default_runner()
    command = service_command()
    path_env = os.environ.get("PATH", "")
    try:
        if platform == "darwin":
            target = _plist_path(home)
            target.parent.mkdir(parents=True, exist_ok=True)
            log_dir.mkdir(parents=True, exist_ok=True)
            target.write_bytes(launchd_plist(command, log_dir, path_env))
            domain = f"gui/{_uid()}"
            runner(
                ["launchctl", "bootout", domain, str(target)],
                check=False,
                capture_output=True,
            )
            # Retry bootstrap up to 3 times (may fail with I/O error after bootout)
            last_exc = None
            for attempt in range(3):
                try:
                    runner(
                        ["launchctl", "bootstrap", domain, str(target)],
                        check=True,
                        capture_output=True,
                    )
                    return f"Service installed and started ({target})."
                except subprocess.CalledProcessError as exc:
                    last_exc = exc
                    if attempt < 2:
                        sleep(0.1)
            # All retries failed; include stderr in error
            stderr_text = (
                last_exc.stderr.decode("utf-8", errors="replace")
                if last_exc and last_exc.stderr
                else "(no stderr)"
            )
            raise ServiceError(
                f"launchctl bootstrap failed: {stderr_text}"
            ) from last_exc
        if platform.startswith("linux"):
            target = _unit_path(home)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(systemd_unit(command, path_env), encoding="utf-8")
            runner(
                ["systemctl", "--user", "daemon-reload"],
                check=True,
                capture_output=True,
            )
            runner(
                ["systemctl", "--user", "enable", "--now", UNIT_NAME],
                check=True,
                capture_output=True,
            )
            runner(  # an update must replace a watcher that is already running
                ["systemctl", "--user", "restart", UNIT_NAME],
                check=True,
                capture_output=True,
            )
            return f"Service installed and started ({target})."
        if platform == "win32":
            target = _startup_path(home)
            target.parent.mkdir(parents=True, exist_ok=True)
            vbs_text = startup_vbs(command)
            target.write_bytes(vbs_text.encode("utf-16"))
            withdraw_stop()  # a watcher asked to end may simply go on
            if not watcher_running():  # never a second watcher beside it
                runner(["wscript", str(target)], check=False, capture_output=True)
            return (
                f"Service installed and started; it starts at every login ({target})."
            )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ServiceError(f"service installation failed: {exc}") from exc
    raise ServiceError(f"unsupported platform: {platform}")


def uninstall(
    *,
    platform: str = sys.platform,
    home: Path | None = None,
    runner: Runner | None = None,
) -> str:
    """Stop and remove the service."""
    runner = runner or _default_runner()
    try:
        if platform == "darwin":
            target = _plist_path(home)
            runner(
                ["launchctl", "bootout", f"gui/{_uid()}", str(target)],
                check=False,
                capture_output=True,
            )
            target.unlink(missing_ok=True)
            return "Service removed."
        if platform.startswith("linux"):
            runner(
                ["systemctl", "--user", "disable", "--now", UNIT_NAME],
                check=False,
                capture_output=True,
            )
            _unit_path(home).unlink(missing_ok=True)
            runner(
                ["systemctl", "--user", "daemon-reload"],
                check=False,
                capture_output=True,
            )
            return "Service removed."
        if platform == "win32":
            _startup_path(home).unlink(missing_ok=True)
            request_stop()
            return "Service removed; a running instance stops after its current batch."
    except OSError as exc:
        raise ServiceError(f"service removal failed: {exc}") from exc
    raise ServiceError(f"unsupported platform: {platform}")


def installed(*, platform: str = sys.platform, home: Path | None = None) -> bool:
    """True if the service file for this platform exists."""
    if platform == "darwin":
        return _plist_path(home).exists()
    if platform == "win32":
        return _startup_path(home).exists()
    return _unit_path(home).exists()


def reconcile(
    want: bool,
    *,
    log_dir: Path,
    platform: str = sys.platform,
    home: Path | None = None,
    runner: Runner | None = None,
) -> str | None:
    """Make the service follow the switch; returns what was done, or None.

    want and not installed: install and start; not want and installed:
    remove. In an isolated RFFILMLAB_HOME run nothing is executed (the
    commands are only logged); with RFFILMLAB_NO_SERVICE=1 (installer tests)
    nothing is changed at all.
    """
    if os.environ.get(NO_SERVICE_ENV) == "1":
        log.info("%s=1: background service left as it is", NO_SERVICE_ENV)
        return None
    if runner is None and paths.dev_home() is not None:
        runner = _quiet_dry_run
    have = installed(platform=platform, home=home)
    if want and not have:
        return install(log_dir=log_dir, platform=platform, home=home, runner=runner)
    if not want and have:
        return uninstall(platform=platform, home=home, runner=runner)
    return None


def status(
    *,
    platform: str = sys.platform,
    home: Path | None = None,
    runner: Runner | None = None,
) -> str:
    """Human-readable service state."""
    if runner is None and paths.dev_home() is not None:
        installed = {
            "darwin": _plist_path,
            "win32": _startup_path,
        }.get(platform, _unit_path)(home).exists()
        return (
            f"Service files found ({paths.HOME_ENV}: service commands are not run)."
            if installed
            else "Service not installed."
        )
    runner = runner or _default_runner()
    if platform == "darwin":
        if not _plist_path(home).exists():
            return "Service not installed."
        done = runner(
            ["launchctl", "print", f"gui/{_uid()}/{LABEL}"],
            check=False,
            capture_output=True,
            text=True,
        )
        return (
            "Service installed and running."
            if done.returncode == 0
            else "Service installed but not running."
        )
    if platform.startswith("linux"):
        if not _unit_path(home).exists():
            return "Service not installed."
        done = runner(
            ["systemctl", "--user", "is-active", UNIT_NAME],
            check=False,
            capture_output=True,
            text=True,
        )
        running = str(done.stdout).strip() == "active"
        return (
            "Service installed and running."
            if running
            else "Service installed but not running."
        )
    if platform == "win32":
        if _startup_path(home).exists():
            return "Service installed (starts at login)."
        return "Service not installed."
    raise ServiceError(f"unsupported platform: {platform}")


def _uid() -> int:
    return os.getuid()  # only reached on macOS


def _plist_path(home: Path | None, label: str = LABEL) -> Path:
    if home is None:
        isolated = paths.service_dir()
        if isolated is not None:
            return isolated / f"{label}.plist"
        home = Path.home()
    return home / "Library" / "LaunchAgents" / f"{label}.plist"


def _unit_path(home: Path | None, name: str = UNIT_NAME) -> Path:
    if home is None:
        isolated = paths.service_dir()
        if isolated is not None:
            return isolated / name
        home = Path.home()
    return home / ".config" / "systemd" / "user" / name


def _startup_path(home: Path | None, name: str = STARTUP_SCRIPT) -> Path:
    if home is None:
        isolated = paths.service_dir()
        if isolated is not None:
            return isolated / name
        home = Path.home()
    appdata = Path(os.environ.get("APPDATA", str(home / "AppData" / "Roaming")))
    return (
        appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / name
    )
