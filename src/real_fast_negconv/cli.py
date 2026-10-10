"""Typer CLI entry point."""

import logging
import sys
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Annotated, Any, NoReturn

import typer

from real_fast_negconv import __version__, config_file
from real_fast_negconv.config import (
    DIR_FIELDS,
    Config,
    default_config_path,
    default_log_dir,
    load_config,
)
from real_fast_negconv.config_file import SWITCHES
from real_fast_negconv.exceptions import ConfigError, FolderError, RfNegconvError
from real_fast_negconv.fileio.exiftool import ExifTool
from real_fast_negconv.service import daemon, update
from real_fast_negconv.service.batch import (
    BUSY_MESSAGE,
    BatchResult,
    problem_message,
    run_batch,
)
from real_fast_negconv.service.notify import notify, summary_message
from real_fast_negconv.service.render import CROP_DETAIL
from real_fast_negconv.service.selfcheck import (
    ProblemNotifier,
    remember_error_files,
    self_check,
)
from real_fast_negconv.service.watcher import watch as watch_folder

log = logging.getLogger(__name__)

LOG_FILE_NAME = "rfnegconv.log"  # background watcher (service)
RUN_LOG_FILE_NAME = "rfnegconv-run.log"  # single runs (launcher, terminal)
RUN_CHANNEL = "run"  # update notice: single runs
SERVICE_CHANNEL = "service"  # update notice: the background service

app = typer.Typer(
    name="rfnegconv",
    help=(
        f"Convert RAW scans of film negatives into DNG, TIFF and JPEG (v{__version__})"
    ),
    add_completion=False,
)
service_app = typer.Typer(
    help="Manage the background watch-folder service.", no_args_is_help=True
)
app.add_typer(service_app, name="service")
config_app = typer.Typer(help="Manage the config file.", no_args_is_help=True)
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
        typer.echo(f"Warning: cannot write log file in {log_dir}: {exc}", err=True)
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
        typer.echo(f"rfnegconv {__version__}")
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
            help="Show version and exit.",
        ),
    ] = False,
    config: Annotated[
        Path | None, typer.Option("--config", help="Config file path.")
    ] = None,
    silent: Annotated[
        bool, typer.Option("--silent", "-Q", help="No console output.")
    ] = False,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="More output.")
    ] = False,
    debug: Annotated[
        bool, typer.Option("--debug", "-vv", help="Debug output.")
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


@app.command()
def run(
    ctx: typer.Context,
    negative: Annotated[
        Path | None, typer.Option("--negative", help="Input folder.")
    ] = None,
    archive: Annotated[
        Path | None, typer.Option("--archive", help="Archive folder.")
    ] = None,
    photos: Annotated[
        Path | None, typer.Option("--photos", help="Output folder.")
    ] = None,
    dng: Annotated[
        bool | None, typer.Option("--dng/--no-dng", help="Write DNG files.")
    ] = None,
    dng_finder_preview: Annotated[
        bool | None,
        typer.Option(
            "--dng-finder-preview/--no-dng-finder-preview",
            help="Write uint16 DNG so Finder / Quick Look show previews (larger).",
        ),
    ] = None,
    summary: Annotated[
        bool,
        typer.Option(
            "--summary",
            help=(
                "Print one line 'processed=<n> failed=<m> busy=<0|1>' for "
                "launchers; exit 1 if the run cannot start or files stayed in "
                "the Negative folder (disk full, permissions)."
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


@app.command()
def watch(ctx: typer.Context) -> None:
    """Keep running and process new files as they arrive."""
    state: State = ctx.obj
    setup_logging(state.verbosity, default_log_dir(), LOG_FILE_NAME)
    cfg = _load(state, {})

    active = cfg  # the config of the next batch, re-read before each batch
    config_problem: str | None = None

    def on_problem(message: str) -> None:
        if active.notify:
            notify("rfnegconv", message)

    def reload() -> None:
        """Switches take effect at the next batch; a broken file keeps the last
        good config (reported once); folder changes need a restart."""
        nonlocal active, config_problem
        try:
            fresh = load_config(state.config_path)
            fresh.require_dirs()
        except RfNegconvError as exc:
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
        if fresh.require_dirs() != cfg.require_dirs():
            log.warning("Changed folders take effect when the service restarts")
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
            if latest is not None:
                on_problem(update.notice(latest))

    def after_batch() -> None:
        remember_error_files(active)  # reported with the batch

    try:
        watch_folder(
            cfg,
            on_batch=lambda result: _report(active, state.verbosity, result),
            on_problem=on_problem,
            before_batch=before_batch,
            after_batch=after_batch,
            current_config=lambda: active,
        )
    except KeyboardInterrupt:
        log.info("Stopped.")
    except RfNegconvError as exc:
        _fail(state, exc)


@service_app.command("install")
def service_install() -> None:
    """Start the watch folder automatically at login."""
    _service(lambda: daemon.install(log_dir=default_log_dir()))


@service_app.command("uninstall")
def service_uninstall() -> None:
    """Remove the background service."""
    _service(daemon.uninstall)


@service_app.command("status")
def service_status(ctx: typer.Context) -> None:
    """Show whether the background service is installed and running."""
    _service(
        lambda: (
            f"{daemon.status()}\nLog file: {default_log_dir() / LOG_FILE_NAME}"
            f"\nRun log file: {default_log_dir() / RUN_LOG_FILE_NAME}"
            f"\n{_exiftool_line(ctx.obj)}"
        )
    )


def _exiftool_line(state: State) -> str:
    try:
        configured = load_config(state.config_path).exiftool_path
    except RfNegconvError:
        configured = None
    tool = ExifTool.locate(configured)
    if tool.executable is None:
        return "exiftool: not found (outputs carry no camera metadata)"
    return f"exiftool: {tool.executable}"


@config_app.command("init")
def config_init(
    ctx: typer.Context,
    negative: Annotated[Path, typer.Option("--negative", help="Input folder.")],
    photos: Annotated[Path, typer.Option("--photos", help="Output folder.")],
    archive: Annotated[Path, typer.Option("--archive", help="Archive folder.")],
    off: Annotated[
        list[str] | None,
        typer.Option(
            "--off",
            help=f"Set this switch to false (repeatable): {', '.join(SWITCHES)}.",
        ),
    ] = None,
    expert_reset: Annotated[
        bool,
        typer.Option(
            "--expert-reset", help="Set every expert threshold to its default."
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
        _fail(state, ConfigError(f"cannot set up folders: {exc}"))
    except RfNegconvError as exc:
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
    except RfNegconvError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc


def _load(state: State, overrides: dict[str, Any]) -> Config:
    try:
        cfg = load_config(state.config_path).merge_overrides(overrides)
        cfg.require_dirs()
    except RfNegconvError as exc:
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
    if latest is not None:
        if summary:
            typer.echo(f"update={latest}")
        elif state.verbosity >= 1:
            typer.echo(f"New version {latest} available: {update.UPDATE_URL}")
    try:
        result = run_batch(cfg)
    except RfNegconvError as exc:
        _fail(state, exc)
    except OSError as exc:  # anything the batch did not classify itself
        _fail(state, FolderError(f"{exc.strerror or exc} ({exc.filename or '-'})"))
    remember_error_files(cfg)  # this run reports its own failures
    problem = problem_message(result)
    if summary:  # the launcher reports the outcome itself (dialog, no notification)
        if problem is not None:  # shown by the launcher instead of the counts
            _fail(state, FolderError(problem))
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
    except RfNegconvError as exc:  # the self-check reports the mismatch
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


def _report(cfg: Config, verbosity: int, result: BatchResult) -> None:
    if verbosity >= 1:
        typer.echo(f"{len(result.succeeded)} converted, {len(result.failed)} failed")
        for path, reason in result.failed:
            typer.echo(f"  {path.name}: {reason}", err=True)
        problem = problem_message(result)
        if problem is not None:
            typer.echo(problem, err=True)
    if cfg.notify and (result.succeeded or result.failed):
        notify(*summary_message(result))


def _fail(state: State, exc: RfNegconvError) -> NoReturn:
    typer.echo(f"Error: {exc}", err=True)
    typer.echo(f"Config file: {state.config_path}", err=True)
    raise typer.Exit(1) from exc
