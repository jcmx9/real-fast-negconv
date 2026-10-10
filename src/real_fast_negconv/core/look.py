"""Gentle correction (contrast, saturation) for TIFF, JPEG and DNG.

Three steps: `measure_sampled` reads statistics from a neutral image,
`look_params` turns statistics into parameters, `apply_look_params` applies
them to an sRGB-encoded image (TIFF/JPEG); `apply_look_linear` applies the
same correction to the scene-linear DNG data. The look never changes the
exposure: it only adds contrast and saturation, both from the roll group's
median statistics when given. All statistics are taken on the neutral image
(crossover applied).
"""

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from real_fast_negconv.core.color import srgb_decode, srgb_encode
from real_fast_negconv.core.converter import FloatImage

CHUNK_ROWS = 256

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


def measure_sampled(sample: FloatImage) -> LookStats:
    """Spread and mean chroma of pixels taken with `inner_sample`."""
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
    """Contrast and saturation from `roll_tone` (the roll group's
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


def is_identity(params: LookParams) -> bool:
    """True if the look changes nothing (no contrast, no saturation boost)."""
    return params.contrast <= 0.0 and (params.is_bw or params.saturation <= 1.0)


def apply_look_linear(
    linear: FloatImage,
    params: LookParams,
    cam_to_srgb: npt.NDArray[np.floating] | None = None,
) -> None:
    """Apply the TIFF/JPEG correction to scene-linear data, in place.

    Per pixel (in row chunks): x = cam_to_srgb @ camera (colour; BW: the
    mono value), c = x limited to [0, 1], then
    x' = decode(apply_look_params(encode(c))) + (x - c) and back to camera
    space with the inverse matrix. Inside [0, 1] the result, converted to sRGB
    and encoded the way the TIFF is made, gives the TIFF's values; values
    outside [0, 1] keep their distance to the end of the range (slope 1), so
    highlights above the white point and shadows below the black point stay
    as recoverable as before. The curve is continuous at 0 and 1; its slope
    there is 1 - contrast, outside it is 1.
    """
    if is_identity(params):
        return
    matrix = inverse = None
    if cam_to_srgb is not None and linear.ndim == 3:
        matrix = np.asarray(cam_to_srgb, np.float32)
        try:
            inverse = np.linalg.inv(matrix.astype(np.float64)).astype(np.float32)
        except np.linalg.LinAlgError:
            matrix = None
    for start in range(0, linear.shape[0], CHUNK_ROWS):
        rows = slice(start, start + CHUNK_ROWS)
        x = linear[rows] @ matrix.T if matrix is not None else linear[rows].copy()
        clipped = np.clip(x, 0.0, 1.0)
        x -= clipped  # the part outside [0, 1]
        corrected = apply_look_params(srgb_encode(clipped, inplace=True), params)
        x += srgb_decode(corrected, inplace=True)
        if matrix is not None and inverse is not None:
            linear[rows] = x @ inverse.T
        else:
            linear[rows] = x


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
    """Inner measurement window, every SAMPLE_STEP-th pixel (a view)."""
    height, width = plane.shape[:2]
    dh, dw = int(height * inset), int(width * inset)
    inner = plane[dh : height - dh, dw : width - dw]
    return inner[::SAMPLE_STEP, ::SAMPLE_STEP]


def _luminance(img: FloatImage) -> FloatImage:
    if img.ndim == 2:
        return img
    return (img @ LUMA).astype(np.float32, copy=False)
