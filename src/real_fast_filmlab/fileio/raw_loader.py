"""Decode camera RAW files into linear, unbalanced camera RGB via LibRaw."""

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt
import rawpy

from real_fast_filmlab.core.converter import FloatImage
from real_fast_filmlab.exceptions import RawLoadError

READ_CHUNK = 1024 * 1024
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
    """Linear camera RGB in [0, 1] plus the camera colour matrix (XYZ -> camera).

    `exposure` is log10(shutter x ISO / aperture^2) of the scan, None when the
    RAW does not say: scans of one roll taken with different exposures have
    their densities shifted by exactly the difference.
    """

    rgb: FloatImage
    xyz_to_cam: npt.NDArray[np.float64]
    source: Path
    exposure: float | None = None

    def take_rgb(self) -> FloatImage:
        """Hand the pixel buffer over (no copy); this object keeps an empty one.

        Lets a consumer work in place and free the frame as soon as it is done.
        """
        rgb, self.rgb = self.rgb, np.empty((0, 0, 3), np.float32)
        return rgb


def load(
    path: Path,
    *,
    half_size: bool = False,
    balance: tuple[float, float, float] | None = None,
) -> RawImage:
    """Decode a RAW without white balance, gamma or auto brightness.

    The picture is decoded as the sensor recorded it (`user_flip=0`): the
    camera's orientation flag is arbitrary when the camera points down at
    the film, so the orientation is set once per scanning setup with `rotate`
    and `mirror`; outputs use Orientation=1. The values keep the sensor's
    scale (`adjust_maximum_thr=0`): LibRaw would otherwise rescale a file to
    its own brightest pixel, which shifts the densities from frame to frame.

    `balance` is the film base as the sensor sees it (transmission per
    channel, see `base_balance`). The channels are brought to the same level
    for the demosaicing and scaled back afterwards: reconstructing a weak
    channel next to strong ones leaves errors as large as the weak signal
    itself, which show as single wrong pixels after the inversion. Values
    stay as recorded up to the film base; brighter ones (bare light beside
    the film) may be limited in the raised channels.
    """
    gains = _balance_gains(balance)
    try:
        with rawpy.imread(str(path)) as raw:
            rgb16 = raw.postprocess(
                output_bps=16,
                gamma=(1, 1),
                no_auto_bright=True,
                use_camera_wb=False,
                use_auto_wb=False,
                user_wb=[gains[0], gains[1], gains[2], gains[1]],
                output_color=rawpy.ColorSpace.raw,  # type: ignore[attr-defined]  # rawpy ships no stubs
                half_size=half_size,
                user_flip=0,
                adjust_maximum_thr=0.0,
            )
            matrix = np.array(raw.rgb_xyz_matrix[:3], dtype=np.float64)
            exposure = _scan_exposure(getattr(raw, "other", None))
    except (
        rawpy.LibRawUnsufficientMemoryError,  # type: ignore[attr-defined]  # rawpy ships no stubs
        rawpy.LibRawMemPoolOverflowError,  # type: ignore[attr-defined]  # rawpy ships no stubs
    ) as exc:
        # not the file's fault: the machine ran out of memory
        raise MemoryError(f"cannot read {path.name}: {exc}") from exc
    except rawpy.LibRawIOError as exc:  # type: ignore[attr-defined]  # rawpy ships no stubs
        # LibRaw reports every read problem the same way, without errno: a
        # plain read tells an unreadable file (permission, I/O error, drive
        # gone) from a truncated or corrupt one
        cause = _read_failure(path) or exc
        raise RawLoadError(f"cannot read {path.name}: {cause}") from cause
    except (rawpy.LibRawError, OSError, ValueError) as exc:  # type: ignore[attr-defined]  # rawpy ships no stubs
        raise RawLoadError(f"cannot read {path.name}: {exc}") from exc
    if not np.any(matrix):
        matrix = np.eye(3)
    rgb = rgb16.astype(np.float32)
    rgb *= (np.float32(1.0 / 65535.0) / np.asarray(gains, np.float32)).astype(
        np.float32
    )
    return RawImage(rgb=rgb, xyz_to_cam=matrix, source=path, exposure=exposure)


MAX_BALANCE_GAIN = 16.0  # a channel is raised by at most four stops


def base_balance(d_min: tuple[float, float, float]) -> tuple[float, float, float]:
    """The film base's transmission per channel, for `load(balance=...)`."""
    r, g, b = (float(10.0**-value) for value in d_min)
    return (r, g, b)


def _balance_gains(
    balance: tuple[float, float, float] | None,
) -> tuple[float, float, float]:
    """Gain per channel that lifts every channel to the strongest one.

    The strongest channel keeps gain 1, so nothing up to the film base can
    exceed the sensor's range. No balance, or one that is not usable: 1, 1, 1.
    """
    if balance is None:
        return (1.0, 1.0, 1.0)
    levels = np.asarray(balance, np.float64)
    if not np.all(np.isfinite(levels)) or np.any(levels <= 0.0):
        return (1.0, 1.0, 1.0)
    gains = np.minimum(levels.max() / levels, MAX_BALANCE_GAIN)
    return (float(gains[0]), float(gains[1]), float(gains[2]))


def _scan_exposure(other: object) -> float | None:
    """log10(shutter x ISO / aperture^2) from the RAW's shooting data.

    None without a shutter time or ISO value. A missing aperture (manual
    lens) counts as 1: such a lens is not changed between the frames of a
    roll without the camera knowing either.
    """

    def positive(name: str) -> float | None:
        try:
            value = float(getattr(other, name))
        except (AttributeError, TypeError, ValueError):
            return None
        return value if math.isfinite(value) and value > 0.0 else None

    shutter, iso = positive("shutter_speed"), positive("iso_speed")
    if shutter is None or iso is None:
        return None
    aperture = positive("aperture") or 1.0
    return math.log10(shutter * iso / (aperture * aperture))


def _read_failure(path: Path) -> OSError | None:
    """The OS error of reading `path` completely (1 MiB chunks), else None."""
    try:
        with path.open("rb") as handle:
            while handle.read(READ_CHUNK):
                pass
    except OSError as exc:
        return exc
    return None
