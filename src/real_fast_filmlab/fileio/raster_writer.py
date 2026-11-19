"""Write sRGB-encoded TIFF (16-bit) and JPEG (8-bit) files."""

import io
import struct
from functools import cache
from pathlib import Path

import numpy as np
import numpy.typing as npt
import tifffile
from PIL import Image, ImageCms

from real_fast_filmlab import __version__
from real_fast_filmlab.core.converter import FloatImage
from real_fast_filmlab.exceptions import EncodeError
from real_fast_filmlab.fileio.atomic import atomic_write

CHUNK_ROWS = 256
ICC_PROFILE_DATE = (2026, 1, 1, 0, 0, 0)  # year, month, day, hour, minute, second
GREY_CURVE_ENTRIES = 1024
ICC_D50 = (0.9642, 1.0, 0.8249)  # profile connection space illuminant
JPEG_FULL_CHROMA = 0  # Pillow: 4:4:4, colour at full resolution


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
    profile: bytes = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    date = struct.pack(">6H", *ICC_PROFILE_DATE)
    return profile[:24] + date + profile[36:]


def _s15_fixed16(*values: float) -> bytes:
    return b"".join(struct.pack(">i", round(value * 65536)) for value in values)


def _icc_tag(signature: bytes, payload: bytes) -> bytes:
    data = signature + bytes(4) + payload
    return data + bytes(-len(data) % 4)


@cache
def grey_icc_profile() -> bytes:
    """ICC profile (v2) for a grey image with the sRGB tone curve.

    Without a profile, colour-managed programs assume their own grey space
    and show black-and-white pictures darker or lighter than the colour
    files. Built by hand (LittleCMS has no ready-made grey profile): header,
    description, D50 white point, tone curve as a table, copyright.
    """
    steps = np.arange(GREY_CURVE_ENTRIES, dtype=np.float64) / (GREY_CURVE_ENTRIES - 1)
    linear = np.where(steps <= 0.04045, steps / 12.92, ((steps + 0.055) / 1.055) ** 2.4)
    curve = np.rint(linear * 65535.0).astype(">u2").tobytes()
    name = b"sRGB tone curve, grey\x00"
    tags = [
        (
            b"desc",
            _icc_tag(
                b"desc", struct.pack(">I", len(name)) + name + bytes(4 + 4 + 2 + 1 + 67)
            ),
        ),
        (b"wtpt", _icc_tag(b"XYZ ", _s15_fixed16(*ICC_D50))),
        (
            b"kTRC",
            _icc_tag(b"curv", struct.pack(">I", GREY_CURVE_ENTRIES) + curve),
        ),
        (b"cprt", _icc_tag(b"text", b"No copyright, use freely\x00")),
    ]
    offset = 128 + 4 + 12 * len(tags)
    table = struct.pack(">I", len(tags))
    body = b""
    for signature, data in tags:
        table += signature + struct.pack(">II", offset + len(body), len(data))
        body += data
    header = (
        struct.pack(">I", offset + len(body))
        + bytes(4)  # preferred CMM
        + struct.pack(">I", 0x02100000)  # version 2.1
        + b"mntrGRAYXYZ "
        + struct.pack(">6H", *ICC_PROFILE_DATE)
        + b"acsp"
        + bytes(4 + 4 + 4 + 4 + 8 + 4)  # platform ... rendering intent
        + _s15_fixed16(*ICC_D50)
    )
    return header + bytes(128 - len(header)) + table + body


def write_tiff(path: Path, srgb: FloatImage, *, description: str) -> None:
    """Write a 16-bit TIFF with its profile: sRGB, or grey with the sRGB curve."""
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
            iccprofile=srgb_icc_profile() if is_rgb else grey_icc_profile(),
            metadata=None,
            description=ascii_description,
            software=f"real-fast-filmlab {__version__}",
        )

    atomic_write(path, write, create_parents=False, exclusive=True)


def write_jpeg(
    path: Path, srgb: FloatImage, *, description: str, quality: int = 95
) -> None:
    """Write an 8-bit JPEG with its profile: sRGB, or grey with the sRGB curve.

    Colour is stored at full resolution (4:4:4): the usual halving of the
    colour channels smears colour grain and fine coloured detail.

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
                subsampling=JPEG_FULL_CHROMA,
            )
        else:
            image.save(
                buffer,
                format="JPEG",
                quality=quality,
                exif=exif_bytes,
                icc_profile=grey_icc_profile(),
            )
    except (OSError, ValueError) as exc:
        raise EncodeError(f"cannot encode {path.name}: {exc}") from exc
    encoded = buffer.getvalue()
    del buffer

    def write(tmp: Path) -> None:
        tmp.write_bytes(encoded)

    atomic_write(path, write, create_parents=False, exclusive=True)
