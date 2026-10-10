"""Write sRGB-encoded TIFF (16-bit) and JPEG (8-bit) files."""

import io
import struct
from functools import cache
from pathlib import Path

import numpy as np
import numpy.typing as npt
import tifffile
from PIL import Image, ImageCms

from real_fast_negconv import __version__
from real_fast_negconv.core.converter import FloatImage
from real_fast_negconv.exceptions import EncodeError
from real_fast_negconv.fileio.atomic import atomic_write

CHUNK_ROWS = 256
ICC_PROFILE_DATE = (2026, 1, 1, 0, 0, 0)  # year, month, day, hour, minute, second


def quantize[T: (np.uint8, np.uint16)](
    srgb: FloatImage, dtype: type[T]
) -> npt.NDArray[T]:
    """Map [0, 1] (NaN -> 0, +inf -> 1) to the full integer range, in row chunks.

    Only one output array plus a small chunk buffer is allocated, never several
    full-size float temporaries.
    """
    scale = np.float32(np.iinfo(dtype).max)
    out = np.empty(srgb.shape, dtype)
    for start in range(0, srgb.shape[0], CHUNK_ROWS):
        rows = slice(start, start + CHUNK_ROWS)
        chunk = np.nan_to_num(srgb[rows], nan=0.0, posinf=1.0, neginf=0.0)
        np.clip(chunk, 0.0, 1.0, out=chunk)
        chunk *= scale
        np.rint(chunk, out=chunk)
        out[rows] = chunk
    return out


@cache
def srgb_icc_profile() -> bytes:
    """ICC profile bytes for sRGB with a fixed creation date (reproducible files).

    LittleCMS writes the current time into the header (bytes 24-35); the
    profile carries no MD5 profile ID, so the date can be replaced as is.
    """
    profile: bytes = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()  # type: ignore[no-untyped-call]  # Pillow stubs leave ImageCmsProfile.tobytes untyped
    date = struct.pack(">6H", *ICC_PROFILE_DATE)
    return profile[:24] + date + profile[36:]


def write_tiff(path: Path, srgb: FloatImage, *, description: str) -> None:
    """Write a 16-bit TIFF; RGB images get an embedded sRGB profile."""
    data = quantize(srgb, np.uint16)
    is_rgb = data.ndim == 3
    ascii_description = description.encode("ascii", "replace").decode("ascii")

    def write(tmp: Path) -> None:
        tifffile.imwrite(
            tmp,
            data,
            photometric="rgb" if is_rgb else "minisblack",
            compression="zlib",
            predictor=True,
            iccprofile=srgb_icc_profile() if is_rgb else None,
            metadata=None,
            description=ascii_description,
            software=f"real-fast-negconv {__version__}",
        )

    atomic_write(path, write)


def write_jpeg(
    path: Path, srgb: FloatImage, *, description: str, quality: int = 95
) -> None:
    """Write an 8-bit JPEG; RGB images get an embedded sRGB profile.

    The image is encoded in memory first, so an encoder failure (EncodeError,
    a problem of this file's data) is told apart from an OS error while
    writing the file (disk full, permissions).
    """
    data = quantize(srgb, np.uint8)
    image = Image.fromarray(data)
    exif = Image.Exif()
    exif[0x010E] = description.encode("ascii", "replace").decode("ascii")
    exif_bytes = exif.tobytes()
    buffer = io.BytesIO()
    try:
        if data.ndim == 3:
            image.save(
                buffer,
                format="JPEG",
                quality=quality,
                exif=exif_bytes,
                icc_profile=srgb_icc_profile(),
            )
        else:
            image.save(buffer, format="JPEG", quality=quality, exif=exif_bytes)
    except (OSError, ValueError) as exc:
        raise EncodeError(f"cannot encode {path.name}: {exc}") from exc
    encoded = buffer.getvalue()
    del buffer

    def write(tmp: Path) -> None:
        tmp.write_bytes(encoded)

    atomic_write(path, write)
