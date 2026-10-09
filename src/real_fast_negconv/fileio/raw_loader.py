"""Decode camera RAW files into linear, unbalanced camera RGB via LibRaw."""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt
import rawpy

from real_fast_negconv.core.converter import FloatImage
from real_fast_negconv.exceptions import RawLoadError

RAW_EXTENSIONS = frozenset(
    {
        ".arw",
        ".sr2",
        ".raf",
        ".nef",
        ".nrw",
        ".cr2",
        ".cr3",
        ".orf",
        ".rw2",
        ".pef",
        ".srw",
        ".dng",
    }
)


@dataclass
class RawImage:
    """Linear camera RGB in [0, 1] plus the camera colour matrix (XYZ -> camera)."""

    rgb: FloatImage
    xyz_to_cam: npt.NDArray[np.float64]
    source: Path

    def take_rgb(self) -> FloatImage:
        """Hand the pixel buffer over (no copy); this object keeps an empty one.

        Lets a consumer work in place and free the frame as soon as it is done.
        """
        rgb, self.rgb = self.rgb, np.empty((0, 0, 3), np.float32)
        return rgb


def load(path: Path, *, half_size: bool = False) -> RawImage:
    """Decode a RAW without white balance, gamma or auto brightness.

    LibRaw applies the RAW orientation flag, so outputs use Orientation=1.
    """
    try:
        with rawpy.imread(str(path)) as raw:
            rgb16 = raw.postprocess(
                output_bps=16,
                gamma=(1, 1),
                no_auto_bright=True,
                use_camera_wb=False,
                use_auto_wb=False,
                user_wb=[1.0, 1.0, 1.0, 1.0],
                output_color=rawpy.ColorSpace.raw,  # type: ignore[attr-defined]  # rawpy ships no stubs
                half_size=half_size,
            )
            matrix = np.array(raw.rgb_xyz_matrix[:3], dtype=np.float64)
    except (rawpy.LibRawError, OSError, ValueError) as exc:  # type: ignore[attr-defined]  # rawpy ships no stubs
        raise RawLoadError(f"cannot read {path.name}: {exc}") from exc
    if not np.any(matrix):
        matrix = np.eye(3)
    rgb = rgb16.astype(np.float32)
    rgb *= np.float32(1.0 / 65535.0)
    return RawImage(rgb=rgb, xyz_to_cam=matrix, source=path)
