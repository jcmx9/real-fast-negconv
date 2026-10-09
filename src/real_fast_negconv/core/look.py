"""Faithful viewing look for JPEG/TIFF (spec 12.B, 12.V); DNG stays neutral.

Three steps: `measure_look` reads statistics from a neutral image,
`look_params` turns statistics into parameters, `apply_look_params` applies
them. The look never changes the exposure: it only adds contrast and
saturation, both from the roll group's median statistics when given. All
statistics are taken on the neutral image (crossover applied, spec 12.S).
"""

from dataclasses import dataclass
from typing import Literal

import numpy as np

from real_fast_negconv.core.converter import FloatImage
from real_fast_negconv.core.geometry import MEASURE_INSET

type LookName = Literal["auto", "off"]

LUMA = np.array([0.2126, 0.7152, 0.0722], np.float32)

# Correction strength per image kind (scales the contrast).
COLOR_STRENGTH = 1.0
BW_STRENGTH = 0.5

# Contrast: s = clip(SPREAD_TARGET - spread, 0, MAX_CONTRAST) * strength.
SPREAD_TARGET = 0.70
MAX_CONTRAST = 0.35

# Saturation: 1 + SAT_GAIN * (CHROMA_TARGET - mean chroma), limited to [1, MAX].
CHROMA_TARGET = 0.10
SAT_GAIN = 1.5
MAX_SATURATION = 1.15
CHROMA_FULL = 0.5  # chroma at which the saturation boost fades out completely

SAMPLE_STEP = 4


@dataclass(frozen=True)
class LookStats:
    """Look statistics of a neutral sRGB image or of a roll group's median."""

    spread: float  # p95 - p5 of the luminance
    chroma: float  # mean of max - min over the channels; 0 for BW


@dataclass(frozen=True)
class LookParams:
    """Parameters of the look; contrast 0 and saturation 1 = identity."""

    contrast: float  # smoothstep mix s
    saturation: float
    is_bw: bool


def measure_look(srgb: FloatImage, inset: float = MEASURE_INSET) -> LookStats:
    """Spread and mean chroma of the inner window (`inset` per side)."""
    return measure_sampled(inner_sample(srgb, inset))


def measure_sampled(sample: FloatImage) -> LookStats:
    """Look statistics of pixels already taken with `inner_sample`."""
    img = np.clip(sample, 0.0, 1.0)
    lum = _luminance(img)
    chroma = 0.0
    if img.ndim == 3:
        chroma = float((img.max(axis=2) - img.min(axis=2)).mean())
    return LookStats(
        spread=float(np.percentile(lum, 95) - np.percentile(lum, 5)),
        chroma=chroma,
    )


def look_params(
    stats: LookStats, is_bw: bool, roll_tone: LookStats | None = None
) -> LookParams:
    """Spec 12.V: contrast and saturation from `roll_tone` (the roll group's
    median spread and chroma) or, if None, from the frame's own statistics.
    No exposure correction: the picture's brightness is left as it is.
    """
    strength = BW_STRENGTH if is_bw else COLOR_STRENGTH
    tone = stats if roll_tone is None else roll_tone
    contrast = strength * float(np.clip(SPREAD_TARGET - tone.spread, 0.0, MAX_CONTRAST))
    saturation = 1.0
    if not is_bw:
        saturation = float(
            np.clip(1.0 + SAT_GAIN * (CHROMA_TARGET - tone.chroma), 1.0, MAX_SATURATION)
        )
    return LookParams(contrast, saturation, is_bw)


def apply_look_params(srgb: FloatImage, params: LookParams) -> FloatImage:
    """Apply S-curve and saturation; no statistics are taken.

    Memory: one working copy of `srgb` plus at most one full-size temporary;
    every step uses explicit in-place operations instead of relying on
    NumPy's temporary elision (not available on every platform).
    """
    out = np.clip(srgb, 0.0, 1.0).astype(np.float32, copy=False)
    is_color = out.ndim == 3
    if params.contrast > 0.0:
        # mix (1 - s) * x + s * x * x * (3 - 2x), built in one temporary
        curve = np.multiply(out, np.float32(-2.0))
        curve += np.float32(3.0)
        curve *= out
        curve *= out
        curve *= np.float32(params.contrast)
        out *= np.float32(1.0 - params.contrast)
        out += curve
        del curve
    if is_color and params.saturation > 1.0:
        _saturate_inplace(out, params.saturation)
    np.clip(out, 0.0, 1.0, out=out)
    return out


def apply_look(srgb: FloatImage, look: LookName) -> FloatImage:
    """Convenience for single images: parameters from the image's own statistics."""
    if look == "off":
        return srgb
    return apply_look_params(srgb, look_params(measure_look(srgb), srgb.ndim == 2))


def _saturate_inplace(out: FloatImage, saturation: float) -> None:
    """Chroma-weighted boost: pale pixels gain most, vivid ones keep theirs."""
    factor = out.max(axis=2)
    factor -= out.min(axis=2)  # chroma
    factor *= np.float32(1.0 / CHROMA_FULL)
    np.clip(factor, 0.0, 1.0, out=factor)
    # 1 + (saturation - 1) * (1 - clipped chroma)
    factor *= np.float32(1.0 - saturation)
    factor += np.float32(saturation)
    lum = _luminance(out)[..., None]
    out -= lum
    out *= factor[..., None]
    out += lum


def inner_sample(plane: FloatImage, inset: float) -> FloatImage:
    """Inner measurement window (spec 12.A), every SAMPLE_STEP-th pixel (a view)."""
    height, width = plane.shape[:2]
    dh, dw = int(height * inset), int(width * inset)
    inner = plane[dh : height - dh, dw : width - dw]
    return inner[::SAMPLE_STEP, ::SAMPLE_STEP]


def _luminance(img: FloatImage) -> FloatImage:
    if img.ndim == 2:
        return img
    return (img @ LUMA).astype(np.float32, copy=False)
