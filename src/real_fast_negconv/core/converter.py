"""Density-space maths: colour negative -> neutral, scene-linear positive."""

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from real_fast_negconv.core.geometry import Rect

EPS = 1.0 / 65535.0
MIN_SPREAD = 0.05
CHUNK_ROWS = 256
LN10 = float(np.log(10.0))

type FloatImage = npt.NDArray[np.float32]
type Triple = tuple[float, float, float]

NO_CROSSOVER: Triple = (1.0, 1.0, 1.0)


@dataclass(frozen=True)
class ToneParams:
    """Per-frame inversion parameters (all densities absolute, per channel).

    `crossover` is the layer-steepness exponent k per channel (colour crossover).
    """

    d_min: Triple
    d_white: Triple
    gamma: float
    crossover: Triple = NO_CROSSOVER

    @property
    def d_hi(self) -> npt.NDArray[np.float32]:
        """Density spread from film base to white point, per channel."""
        spread = np.asarray(self.d_white, np.float32) - np.asarray(
            self.d_min, np.float32
        )
        return np.maximum(spread, np.float32(MIN_SPREAD))


def to_density(rgb: FloatImage, *, inplace: bool = False) -> FloatImage:
    """Optical density D = -log10(T) of linear transmission values.

    `inplace=True` overwrites a float32 `rgb` instead of allocating a copy.
    """
    if inplace and rgb.dtype == np.float32:
        density = np.maximum(rgb, np.float32(EPS), out=rgb)
    else:
        density = np.maximum(rgb, np.float32(EPS)).astype(np.float32, copy=False)
    np.log10(density, out=density)
    np.negative(density, out=density)
    return density


def _normalize_inplace(
    density: FloatImage,
    d_min: npt.NDArray[np.floating],
    d_hi: npt.NDArray[np.floating],
) -> float:
    target = float(np.mean(d_hi))
    density -= np.asarray(d_min, np.float32)
    np.maximum(density, np.float32(0.0), out=density)
    density *= (target / np.asarray(d_hi, np.float32)).astype(np.float32)
    return target


def normalize_density(
    density: FloatImage,
    d_min: npt.NDArray[np.floating],
    d_hi: npt.NDArray[np.floating],
) -> tuple[FloatImage, float]:
    """Subtract the film base and equalise channel spreads (returns a copy)."""
    out = density.astype(np.float32, copy=True)
    return out, _normalize_inplace(out, d_min, d_hi)


def density_to_linear(density: FloatImage, params: ToneParams) -> FloatImage:
    """Convert density (in place) to scene-linear light with white at 1.0.

    x = D_norm / D_target, x' = x ** k (crossover, per channel; base 0 and
    white 1 stay fixed), Y = 10^((x' * D_target - D_target) / gamma)
    """
    target = _normalize_inplace(
        density, np.asarray(params.d_min, np.float32), params.d_hi
    )
    if params.crossover != NO_CROSSOVER:
        density *= np.float32(1.0 / target)
        np.power(density, np.asarray(params.crossover, np.float32), out=density)
        density *= np.float32(target)
    density -= np.float32(target)
    density *= np.float32(LN10 / params.gamma)
    np.exp(density, out=density)
    return density


def black_point(
    linear: FloatImage, crop: Rect, percentile: float = 0.5, step: int = 4
) -> float:
    """Luminance percentile inside the crop (every `step`-th pixel)."""
    sample = linear[crop.slices()][::step, ::step]
    lum = sample.mean(axis=-1) if sample.ndim == 3 else sample
    return float(np.percentile(lum, percentile))


def apply_black_point(
    linear: FloatImage, black: float, *, clip: bool = True
) -> FloatImage:
    """Map `black` to 0 with a common offset for all channels (in place).

    `clip=True` limits the result to [0, 1]; `clip=False` keeps values below
    the black point (< 0) and above the white point (> 1).
    """
    if 0.0 < black < 0.99:
        linear -= np.float32(black)
        linear *= np.float32(1.0 / (1.0 - black))
    if clip:
        np.clip(linear, 0.0, 1.0, out=linear)
    return linear


def to_mono(linear: FloatImage, *, clip: bool = False) -> FloatImage:
    """Average the colour channels into a single grey channel.

    `clip=True` averages the channels limited to [0, 1], in row chunks (no
    full-size clipped copy).
    """
    if not clip:
        return np.asarray(linear.mean(axis=-1), dtype=np.float32)
    out = np.empty(linear.shape[:2], np.float32)
    for start in range(0, linear.shape[0], CHUNK_ROWS):
        rows = slice(start, start + CHUNK_ROWS)
        out[rows] = np.clip(linear[rows], 0.0, 1.0).mean(axis=-1)
    return out
