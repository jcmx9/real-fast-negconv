"""Flat field: take the light fall-off of lamp and lens out of a scan.

The inversion amplifies uneven light: where the lamp or the lens gives less
light, the negative looks denser and the picture comes out brighter. A RAW
of the empty holder on the same light, taken with the same lens, aperture
and distance, records that fall-off; dividing every scan by it removes it.
Only the smooth fall-off is used (the reference is reduced and blurred), so
dust on the reference leaves no marks.
"""

import logging
import threading
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

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
    """Fall-off map from the decoded reference (linear camera RGB)."""
    height, width = rgb.shape[:2]
    scale = MAP_EDGE / max(height, width)
    size = (max(2, round(width * scale)), max(2, round(height * scale)))
    small = cv2.resize(rgb, size, interpolation=cv2.INTER_AREA)
    sigma = BLUR_FRACTION * max(size)
    small = cv2.GaussianBlur(small, (0, 0), sigma, borderType=cv2.BORDER_REPLICATE)
    dh = max(1, round(size[1] * CENTRE_FRACTION / 2))
    dw = max(1, round(size[0] * CENTRE_FRACTION / 2))
    centre = small[
        size[1] // 2 - dh : size[1] // 2 + dh, size[0] // 2 - dw : size[0] // 2 + dw
    ]
    reference = np.maximum(centre.reshape(-1, 3).mean(axis=0), np.float32(1e-6))
    gain = np.clip(small / reference, MIN_GAIN, MAX_GAIN).astype(np.float32)
    return FlatField(gain=np.ascontiguousarray(gain))


_cache: dict[tuple[Path, int, int], FlatField | None] = {}
_cache_lock = threading.Lock()


def load(path: Path | None) -> FlatField | None:
    """The flat field of the reference RAW `path`; None if unset or unusable.

    Decoded once per file version (path, size, modification time) and kept;
    an unusable reference is reported once and the scans are developed
    without it.
    """
    if path is None:
        return None
    try:
        stat = path.stat()
    except OSError as exc:
        key = (path, -1, -1)
        with _cache_lock:
            if key not in _cache:
                _cache[key] = None
                log.warning("Flat-field reference %s not readable: %s", path, exc)
        return None
    key = (path, stat.st_size, stat.st_mtime_ns)
    with _cache_lock:
        if key not in _cache:
            try:
                _cache[key] = build(raw_loader.load(path, half_size=True).rgb)
                log.info("Flat field loaded from %s", path.name)
            except (RawLoadError, MemoryError, cv2.error) as exc:
                _cache[key] = None
                log.warning("Flat-field reference %s not usable: %s", path, exc)
        return _cache[key]


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
