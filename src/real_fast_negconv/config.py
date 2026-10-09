"""Pydantic configuration with TOML loading and per-OS default locations."""

import logging
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

from real_fast_negconv import paths
from real_fast_negconv.core.analyzer import AnalyzerSettings
from real_fast_negconv.core.geometry import Rotation
from real_fast_negconv.core.rolls import RollSettings
from real_fast_negconv.exceptions import ConfigError

log = logging.getLogger(__name__)

DIR_FIELDS = ("negative_dir", "archive_dir", "photos_dir")
HOLDER_MIN_FLOOR = 0.3  # lower bound of holder_min, also for the derived default
_ANALYZER = AnalyzerSettings()
_ROLLS = RollSettings()


def default_config_path() -> Path:
    """Per-OS config file location."""
    return paths.config_dir() / "config.toml"


def default_log_dir() -> Path:
    """Per-OS log directory."""
    return paths.log_dir()


class Config(BaseModel):
    """Runtime configuration (spec 7.1)."""

    model_config = ConfigDict(extra="forbid")

    negative_dir: Path | None = None
    archive_dir: Path | None = None
    photos_dir: Path | None = None
    dng: bool = True
    dng_finder_preview: bool = False
    rotate: Rotation = 0
    mirror: bool = False
    exiftool_path: Path | None = None
    notify: bool = True
    parallel_jobs: int = Field(default=0, ge=0)
    settle_seconds: float = Field(default=5.0, gt=0)
    jpeg_quality: int = Field(default=95, ge=1, le=100)
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
    min_skew_deg: float = Field(default=_ANALYZER.min_skew_deg, ge=0, le=45)
    max_skew_deg: float = Field(default=_ANALYZER.max_skew_deg, ge=0, le=45)
    bw_threshold: float = Field(default=_ANALYZER.bw_threshold, gt=0)
    hue_tol: float = Field(default=_ROLLS.hue_tol, gt=0)
    highkey_delta: float = Field(default=_ROLLS.highkey_delta, ge=0)
    uniform_ratio: float = Field(default=_ROLLS.uniform_ratio, ge=1)
    crossover_limit: float = Field(default=_ROLLS.crossover_limit, ge=0, le=0.5)
    verbosity: int = Field(default=1, ge=0, le=3)

    @field_validator(*DIR_FIELDS, "exiftool_path", mode="before")
    @classmethod
    def _expand_user(cls, value: object) -> object:
        if isinstance(value, str):
            return Path(value).expanduser() if value.strip() else None
        if isinstance(value, Path):
            return value.expanduser()
        return value

    @model_validator(mode="after")
    def _holder_min_up_to_holder_delta(self) -> "Config":
        """Default holder_min is max(0.3, min(1.0, holder_delta)).

        The derived value is not marked as set (it is re-derived after a
        merge); only a holder_min set by the user may exceed holder_delta.
        """
        if "holder_min" not in self.model_fields_set:
            derived = max(
                HOLDER_MIN_FLOOR, min(_ANALYZER.holder_min, self.holder_delta)
            )
            self.__dict__["holder_min"] = derived  # bypasses model_fields_set
        elif self.holder_min > self.holder_delta:
            raise ValueError("holder_min must not exceed holder_delta")
        return self

    def merge_overrides(self, overrides: dict[str, Any]) -> "Config":
        """Return a copy with all non-None overrides applied."""
        filtered = {k: v for k, v in overrides.items() if v is not None}
        try:
            data: dict[str, Any] = self.model_dump(exclude_unset=True) | filtered
            return Config.model_validate(data)
        except ValidationError as exc:
            raise ConfigError(_format_errors(exc)) from exc

    def require_dirs(self) -> tuple[Path, Path, Path]:
        """Resolved (negative, archive, photos); all set and pairwise different."""
        missing = [name for name in DIR_FIELDS if getattr(self, name) is None]
        if missing:
            raise ConfigError("folders not configured: " + ", ".join(missing))
        negative, archive, photos = (
            Path(getattr(self, n)).resolve() for n in DIR_FIELDS
        )
        if len({negative, archive, photos}) < 3:
            raise ConfigError(
                "negative_dir, archive_dir and photos_dir must be "
                "three different folders"
            )
        return negative, archive, photos

    def analyzer_settings(self) -> AnalyzerSettings:
        return AnalyzerSettings(
            holder_delta=self.holder_delta,
            holder_min=self.holder_min,
            gap_delta=self.gap_delta,
            gap_std=self.gap_std,
            loose_delta=self.loose_delta,
            loose_std=self.loose_std,
            aspect_tol=self.aspect_tol,
            dmin_percentile=self.dmin_percentile,
            white_percentile=self.white_percentile,
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
        )


def load_config(path: Path) -> Config:
    """Load a TOML config; a missing file yields the defaults."""
    if not path.exists():
        return Config()
    try:
        raw_data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid TOML in {path}: {exc}") from exc
    except (OSError, UnicodeDecodeError) as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc
    data: dict[str, Any] = dict(raw_data)
    try:
        return Config.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"invalid config in {path}: {_format_errors(exc)}") from exc


def _format_errors(exc: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(part) for part in err['loc'])}: {err['msg']}"
        for err in exc.errors()
    )
