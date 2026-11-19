"""Pydantic configuration with TOML loading and per-OS default locations."""

import logging
import re
import tomllib
from pathlib import Path
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic_core import ErrorDetails

from real_fast_filmlab import paths
from real_fast_filmlab.core.analyzer import AnalyzerSettings
from real_fast_filmlab.core.geometry import Rotation
from real_fast_filmlab.core.look import MAX_TOTAL_CONTRAST, MAX_TOTAL_SATURATION
from real_fast_filmlab.core.rolls import RollSettings
from real_fast_filmlab.exceptions import ConfigError

log = logging.getLogger(__name__)

DIR_FIELDS = ("negative_dir", "archive_dir", "photos_dir")
HOLDER_MIN_FLOOR = 0.3  # lower bound of holder_min, also for the derived default
IGNORED_KEYS = ("verbosity",)  # accepted in the file without effect (-Q/-v/-vv)
_ANALYZER = AnalyzerSettings()
_ROLLS = RollSettings()


def default_config_path() -> Path:
    """Per-OS config file location."""
    return paths.config_dir() / "config.toml"


def default_log_dir() -> Path:
    """Per-OS log directory."""
    return paths.log_dir()


class Config(BaseModel):
    """Runtime configuration (config file plus command-line overrides)."""

    model_config = ConfigDict(extra="forbid")

    negative_dir: Path | None = None
    archive_dir: Path | None = None
    photos_dir: Path | None = None
    dng: bool = True
    tiff: bool = True
    contact_sheet: bool = True
    service: bool = True
    update_check: bool = True
    dng_finder_preview: bool = False
    rotate: Rotation = 0
    mirror: bool = False
    exiftool_path: Path | None = None
    notify: bool = True
    parallel_jobs: int = Field(default=0, ge=0)
    settle_seconds: float = Field(default=5.0, gt=0)
    jpeg_quality: int = Field(default=95, ge=1, le=100)
    jpeg_sharpen: bool = False
    contrast: float = Field(default=_ROLLS.contrast, ge=0, le=MAX_TOTAL_CONTRAST)
    saturation: float = Field(default=_ROLLS.saturation, ge=1, le=MAX_TOTAL_SATURATION)
    flatfield: Path | None = None
    measure_inset: float = Field(default=_ANALYZER.measure_inset, ge=0, le=0.25)
    gamma_color: float = Field(default=_ANALYZER.gamma_color, gt=0)
    gamma_bw: float = Field(default=_ANALYZER.gamma_bw, gt=0)
    holder_delta: float = Field(default=_ANALYZER.holder_delta, gt=0)
    holder_min: float = Field(default=_ANALYZER.holder_min, ge=HOLDER_MIN_FLOOR)
    gap_delta: float = Field(default=_ANALYZER.gap_delta, gt=0)
    gap_std: float = Field(default=_ANALYZER.gap_std, gt=0)
    loose_delta: float = Field(default=_ANALYZER.loose_delta, gt=0)
    loose_std: float = Field(default=_ANALYZER.loose_std, gt=0)
    aspect_tol: float = Field(default=_ANALYZER.aspect_tol, gt=0, lt=1)
    dmin_percentile: float = Field(default=_ANALYZER.dmin_percentile, ge=0, le=100)
    white_percentile: float = Field(default=_ANALYZER.white_percentile, gt=0, le=100)
    edge_white: float = Field(default=_ANALYZER.edge_white, ge=0, le=0.5)
    min_skew_deg: float = Field(default=_ANALYZER.min_skew_deg, ge=0, le=45)
    max_skew_deg: float = Field(default=_ANALYZER.max_skew_deg, ge=0, le=45)
    bw_threshold: float = Field(default=_ANALYZER.bw_threshold, gt=0)
    hue_tol: float = Field(default=_ROLLS.hue_tol, gt=0)
    highkey_delta: float = Field(default=_ROLLS.highkey_delta, ge=0)
    uniform_ratio: float = Field(default=_ROLLS.uniform_ratio, ge=1)
    crossover_limit: float = Field(default=_ROLLS.crossover_limit, ge=0, le=0.5)
    crossover_roll_limit: float = Field(
        default=_ROLLS.crossover_roll_limit, ge=0, le=0.5
    )
    white_limit: float = Field(default=_ROLLS.white_limit, ge=0, le=0.5)

    @field_validator(*DIR_FIELDS, "exiftool_path", "flatfield", mode="before")
    @classmethod
    def _expand_user(cls, value: object) -> object:
        if isinstance(value, str):
            return Path(value).expanduser() if value.strip() else None
        if isinstance(value, Path):
            return value.expanduser()
        return value

    @model_validator(mode="after")
    def _derive_holder_min(self) -> "Config":
        """Default holder_min is max(0.3, min(1.0, holder_delta)).

        The derived value is not marked as set (it is re-derived after a
        merge). A holder_min set by the user is kept as written; the
        analysis uses `effective_holder_min`.
        """
        if "holder_min" not in self.model_fields_set:
            derived = max(
                HOLDER_MIN_FLOOR, min(_ANALYZER.holder_min, self.holder_delta)
            )
            self.__dict__["holder_min"] = derived  # bypasses model_fields_set
        return self

    @property
    def effective_holder_min(self) -> float:
        """holder_min as used: at most holder_delta, at least 0.3.

        A lowered holder_delta therefore never needs a lowered holder_min.
        """
        return max(HOLDER_MIN_FLOOR, min(self.holder_min, self.holder_delta))

    def merge_overrides(self, overrides: dict[str, Any]) -> "Config":
        """Return a copy with all non-None overrides applied."""
        filtered = {k: v for k, v in overrides.items() if v is not None}
        try:
            data: dict[str, Any] = self.model_dump(exclude_unset=True) | filtered
            return Config.model_validate(data)
        except ValidationError as exc:
            raise ConfigError(format_errors(exc)) from exc

    def require_dirs(self) -> tuple[Path, Path, Path]:
        """Resolved (negative, archive, photos); all set and pairwise different."""
        missing = [name for name in DIR_FIELDS if getattr(self, name) is None]
        if missing:
            raise ConfigError("Ordner nicht eingestellt: " + ", ".join(missing))
        negative, archive, photos = (
            Path(getattr(self, n)).resolve() for n in DIR_FIELDS
        )
        if len({negative, archive, photos}) < 3:
            raise ConfigError(
                "negative_dir, archive_dir und photos_dir müssen drei "
                "verschiedene Ordner sein"
            )
        return negative, archive, photos

    def analyzer_settings(self) -> AnalyzerSettings:
        return AnalyzerSettings(
            holder_delta=self.holder_delta,
            holder_min=self.effective_holder_min,
            gap_delta=self.gap_delta,
            gap_std=self.gap_std,
            loose_delta=self.loose_delta,
            loose_std=self.loose_std,
            aspect_tol=self.aspect_tol,
            dmin_percentile=self.dmin_percentile,
            white_percentile=self.white_percentile,
            edge_white=self.edge_white,
            bw_threshold=self.bw_threshold,
            min_skew_deg=self.min_skew_deg,
            max_skew_deg=self.max_skew_deg,
            measure_inset=self.measure_inset,
            gamma_color=self.gamma_color,
            gamma_bw=self.gamma_bw,
        )

    def roll_settings(self) -> RollSettings:
        return RollSettings(
            hue_tol=self.hue_tol,
            highkey_delta=self.highkey_delta,
            uniform_ratio=self.uniform_ratio,
            crossover_limit=self.crossover_limit,
            crossover_roll_limit=self.crossover_roll_limit,
            white_limit=self.white_limit,
            contrast=self.contrast,
            saturation=self.saturation,
        )


def load_config(path: Path) -> Config:
    """Load a TOML config; a missing file yields the defaults."""
    if not path.exists():
        return Config()
    try:
        raw_data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        log.info("Invalid TOML in %s: %s", path, exc)
        raise ConfigError(syntax_error(exc)) from exc
    except (OSError, UnicodeDecodeError) as exc:
        log.info("Cannot read %s: %s", path, exc)
        raise ConfigError("Die Konfigurationsdatei ist nicht lesbar.") from exc
    data: dict[str, Any] = dict(raw_data)
    for key in IGNORED_KEYS:
        if data.pop(key, None) is not None:
            log.debug("config key %r has no effect; ignored", key)
    try:
        return Config.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(format_errors(exc)) from exc


def syntax_error(exc: tomllib.TOMLDecodeError) -> str:
    """Plain German text for a file that is not valid TOML, with the line."""
    match = re.search(r"at line (\d+), column (\d+)", str(exc))
    where = f" (Zeile {match[1]}, Spalte {match[2]})" if match else ""
    return f"Schreibfehler in der Konfigurationsdatei{where}."


def format_errors(exc: ValidationError) -> str:
    """Pydantic errors as one plain German line: `Ungültige Einstellung: key: ...`."""
    return "Ungültige Einstellung: " + "; ".join(
        f"{'.'.join(str(part) for part in err['loc'])}: {_plain(err)}"
        for err in exc.errors()
    )


def _number(value: object) -> str:
    return f"{value:g}" if isinstance(value, float) else str(value)


def _plain(err: ErrorDetails) -> str:
    """German text for one pydantic error; unknown kinds keep pydantic's text."""
    kind = err["type"]
    ctx = err.get("ctx", {})
    if kind == "extra_forbidden":
        return "unbekannter Schlüssel"
    if kind == "literal_error":
        return "erlaubt sind " + str(ctx["expected"]).replace(" or ", " oder ")
    if kind in _BOUNDS:
        bound, text = _BOUNDS[kind]
        return text.format(_number(ctx[bound]))
    for prefix, text in _TYPES:
        if kind.startswith(prefix):
            return text
    return err["msg"]


_BOUNDS = {
    "greater_than": ("gt", "muss größer als {} sein"),
    "greater_than_equal": ("ge", "muss mindestens {} sein"),
    "less_than": ("lt", "muss kleiner als {} sein"),
    "less_than_equal": ("le", "darf höchstens {} sein"),
}
_TYPES = (
    ("bool_", "muss true oder false sein"),
    ("int_", "muss eine ganze Zahl sein"),
    ("float_", "muss eine Zahl sein"),
    ("path_", "muss ein Text in Anführungszeichen sein"),
    ("string_", "muss ein Text in Anführungszeichen sein"),
)
