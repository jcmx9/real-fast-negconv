"""Colour crossover correction: per-layer steepness from mid-grey (spec 12.S).

The three dye layers of a colour negative have slightly different gradation
curves. Film base (x = 0) and white point (x = 1) are neutral after the
channel normalisation, the mid-tones are not. Per frame, pixels whose green
sits at mid-grey (x_G about 0.5) give the median red and blue there; the
exponent k = ln 0.5 / ln mid moves those mids back to 0.5 (x' = x ** k).
The roll damps motif colour: frame and roll exponents are combined as a
geometric mean and limited.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

import numpy as np

from real_fast_negconv.core.converter import (
    MIN_SPREAD,
    NO_CROSSOVER,
    FloatImage,
    Triple,
)

MID_BAND = 0.05  # |x_G - 0.5| below this counts as mid-grey
MIN_MID_PIXELS = 200  # fewer mid-grey pixels in the inner window: no measurement
MID_CLIP = (0.05, 0.95)  # mids are clipped before the logarithm
ROLL_MIN_FRAMES = 3  # measured colour frames a roll value needs
ROLL_AGREEMENT = 0.8  # share of frames on the side of the group median, R and B
SAMPLE_MAX_PIXELS = 87_381  # 1 MiB of float32 RGB per frame

type CrossoverSource = Literal["frame+roll", "frame only", "roll only", "none", "off"]


@dataclass(frozen=True, eq=False)
class DensitySample:
    """Every `step`-th pixel (raster order) of the inner window, density RGB."""

    pixels: FloatImage  # shape (N, 3)
    step: int


EMPTY_SAMPLE = DensitySample(np.empty((0, 3), np.float32), 1)


def sample_window(inner: FloatImage) -> DensitySample:
    """Compact copy of the inner-window density, at most SAMPLE_MAX_PIXELS.

    Every `step`-th pixel in raster order, gathered by index: the (usually
    non-contiguous) window itself is never copied.
    """
    height, width = inner.shape[:2]
    step = max(1, math.ceil(height * width / SAMPLE_MAX_PIXELS))
    index = np.arange(0, height * width, step)
    pixels = inner[index // width, index % width].astype(np.float32, copy=False)
    return DensitySample(pixels, step)


def frame_mids(sample: DensitySample, d_min: Triple, d_white: Triple) -> Triple | None:
    """Median normalised R, G, B of the mid-grey pixels, or None if too few.

    x_c = (D_c - d_min_c) / max(d_white_c - d_min_c, MIN_SPREAD); mid-grey is
    |x_G - 0.5| < MID_BAND. The minimum counts pixels of the whole window
    (selected sample pixels x step).
    """
    lo = np.asarray(d_min, np.float64)
    spread = np.maximum(np.asarray(d_white, np.float64) - lo, MIN_SPREAD)
    x = (sample.pixels - lo) / spread
    selected = x[np.abs(x[:, 1] - 0.5) < MID_BAND]
    if selected.shape[0] * sample.step < MIN_MID_PIXELS:
        return None
    r, g, b = np.median(selected, axis=0)
    return (float(r), float(g), float(b))


def steepness(mids: Triple) -> Triple:
    """Exponent k per channel that maps the mid of R and B to 0.5; G keeps 1."""

    def k(mid: float) -> float:
        return math.log(0.5) / math.log(min(max(mid, MID_CLIP[0]), MID_CLIP[1]))

    return (k(mids[0]), 1.0, k(mids[2]))


def roll_mids(mids: Sequence[Triple]) -> Triple | None:
    """Group median of the frame mids, if the roll agrees (else None).

    Needs ROLL_MIN_FRAMES measured frames, and for R and for B at least
    ROLL_AGREEMENT of them on the same side of 0.5 as the group median.
    """
    if len(mids) < ROLL_MIN_FRAMES:
        return None
    values = np.asarray(mids, np.float64)
    median = np.median(values, axis=0)
    for channel in (0, 2):
        side = np.sign(values[:, channel] - 0.5)
        share = float(np.mean(side == np.sign(median[channel] - 0.5)))
        if share < ROLL_AGREEMENT:
            return None
    return (float(median[0]), float(median[1]), float(median[2]))


def combine(k_frame: Triple, k_roll: Triple, limit: float) -> Triple:
    """k = clip(sqrt(k_frame * k_roll), 1 - limit, 1 + limit); limit 0: none."""
    if limit <= 0.0:
        return NO_CROSSOVER
    r, g, b = (
        min(max(math.sqrt(frame * roll), 1.0 - limit), 1.0 + limit)
        for frame, roll in zip(k_frame, k_roll, strict=True)
    )
    return (r, g, b)


def crossover_per_frame(
    mids: Sequence[Triple | None], groups: Sequence[int], limit: float
) -> list[tuple[Triple, CrossoverSource]]:
    """Exponent and its source per frame; `mids` None = BW or not measured."""
    if limit <= 0.0:
        return [(NO_CROSSOVER, "off")] * len(mids)
    roll: dict[int, Triple | None] = {}
    for group in set(groups):
        measured = [
            m for m, g in zip(mids, groups, strict=True) if g == group and m is not None
        ]
        roll[group] = roll_mids(measured)
    result: list[tuple[Triple, CrossoverSource]] = []
    for mid, group in zip(mids, groups, strict=True):
        group_mids = roll[group]
        if mid is None and group_mids is None:
            result.append((NO_CROSSOVER, "none"))
            continue
        source: CrossoverSource
        if mid is None:
            source = "roll only"
        elif group_mids is None:
            source = "frame only"
        else:
            source = "frame+roll"
        k_frame = NO_CROSSOVER if mid is None else steepness(mid)
        k_roll = NO_CROSSOVER if group_mids is None else steepness(group_mids)
        result.append((combine(k_frame, k_roll, limit), source))
    return result


def crossover_note(k: Triple, source: CrossoverSource) -> str:
    """ASCII text for the description and log; empty when switched off."""
    if source == "off":
        return ""
    if source == "none":
        return "none"
    return f"R x{k[0]:.3f} B x{k[2]:.3f} ({source})"
