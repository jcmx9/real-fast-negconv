"""Camera RGB -> sRGB conversion and sRGB transfer function."""

import logging

import numpy as np
import numpy.typing as npt

from real_fast_negconv.core.converter import FloatImage

log = logging.getLogger(__name__)

CHUNK_ROWS = 256

SRGB_TO_XYZ = np.array(
    [
        [0.4124564, 0.3575761, 0.1804375],
        [0.2126729, 0.7151522, 0.0721750],
        [0.0193339, 0.1191920, 0.9503041],
    ]
)


def camera_to_srgb_matrix(
    xyz_to_cam: npt.NDArray[np.floating],
) -> npt.NDArray[np.float32]:
    """Matrix mapping white-balanced camera RGB to linear sRGB (dcraw method)."""
    cam_rgb = np.asarray(xyz_to_cam, np.float64) @ SRGB_TO_XYZ
    sums = cam_rgb.sum(axis=1, keepdims=True)
    if not np.all(np.isfinite(cam_rgb)) or np.any(np.abs(sums) < 1e-6):
        log.warning("Unusable camera colour matrix; using identity (colours raw)")
        return np.eye(3, dtype=np.float32)
    try:
        return np.linalg.inv(cam_rgb / sums).astype(np.float32)
    except np.linalg.LinAlgError:
        log.warning("Singular camera colour matrix; using identity (colours raw)")
        return np.eye(3, dtype=np.float32)


def apply_matrix(img: FloatImage, matrix: npt.NDArray[np.floating]) -> FloatImage:
    """Apply a 3x3 colour matrix per pixel; negative results are clipped.

    Works in row chunks, so a non-contiguous view (a crop) is never copied whole.
    """
    transposed = np.asarray(matrix, np.float32).T
    out = np.empty(img.shape, np.float32)
    for start in range(0, img.shape[0], CHUNK_ROWS):
        rows = slice(start, start + CHUNK_ROWS)
        np.matmul(img[rows], transposed, out=out[rows])
    np.maximum(out, np.float32(0.0), out=out)
    return out


def srgb_encode(linear: FloatImage, *, inplace: bool = False) -> FloatImage:
    """sRGB OETF on values clipped to [0, 1].

    `inplace=True` overwrites a float32 `linear` instead of allocating a copy.
    """
    if inplace and linear.dtype == np.float32:
        out = np.clip(linear, 0.0, 1.0, out=linear)
    else:
        out = np.clip(linear, 0.0, 1.0).astype(np.float32)
    low = out <= 0.0031308
    low_values = out[low] * np.float32(12.92)
    np.power(out, np.float32(1.0 / 2.4), out=out)
    out *= np.float32(1.055)
    out -= np.float32(0.055)
    out[low] = low_values
    return out
