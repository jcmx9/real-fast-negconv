"""The config file as the user sees it: every key with its value and a comment.

`rfnegconv config init` writes the complete file; on an existing file it only
appends missing keys (with their defaults) and switches off the switches it
is asked to. Existing values are never changed otherwise.
"""

import json
import re
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from real_fast_negconv.config import IGNORED_KEYS, Config, format_errors, load_config
from real_fast_negconv.exceptions import ConfigError
from real_fast_negconv.fileio.atomic import atomic_write
from real_fast_negconv.system import automatic_workers

SWITCHES = ("dng", "tiff", "contact_sheet", "service", "update_check")

HEADER = (
    "# real-fast-negconv – Einstellungen\n"  # noqa: RUF001  # German typographic dash is intended
    "# Schalter: true = an, false = aus. Eine Änderung gilt ab dem nächsten Lauf.\n"
)


# "{auto}" is filled in when the line is written (comment only; the value stays)
PARALLEL_JOBS_COMMENT = (
    "0 = automatisch nach CPU-Kernen und Arbeitsspeicher (auf diesem Rechner: {auto})"
)


@dataclass(frozen=True)
class Key:
    """One config key in the file: its section and a short German comment."""

    name: str
    comment: str


SECTIONS: tuple[tuple[str, tuple[Key, ...]], ...] = (
    (
        "Ordner",
        (
            Key("negative_dir", "Eingang: hier RAW-Dateien hineinlegen"),
            Key("photos_dir", "fertige Bilder"),
            Key("archive_dir", "Originale nach der Verarbeitung"),
        ),
    ),
    (
        "Ausgaben (JPEG wird immer geschrieben)",
        (
            Key("dng", "DNG schreiben"),
            Key("tiff", "TIFF schreiben"),
            Key("contact_sheet", "nach jedem Lauf ein Kontaktabzug in „Fotos“"),
            Key(
                "dng_finder_preview",
                "true: größeres DNG, das Finder und Quick Look anzeigen",
            ),
            Key("jpeg_quality", "JPEG-Qualität, 1 bis 100"),
        ),
    ),
    (
        "Ausrichtung",
        (
            Key("rotate", "0, 90, 180 oder 270 (im Uhrzeigersinn)"),
            Key("mirror", "true: von der Schichtseite fotografiert"),
        ),
    ),
    (
        "Dienst und Betrieb",
        (
            Key("service", "Hintergrunddienst: neue Negative automatisch umwandeln"),
            Key("update_check", "höchstens einmal pro Woche nach neuer Version sehen"),
            Key("notify", "Mitteilung nach jedem Lauf"),
            Key("parallel_jobs", PARALLEL_JOBS_COMMENT),
            Key("settle_seconds", "Dienst: Sekunden ohne Änderung vor dem Start"),
            Key("exiftool_path", "leer = exiftool automatisch suchen"),
        ),
    ),
    (
        "Experten-Schwellen (nur bei ungewöhnlichem Material ändern, siehe README)",
        (
            Key("measure_inset", "Rand des Messfensters je Seite"),
            Key("holder_delta", "Filmmaske: Dichte über der Basis"),
            Key("holder_min", "Halter: Mindestdichte, höchstens holder_delta"),
            Key("gap_delta", "Steg: Dichtegrenze"),
            Key("gap_std", "Steg: Streuungsgrenze"),
            Key("loose_delta", "Randbeschnitt: Dichtegrenze"),
            Key("loose_std", "Randbeschnitt: Streuungsgrenze"),
            Key("aspect_tol", "Filmformat einrasten bis zu dieser Abweichung"),
            Key("min_skew_deg", "kleinste korrigierte Schräglage (Grad)"),
            Key("max_skew_deg", "größte korrigierte Schräglage (Grad)"),
            Key("dmin_percentile", "Perzentil der Filmbasis (%)"),
            Key("white_percentile", "Perzentil des Weißpunkts (%)"),
            Key("bw_threshold", "Farbe/Schwarzweiß-Grenze"),
            Key("gamma_color", "Gradation Farbfilm"),
            Key("gamma_bw", "Gradation Schwarzweißfilm"),
            Key("hue_tol", "Rollen-Gruppierung: Farbton-Abstand"),
            Key("highkey_delta", "High-Key-Fallback: Mindestanhebung"),
            Key("uniform_ratio", "High-Key-Fallback: Gleichmäßigkeit"),
            Key("crossover_limit", "Farbübergangs-Korrektur, 0 = aus"),
        ),
    ),
)
ALL_KEYS = tuple(key for _title, keys in SECTIONS for key in keys)
EXPERT_KEYS = SECTIONS[-1][1]
COMMENT_COLUMN = 28


def toml_value(value: object) -> str:
    """One TOML value; a missing path is the empty string."""
    if value is None:
        return '""'
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Path):
        # a JSON string is a valid TOML basic string
        return json.dumps(str(value), ensure_ascii=False)
    if isinstance(value, int | float):
        return repr(value)
    raise TypeError(f"no TOML form for {value!r}")  # pragma: no cover


def key_line(key: Key, value: object) -> str:
    assignment = f"{key.name} = {toml_value(value)}"
    comment = key.comment
    if "{auto}" in comment:
        comment = comment.format(auto=automatic_workers())
    return f"{assignment.ljust(COMMENT_COLUMN - 1)} # {comment}\n"


def default_values(folders: dict[str, Path]) -> dict[str, object]:
    """Value of every key in a new file: the defaults plus the given folders."""
    defaults = Config()
    values: dict[str, object] = {k.name: getattr(defaults, k.name) for k in ALL_KEYS}
    values.update({name: folder.expanduser() for name, folder in folders.items()})
    return values


def render(values: dict[str, object]) -> str:
    """The complete config file."""
    parts = [HEADER]
    for title, keys in SECTIONS:
        parts.append(f"\n# {title}\n")
        parts.extend(key_line(key, values[key.name]) for key in keys)
    return "".join(parts)


def set_switch(text: str, name: str, value: bool) -> str:
    """Set the switch `name` in the file text (its line stays otherwise as is)."""
    pattern = re.compile(rf'^(\s*"?{name}"?\s*=\s*)(true|false)\b', re.MULTILINE)
    return pattern.sub(lambda m: m.group(1) + ("true" if value else "false"), text)


def set_value(text: str, name: str, value: object) -> str:
    """Set the plain value of key `name` in the file text; a comment stays."""
    pattern = re.compile(
        rf'^(\s*"?{name}"?\s*=\s*)[^#\n]*?(\s*(?:#.*)?)$', re.MULTILINE
    )
    return pattern.sub(lambda m: m.group(1) + toml_value(value) + m.group(2), text)


@dataclass(frozen=True)
class InitResult:
    """Outcome of `config init`: "created", "completed" (keys appended or a
    switch set) or "kept" (the file was not changed)."""

    status: str
    config: Config


def init_file(
    path: Path,
    *,
    folders: dict[str, Path],
    switches_off: tuple[str, ...] = (),
    service_installed: Callable[[], bool] | None = None,
    expert_reset: bool = False,
) -> InitResult:
    """Write the complete config file, or complete an existing one.

    A new file gets every key (`folders` for the three folders, defaults for
    the rest). An existing file must be valid; keys it lacks are appended with
    the values the file produces now (defaults, or values derived from its
    other keys), so appending never changes what the file means. Exception:
    a missing `service` is written as the current state (`service_installed`),
    so completing a file never brings back a service that was removed. Its
    values stay as they are. The switches in `switches_off` are set to false
    in both cases. With `expert_reset` every expert threshold is set to its
    default (present lines in place, missing ones appended).
    """
    unknown = [name for name in switches_off if name not in SWITCHES]
    if unknown:
        raise ConfigError("unknown switch: " + ", ".join(unknown))
    if not path.exists():
        values = default_values(folders)
        values.update(dict.fromkeys(switches_off, False))
        text = render(values)
        _check(text, path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8", newline="") as handle:  # never overwrite
            handle.write(text)
        return InitResult(status="created", config=load_config(path))
    loaded = load_config(path)  # an invalid file is reported and never touched
    try:
        original = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:  # pragma: no cover - load read it
        raise ConfigError(f"cannot read {path}: {exc}") from exc
    present = set(tomllib.loads(original))
    current: dict[str, object] = {k.name: getattr(loaded, k.name) for k in ALL_KEYS}
    for name, folder in folders.items():
        if current[name] is None:
            current[name] = folder.expanduser()
    if "service" not in present and service_installed is not None:
        current["service"] = service_installed()
    if expert_reset:
        defaults = Config()
        current.update({k.name: getattr(defaults, k.name) for k in EXPERT_KEYS})
    missing = [key for key in ALL_KEYS if key.name not in present]
    text = original
    if missing:
        if text and not text.endswith("\n"):
            text += "\n"
        text += "\n" + "".join(key_line(key, current[key.name]) for key in missing)
    for name in switches_off:
        text = set_switch(text, name, False)
    if expert_reset:
        for key in EXPERT_KEYS:
            if key.name in present:
                text = set_value(text, key.name, current[key.name])
    if text == original:
        return InitResult(status="kept", config=loaded)
    _check(text, path)
    atomic_write(path, lambda tmp: _write_text(tmp, text))
    return InitResult(status="completed", config=load_config(path))


def _check(text: str, path: Path) -> None:
    """The text must load as a valid config before it is written."""
    try:
        data: dict[str, Any] = tomllib.loads(text)
        for key in IGNORED_KEYS:
            data.pop(key, None)
        Config.model_validate(data)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"cannot complete {path}: {exc}") from exc
    except ValidationError as exc:
        raise ConfigError(f"cannot complete {path}: {format_errors(exc)}") from exc


def _write_text(path: Path, text: str) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(text)
