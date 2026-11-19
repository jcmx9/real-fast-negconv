"""Flat field: take the light fall-off of lamp and lens out of a scan.

The inversion amplifies uneven light: where the lamp or the lens gives less
light, the negative looks denser and the picture comes out brighter. A RAW
of the empty holder on the same light, taken with the same lens, aperture
and distance, records that fall-off; dividing every scan by it removes it.
Only the smooth fall-off is used (the reference is reduced and blurred), so
dust on the reference leaves no marks.

A holder shows the light through a window: the reference then is a bright
rectangle in a black frame. Only the lit area tells the fall-off; the map is
smoothed inside it and carried on outwards from its edge, so the frame never
darkens the picture next to it.
"""

import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import cv2
import numpy as np
import numpy.typing as npt

from real_fast_filmlab.core.converter import FloatImage
from real_fast_filmlab.exceptions import RawLoadError
from real_fast_filmlab.fileio import raw_loader

log = logging.getLogger(__name__)

MAP_EDGE = 256  # long edge of the stored fall-off map
BLUR_FRACTION = 0.05  # blur sigma, x long edge of the map
CENTRE_FRACTION = 0.1  # the central region that defines "full light"
MIN_GAIN, MAX_GAIN = 0.2, 1.5  # limits of the fall-off (1 = centre)
ASPECT_TOLERANCE = 0.02  # reference and scan must have the same shape
CHUNK_ROWS = 256
# The lit area of the reference (the window of a holder)
LIT_FRACTION = 0.25  # lit: brightest channel above this x the reference's peak
LIT_MARGIN = 2  # map pixels taken off the lit area: the soft edge of the window
MIN_WEIGHT = 1e-3  # blurred share of lit pixels below which the map is carried on
# A reference that cannot tell the fall-off
CLIP_LEVEL = 0.98  # of the sensor range: the light is clipped there
CLIP_SHARE = 0.01  # share of the lit area that may be clipped (glints)
DARK_LEVEL = 0.01  # of the sensor range: a peak below this is no light

type Reason = Literal["missing", "unreadable", "overexposed", "dark"]


class UnusableReferenceError(Exception):
    """The reference cannot tell the fall-off; `reason` says why."""

    def __init__(self, reason: Reason) -> None:
        super().__init__(reason)
        self.reason: Reason = reason


@dataclass(frozen=True, eq=False)
class FlatField:
    """Light relative to the image centre, per channel, on a small map."""

    gain: FloatImage  # (h, w, 3), 1.0 at the centre

    def matches(self, shape: tuple[int, ...]) -> bool:
        """True if an image of `shape` has the proportions of the reference."""
        own = self.gain.shape[1] / self.gain.shape[0]
        other = shape[1] / shape[0]
        return bool(abs(own / other - 1.0) <= ASPECT_TOLERANCE)

    def correct(self, rgb: FloatImage) -> None:
        """Divide `rgb` by the fall-off, in place and in row chunks."""
        height, width = rgb.shape[:2]
        full_width = cv2.resize(
            self.gain, (width, self.gain.shape[0]), interpolation=cv2.INTER_LINEAR
        )
        rows_in = self.gain.shape[0]
        for start in range(0, height, CHUNK_ROWS):
            stop = min(height, start + CHUNK_ROWS)
            # rows of the map this chunk falls between (linear interpolation)
            position = (np.arange(start, stop) + 0.5) * rows_in / height - 0.5
            lower = np.clip(np.floor(position).astype(np.int64), 0, rows_in - 1)
            upper = np.clip(lower + 1, 0, rows_in - 1)
            weight = np.clip(position - lower, 0.0, 1.0).astype(np.float32)
            gain = full_width[lower] * (1.0 - weight)[:, None, None]
            gain += full_width[upper] * weight[:, None, None]
            rgb[start:stop] /= gain


def build(rgb: FloatImage) -> FlatField:
    """Fall-off map from the decoded reference (linear camera RGB).

    Raises UnusableReferenceError for a reference without light ("dark") or with
    more than CLIP_SHARE of its lit area at the sensor's limit
    ("overexposed": the clipped light is flat, whatever the fall-off).
    """
    height, width = rgb.shape[:2]
    scale = MAP_EDGE / max(height, width)
    size = (max(2, round(width * scale)), max(2, round(height * scale)))
    small = cv2.resize(rgb, size, interpolation=cv2.INTER_AREA)
    brightest = small.max(axis=2)
    peak = float(np.percentile(brightest, 99.0))
    if peak < DARK_LEVEL:
        raise UnusableReferenceError("dark")
    lit = brightest > LIT_FRACTION * peak
    if float((brightest[lit] >= CLIP_LEVEL).mean()) > CLIP_SHARE:
        raise UnusableReferenceError("overexposed")
    smooth = _smooth_lit(small, lit, BLUR_FRACTION * max(size))
    dh = max(1, round(size[1] * CENTRE_FRACTION / 2))
    dw = max(1, round(size[0] * CENTRE_FRACTION / 2))
    centre = smooth[
        size[1] // 2 - dh : size[1] // 2 + dh, size[0] // 2 - dw : size[0] // 2 + dw
    ]
    reference = np.maximum(centre.reshape(-1, 3).mean(axis=0), np.float32(1e-6))
    gain = np.clip(smooth / reference, MIN_GAIN, MAX_GAIN).astype(np.float32)
    return FlatField(gain=np.ascontiguousarray(gain))


def _smooth_lit(
    small: FloatImage, lit: npt.NDArray[np.bool_], sigma: float
) -> FloatImage:
    """`small` blurred over its lit pixels only, carried on beyond them.

    The soft edge of the lit area (LIT_MARGIN pixels) is left out. Each
    pixel gets the Gaussian average of the lit pixels around it; where
    hardly any is in reach (less than MIN_WEIGHT of the kernel), the value
    of the nearest pixel that has one. A reference lit all over is simply
    blurred.
    """
    kernel = np.ones((2 * LIT_MARGIN + 1, 2 * LIT_MARGIN + 1), np.uint8)
    core = cv2.erode(lit.astype(np.uint8), kernel)  # image borders are no edge
    if not core.any():
        core = lit.astype(np.uint8)
    weight = core.astype(np.float32)
    border = cv2.BORDER_REPLICATE
    summed = cv2.GaussianBlur(
        small * weight[..., None], (0, 0), sigma, borderType=border
    )
    share = cv2.GaussianBlur(weight, (0, 0), sigma, borderType=border)
    known = share >= MIN_WEIGHT
    smooth = summed / np.maximum(share, np.float32(MIN_WEIGHT))[..., None]
    if not known.all():
        # label of the nearest known pixel for every other one
        _, labels = cv2.distanceTransformWithLabels(
            (~known).astype(np.uint8),
            cv2.DIST_L2,
            cv2.DIST_MASK_5,
            labelType=cv2.DIST_LABEL_PIXEL,
        )
        nearest = np.zeros(int(labels.max()) + 1, np.intp)
        nearest[labels[known]] = np.flatnonzero(known)
        smooth = smooth.reshape(-1, 3)[nearest[labels]]
    return np.asarray(smooth, np.float32)


_cache: dict[tuple[Path, int, int], FlatField | Reason] = {}
_cache_lock = threading.Lock()


def _resolve(path: Path) -> FlatField | Reason:
    """The flat field of `path`, or why there is none.

    Decoded once per file version (path, size, modification time) and kept;
    an unusable reference is logged once.
    """
    try:
        stat = path.stat()
    except OSError as exc:
        key = (path, -1, -1)
        with _cache_lock:
            if key not in _cache:
                _cache[key] = "missing"
                log.warning("Flat-field reference %s not readable: %s", path, exc)
        return "missing"
    key = (path, stat.st_size, stat.st_mtime_ns)
    with _cache_lock:
        if key not in _cache:
            try:
                _cache[key] = build(raw_loader.load(path, half_size=True).rgb)
                log.info("Flat field loaded from %s", path.name)
            except UnusableReferenceError as exc:
                _cache[key] = exc.reason
                log.warning("Flat-field reference %s not usable: %s", path, exc)
            except (RawLoadError, MemoryError, cv2.error) as exc:
                _cache[key] = "unreadable"
                log.warning("Flat-field reference %s not usable: %s", path, exc)
        return _cache[key]


def load(path: Path | None) -> FlatField | None:
    """The flat field of the reference RAW `path`; None if unset or unusable.

    The scans are developed without an unusable reference; `problem` tells
    why it is unusable.
    """
    if path is None:
        return None
    found = _resolve(path)
    return found if isinstance(found, FlatField) else None


def problem(path: Path | None) -> Reason | None:
    """Why the configured reference `path` is not used; None if it is fine."""
    if path is None:
        return None
    found = _resolve(path)
    return None if isinstance(found, FlatField) else found


def fits(path: Path | None, shape: tuple[int, ...]) -> bool:
    """False if a usable reference has other proportions than a scan of `shape`."""
    flat = load(path)
    return flat is None or flat.matches(shape)


def apply(raw: raw_loader.RawImage, path: Path | None) -> bool:
    """Correct `raw` in place with the reference `path`; True if it was done.

    A reference of other proportions (another camera or orientation) is not
    applied.
    """
    flat = load(path)
    if flat is None:
        return False
    if not flat.matches(raw.rgb.shape):
        log.warning(
            "Flat field not applied to %s: the reference has other proportions",
            raw.source.name,
        )
        return False
    flat.correct(raw.rgb)
    np.clip(raw.rgb, 0.0, 1.0, out=raw.rgb)
    return True
