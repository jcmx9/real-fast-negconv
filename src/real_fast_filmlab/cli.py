"""Typer CLI entry point."""

import logging
import signal
import sys
import threading
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Annotated, Any, NoReturn

import typer

from real_fast_filmlab import __version__, config_file
from real_fast_filmlab.config import (
    DIR_FIELDS,
    Config,
    default_config_path,
    default_log_dir,
    load_config,
)
from real_fast_filmlab.config_file import SWITCHES
from real_fast_filmlab.exceptions import ConfigError, FolderError, RfFilmlabError
from real_fast_filmlab.fileio.exiftool import ExifTool
from real_fast_filmlab.fileio.lock import file_lock
from real_fast_filmlab.service import daemon, update
from real_fast_filmlab.service.batch import (
    BUSY_MESSAGE,
    BatchResult,
    problem_message,
    run_batch,
)
from real_fast_filmlab.service.notify import notify, summary_message
from real_fast_filmlab.service.render import CROP_DETAIL
from real_fast_filmlab.service.selfcheck import (
    ProblemNotifier,
    remember_error_files,
    self_check,
)
from real_fast_filmlab.service.watcher import watch as watch_folder

log = logging.getLogger(__name__)

LOG_FILE_NAME = "rffilmlab.log"  # background watcher (service)
RUN_LOG_FILE_NAME = "rffilmlab-run.log"  # single runs (launcher, terminal)
RUN_CHANNEL = "run"  # update notice: single runs
SERVICE_CHANNEL = "service"  # update notice: the background service
CONFIG_RETRY_SECONDS = 10.0  # background watcher: wait for a corrected config
# a watcher that was asked to end may still hold the lock for a moment
WATCHER_LOCK_ATTEMPTS = 10
WATCHER_LOCK_WAIT_SECONDS = 0.5
FOLDERS_CHANGED_MESSAGE = (
    "Die geänderten Ordner gelten erst nach einem Neustart des Dienstes – "  # noqa: RUF001  # German typographic dash is intended
    "bis dahin arbeitet er mit den bisherigen Ordnern weiter."
)

app = typer.Typer(
    name="rffilmlab",
    help=(
        f"RAW-Scans von Filmnegativen in DNG, TIFF und JPEG umwandeln (v{__version__})"
    ),
    add_completion=False,
)
service_app = typer.Typer(help="Den Hintergrunddienst verwalten.", no_args_is_help=True)
app.add_typer(service_app, name="service")
config_app = typer.Typer(
    help="Die Konfigurationsdatei verwalten.", no_args_is_help=True
)
app.add_typer(config_app, name="config")


@dataclass
class State:
    config_path: Path
    verbosity: int


def setup_logging(
    verbosity: int, log_dir: Path, file_name: str = RUN_LOG_FILE_NAME
) -> None:
    """File log always; console according to verbosity (0 = none).

    The watcher and single runs write separate files, so two processes never
    rotate the same file.
    """
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
    root.setLevel(logging.DEBUG)
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_dir / file_name,
            maxBytes=5_000_000,
            backupCount=5,
            encoding="utf-8",
        )
    except OSError as exc:
        typer.echo(f"Warnung: Kein Protokoll in {log_dir} möglich: {exc}", err=True)
    else:
        file_handler.setLevel(logging.DEBUG if verbosity >= 3 else logging.INFO)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
        )
        root.addHandler(file_handler)
    if verbosity >= 1:
        console = logging.StreamHandler(sys.stderr)
        console.setLevel(logging.DEBUG if verbosity >= 3 else logging.INFO)
        if verbosity < 2:  # the per-file crop reason starts at -v (the log has it)
            console.addFilter(lambda record: not hasattr(record, CROP_DETAIL))
        console.setFormatter(logging.Formatter("%(message)s"))
        root.addHandler(console)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"rffilmlab {__version__}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-V",
            callback=_version_callback,
            is_eager=True,
            help="Version anzeigen und beenden.",
        ),
    ] = False,
    config: Annotated[
        Path | None, typer.Option("--config", help="Pfad der Konfigurationsdatei.")
    ] = None,
    silent: Annotated[
        bool, typer.Option("--silent", "-Q", help="Keine Konsolenausgabe.")
    ] = False,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Mehr Ausgabe.")
    ] = False,
    debug: Annotated[
        bool, typer.Option("--debug", "-vv", help="Debug-Ausgabe.")
    ] = False,
) -> None:
    """Without a command: process everything in the Negative folder once."""
    verbosity = 0 if silent else (3 if debug else (2 if verbose else 1))
    state = State(
        config_path=config or default_config_path(),
        verbosity=verbosity,
    )
    ctx.obj = state
    if ctx.invoked_subcommand is None:
        _run(state, {})


@app.command(help="Alles im Eingangsordner einmal verarbeiten.")
def run(
    ctx: typer.Context,
    negative: Annotated[
        Path | None, typer.Option("--negative", help="Eingangsordner.")
    ] = None,
    archive: Annotated[
        Path | None, typer.Option("--archive", help="Archivordner.")
    ] = None,
    photos: Annotated[
        Path | None, typer.Option("--photos", help="Ausgabeordner.")
    ] = None,
    dng: Annotated[
        bool | None, typer.Option("--dng/--no-dng", help="DNG-Dateien schreiben.")
    ] = None,
    dng_finder_preview: Annotated[
        bool | None,
        typer.Option(
            "--dng-finder-preview/--no-dng-finder-preview",
            help="Größeres DNG schreiben, das Finder und Quick Look anzeigen.",
        ),
    ] = None,
    summary: Annotated[
        bool,
        typer.Option(
            "--summary",
            help=(
                "Für Starter: gibt die Zeile 'processed=<n> failed=<m> "
                "busy=<0|1>' aus; Exit-Code 1, wenn der Lauf nicht starten kann "
                "oder Dateien im Eingangsordner blieben (Speicher voll, "
                "Berechtigungen)."
            ),
        ),
    ] = False,
) -> None:
    """Process everything in the Negative folder once."""
    overrides = {
        "negative_dir": negative,
        "archive_dir": archive,
        "photos_dir": photos,
        "dng": dng,
        "dng_finder_preview": dng_finder_preview,
    }
    _run(ctx.obj, overrides, summary=summary)


@app.command(
    help=(
        "Weiterlaufen und neue Dateien verarbeiten, sobald sie eintreffen. "
        "Pro Benutzer läuft nur eine Überwachung; eine zweite endet sofort."
    )
)
def watch(ctx: typer.Context) -> None:
    """Keep running and process new files as they arrive.

    Only one watcher runs per user: a second one ends at once. With -Q (as
    the background service runs it) a broken config does not end it: it
    reports the problem once and waits for the corrected file. A termination
    request finishes the files in work first.
    """
    state: State = ctx.obj
    setup_logging(state.verbosity, default_log_dir(), LOG_FILE_NAME)
    stop = threading.Event()
    with _stop_on_terminate(stop), ExitStack() as stack:
        if not _hold_watcher_lock(stack, stop):
            log.info("Another watcher is already running; this one ends")
            if state.verbosity >= 1:
                typer.echo("Die automatische Verarbeitung läuft bereits.")
            return
        daemon.withdraw_stop()  # left over from a time when no watcher ran
        cfg = _load(state, {}) if state.verbosity >= 1 else _await_config(state, stop)
        if cfg is not None:
            _watch(state, cfg, stop)


def _watch(state: State, cfg: Config, stop: threading.Event) -> None:
    active = cfg  # the config of the next batch, re-read before each batch
    config_problem: str | None = None
    folders_changed = False  # told once until the file names the old ones again

    def on_problem(message: str) -> None:
        if active.notify:
            notify("rffilmlab", message)

    def reload() -> None:
        """Switches take effect at the next batch; a broken file keeps the last
        good config (reported once); folder changes need a restart (reported
        once)."""
        nonlocal active, config_problem, folders_changed
        try:
            fresh = load_config(state.config_path)
            fresh.require_dirs()
        except RfFilmlabError as exc:
            message = (
                "Konfiguration fehlerhaft – es gilt weiter die letzte gültige: "  # noqa: RUF001  # German typographic dash is intended
                f"{exc}"
            )
            if message != config_problem:
                config_problem = message
                log.error("%s (config file: %s)", message, state.config_path)
                on_problem(message)
            return
        config_problem = None
        changed = fresh.require_dirs() != cfg.require_dirs()
        if changed and not folders_changed:
            log.warning("Changed folders take effect when the service restarts")
            on_problem(FOLDERS_CHANGED_MESSAGE)
        folders_changed = changed
        if changed:
            fresh = fresh.model_copy(
                update={name: getattr(cfg, name) for name in DIR_FIELDS}
            )
        active = fresh

    notifier = ProblemNotifier(on_problem)

    def before_batch() -> None:
        reload()
        # folder problems are reported by the watcher itself
        notifier.report(self_check(active, folders=False))
        if active.update_check:
            latest = update.new_version(SERVICE_CHANNEL)
            if latest is not None and active.notify:  # told once it can be shown
                on_problem(update.notice(latest))
                update.mark_notified(SERVICE_CHANNEL, latest)

    def after_batch() -> None:
        remember_error_files(active)  # reported with the batch

    try:
        watch_folder(
            cfg,
            on_batch=lambda result: _report(
                active, state.verbosity, result, service=True
            ),
            on_problem=on_problem,
            before_batch=before_batch,
            after_batch=after_batch,
            current_config=lambda: active,
            stop=stop,
            stop_requested=_stop_requested,
        )
    except KeyboardInterrupt:
        log.info("Stopped.")
    except RfFilmlabError as exc:
        _fail(state, exc)


@contextmanager
def _stop_on_terminate(stop: threading.Event) -> Iterator[None]:
    """SIGTERM (service manager, logout) sets `stop` instead of killing."""
    try:
        previous = signal.signal(signal.SIGTERM, lambda *_: stop.set())
    except ValueError:  # not the main thread: signals cannot be handled here
        yield
        return
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous)


def _hold_watcher_lock(stack: ExitStack, stop: threading.Event) -> bool:
    """Take the watcher lock for the life of `stack`; False if another has it."""
    path = daemon.watcher_lock_path()
    for attempt in range(WATCHER_LOCK_ATTEMPTS):
        if attempt:
            stop.wait(WATCHER_LOCK_WAIT_SECONDS)
        attempt_stack = ExitStack()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            acquired = attempt_stack.enter_context(file_lock(path))
        except OSError as exc:
            log.warning("Watcher lock not available (%s); continuing without", exc)
            return True
        if acquired:
            stack.push(attempt_stack)
            return True
        attempt_stack.close()
        if stop.is_set():
            break
    return False


def _stop_requested() -> bool:
    """True once the service was switched off where no service manager stops it."""
    if not daemon.stop_request_path().exists():
        return False
    try:
        daemon.withdraw_stop()
    except OSError as exc:  # the request counts even if it cannot be removed
        log.warning("Stop request could not be removed: %s", exc)
    return True


def _await_config(state: State, stop: threading.Event) -> Config | None:
    """The config for the background watcher; waits while the file is broken.

    Ending with an error would only make the service manager restart the
    watcher forever. The problem is logged and notified once per message.
    """
    reported: str | None = None
    while not stop.is_set():
        try:
            cfg = load_config(state.config_path)
            cfg.require_dirs()
        except RfFilmlabError as exc:
            message = (
                "Konfiguration fehlerhaft – die automatische Verarbeitung "  # noqa: RUF001  # German typographic dash is intended
                f"wartet auf die Korrektur: {exc}"
            )
            if message != reported:
                reported = message
                log.error("%s (config file: %s)", message, state.config_path)
                notify("rffilmlab", message)
            stop.wait(CONFIG_RETRY_SECONDS)
            continue
        if reported is not None:
            log.info("Config is valid again; watching starts")
        return cfg
    return None


@service_app.command(
    "install", help="Die automatische Verarbeitung bei jeder Anmeldung starten."
)
def service_install() -> None:
    """Start the watch folder automatically at login."""
    _service(lambda: daemon.install(log_dir=default_log_dir()))


@service_app.command("uninstall", help="Den Hintergrunddienst entfernen.")
def service_uninstall() -> None:
    """Remove the background service."""
    _service(daemon.uninstall)


@service_app.command(
    "status", help="Zeigen, ob der Hintergrunddienst eingerichtet ist und läuft."
)
def service_status(
    ctx: typer.Context,
    summary: Annotated[
        bool,
        typer.Option(
            "--summary",
            help=(
                "Für Installer und Starter: gibt die Zeilen "
                "'service=<absent|installed|running|stopped>' und "
                "'exiftool=<Pfad oder leer>' aus."
            ),
        ),
    ] = False,
) -> None:
    """Show whether the background service is installed and running."""
    exiftool = _exiftool(ctx.obj)
    if summary:
        _service(lambda: f"service={daemon.state()}\nexiftool={exiftool or ''}")
        return
    found = exiftool or "nicht gefunden (die Fotos bekommen keine Kameradaten)"
    _service(
        lambda: (
            f"{daemon.status()}\nProtokoll: {default_log_dir() / LOG_FILE_NAME}"
            f"\nProtokoll der Einzelläufe: {default_log_dir() / RUN_LOG_FILE_NAME}"
            f"\nexiftool: {found}"
        )
    )


def _exiftool(state: State) -> Path | None:
    """The exiftool in use, or None."""
    try:
        configured = load_config(state.config_path).exiftool_path
    except RfFilmlabError:
        configured = None
    return ExifTool.locate(configured).executable


@config_app.command(
    "init",
    help=(
        "Die vollständige Konfigurationsdatei schreiben oder fehlende Schlüssel "
        "ergänzen und die Ordner anlegen. Vorhandene Werte bleiben, wie sie "
        "sind. Gibt Zeilen der Form schlüssel=wert aus (config, status, "
        "negative, photos, archive und jeden Schalter); status ist created, "
        "completed (Datei geändert) oder kept."
    ),
)
def config_init(
    ctx: typer.Context,
    negative: Annotated[Path, typer.Option("--negative", help="Eingangsordner.")],
    photos: Annotated[Path, typer.Option("--photos", help="Ausgabeordner.")],
    archive: Annotated[Path, typer.Option("--archive", help="Archivordner.")],
    off: Annotated[
        list[str] | None,
        typer.Option(
            "--off",
            help=(
                "Diesen Schalter auf false setzen (wiederholbar): "
                f"{', '.join(SWITCHES)}."
            ),
        ),
    ] = None,
    expert_reset: Annotated[
        bool,
        typer.Option(
            "--expert-reset",
            help="Jede Experten-Schwelle auf ihren Standardwert setzen.",
        ),
    ] = False,
) -> None:
    """Write the complete config (every key) or add missing keys; create folders.

    An existing config keeps its values; only keys it lacks are added (with
    their defaults) and the switches named with --off are set to false.
    --expert-reset sets every expert threshold to its default.
    Prints key=value lines (config, status, negative, photos, archive and
    every switch); status is created, completed (file changed) or kept.
    """
    state: State = ctx.obj
    path = state.config_path
    try:
        outcome = config_file.init_file(
            path,
            folders={
                "negative_dir": negative,
                "photos_dir": photos,
                "archive_dir": archive,
            },
            switches_off=tuple(off or ()),
            service_installed=daemon.installed,
            expert_reset=expert_reset,
        )
        negative_dir, archive_dir, photos_dir = outcome.config.require_dirs()
        for folder in (negative_dir, photos_dir, archive_dir):
            folder.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        _fail(state, ConfigError(f"Die Ordner lassen sich nicht anlegen: {exc}"))
    except RfFilmlabError as exc:
        _fail(state, exc)
    typer.echo(f"config={path}")
    typer.echo(f"status={outcome.status}")
    typer.echo(f"negative={negative_dir}")
    typer.echo(f"photos={photos_dir}")
    typer.echo(f"archive={archive_dir}")
    for name in SWITCHES:
        typer.echo(f"{name}={str(getattr(outcome.config, name)).lower()}")


def _service(action: Any) -> None:
    try:
        typer.echo(action())
    except RfFilmlabError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc


def _load(state: State, overrides: dict[str, Any]) -> Config:
    try:
        cfg = load_config(state.config_path).merge_overrides(overrides)
        cfg.require_dirs()
    except RfFilmlabError as exc:
        _fail(state, exc)
    return cfg


def _run(state: State, overrides: dict[str, Any], *, summary: bool = False) -> None:
    setup_logging(state.verbosity, default_log_dir())
    cfg = _load(state, overrides)
    # the service always uses the default config: only a run with that file
    # may change it
    default_config = _same_file(state.config_path, default_config_path())
    if default_config:
        sync_service(cfg)
    findings = self_check(cfg, service=default_config)
    for finding in findings:
        if finding.fatal:
            continue
        if summary:
            typer.echo(f"check={finding.message}")
        elif state.verbosity >= 1:
            typer.echo(finding.message, err=True)
    fatal = next((f for f in findings if f.fatal), None)
    if fatal is not None:
        _fail(state, FolderError(fatal.message))
    latest = update.new_version(RUN_CHANNEL) if cfg.update_check else None
    if latest is not None and (summary or state.verbosity >= 1):
        if summary:
            typer.echo(f"update={latest}")
        else:
            typer.echo(f"Neue Version {latest} verfügbar: {update.UPDATE_URL}")
        update.mark_notified(RUN_CHANNEL, latest)  # a silent run tells nobody
    try:
        result = run_batch(cfg)
    except RfFilmlabError as exc:
        _fail(state, exc)
    except OSError as exc:  # anything the batch did not classify itself
        _fail(state, FolderError(f"{exc.strerror or exc} ({exc.filename or '-'})"))
    remember_error_files(cfg)  # this run reports its own failures
    problem = problem_message(result)
    if summary:  # the launcher reports the outcome itself (dialog, no notification)
        if problem is not None:  # shown by the launcher instead of the counts
            _fail(state, FolderError(problem))
        for hint in result.hints:  # shown like the self-check findings
            typer.echo(f"check={hint}")
        typer.echo(summary_line(result))
        return
    if result.busy:
        if state.verbosity >= 1:
            typer.echo(BUSY_MESSAGE)
        return
    _report(cfg, state.verbosity, result)
    if result.failed:
        raise typer.Exit(1)


def _same_file(a: Path, b: Path) -> bool:
    try:
        return a.expanduser().resolve() == b.expanduser().resolve()
    except OSError:
        return False


def sync_service(cfg: Config) -> None:
    """Install or remove the background service so it follows `service`."""
    try:
        done = daemon.reconcile(cfg.service, log_dir=default_log_dir())
    except RfFilmlabError as exc:  # the self-check reports the mismatch
        log.warning("Background service not changed: %s", exc)
        return
    if done is not None:
        log.info("Background service (service = %s): %s", cfg.service, done)


def summary_line(result: BatchResult) -> str:
    """Machine-readable outcome of one run for the launchers."""
    return (
        f"processed={len(result.succeeded)} failed={len(result.failed)} "
        f"busy={int(result.busy)}"
    )


def _report(
    cfg: Config, verbosity: int, result: BatchResult, *, service: bool = False
) -> None:
    if verbosity >= 1:
        typer.echo(
            f"{len(result.succeeded)} umgewandelt, {len(result.failed)} fehlgeschlagen"
        )
        for path, reason in result.failed:
            typer.echo(f"  {path.name}: {reason}", err=True)
        problem = problem_message(result)
        if problem is not None:
            typer.echo(problem, err=True)
        for hint in result.hints:
            typer.echo(hint, err=True)
    if cfg.notify and (result.succeeded or result.failed):
        notify(*summary_message(result, service=service))


def _fail(state: State, exc: RfFilmlabError) -> NoReturn:
    typer.echo(f"Error: {exc}", err=True)
    typer.echo(f"Konfigurationsdatei: {state.config_path}", err=True)
    raise typer.Exit(1) from exc
