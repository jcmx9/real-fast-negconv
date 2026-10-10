"""Write demosaiced, scene-linear images as float16 or uint16 LinearRaw DNG."""

from pathlib import Path

import numpy as np
import numpy.typing as npt
import tifffile

from real_fast_negconv import __version__
from real_fast_negconv.core.converter import FloatImage
from real_fast_negconv.core.geometry import Rect
from real_fast_negconv.fileio.atomic import atomic_write

PHOTOMETRIC_LINEAR_RAW = 34892
PREDICTOR_FLOATINGPOINT_X2 = 34894
ILLUMINANT_D65 = 21
RATIONAL_DENOMINATOR = 10000
UINT16_MAX = 65535.0
FLOAT16_MAX = 65504.0
CHUNK_ROWS = 256

type DngTag = tuple[int, str, int, object, bool]


def write_dng(
    path: Path,
    linear: FloatImage,
    *,
    crop: Rect,
    xyz_to_cam: npt.NDArray[np.floating],
    camera: str,
    description: str,
    preview: npt.NDArray[np.uint8],
    integer: bool = False,
) -> None:
    """Write `linear` (H, W, 3, black = 0.0, white = 1.0) as DNG with a preview.

    The crop travels as embedded Camera Raw XMP so it can be reset in the editor;
    the LinearRaw main image is a SubIFD (macOS only thumbnails IFD0).
    `integer=False` stores float16 with Deflate and keeps values outside 0-1
    (highlights above the white point, shadows below the black point);
    `integer=True` stores uncompressed uint16 limited to 0-1 (BlackLevel 0,
    WhiteLevel 65535), the only variant macOS ImageIO renders (Finder / Quick
    Look previews). The 8-bit preview comes from the 0-1 limited sRGB image.
    """
    if linear.ndim != 3 or linear.shape[2] != 3:
        raise ValueError(f"DNG needs an RGB image, got shape {linear.shape}")
    if preview.ndim != 3 or preview.shape[2] != 3 or preview.dtype != np.uint8:
        raise ValueError("preview must be an 8-bit RGB image")
    data = _to_uint16(linear) if integer else _to_float16(linear)
    tags = _dng_tags(xyz_to_cam, camera, _crop_xmp(crop, linear.shape[:2]))
    ascii_description = description.encode("ascii", "replace").decode("ascii")

    def write(tmp: Path) -> None:
        with tifffile.TiffWriter(tmp) as tif:
            tif.write(
                preview,
                photometric="rgb",
                subfiletype=1,
                subifds=1,
                extratags=tags,
                metadata=None,
                description=ascii_description,
                software=f"real-fast-negconv {__version__}",
            )
            if integer:
                tif.write(
                    data,
                    photometric=PHOTOMETRIC_LINEAR_RAW,
                    subfiletype=0,
                    tile=(256, 256),
                    extratags=[
                        (50714, "H", 3, (0, 0, 0), True),  # BlackLevel
                        (50717, "I", 3, (65535, 65535, 65535), True),  # WhiteLevel
                    ],
                    metadata=None,
                )
            else:
                tif.write(
                    data,
                    photometric=PHOTOMETRIC_LINEAR_RAW,
                    subfiletype=0,
                    compression=8,
                    compressionargs={"level": 6},
                    predictor=PREDICTOR_FLOATINGPOINT_X2,
                    tile=(256, 256),
                    metadata=None,
                )

    atomic_write(path, write)


def _to_float16(linear: FloatImage) -> npt.NDArray[np.float16]:
    """Replace NaN/inf and limit to the float16 range [-65504, 65504].

    Values below 0 and above 1 are kept. Works in row chunks (no full float
    copy).
    """
    out = np.empty(linear.shape, np.float16)
    for start in range(0, linear.shape[0], CHUNK_ROWS):
        rows = slice(start, start + CHUNK_ROWS)
        chunk = np.nan_to_num(
            linear[rows], nan=0.0, posinf=FLOAT16_MAX, neginf=-FLOAT16_MAX
        )
        np.clip(chunk, -FLOAT16_MAX, FLOAT16_MAX, out=chunk)
        out[rows] = chunk
    return out


def _to_uint16(linear: FloatImage) -> npt.NDArray[np.uint16]:
    """Quantize white = 1.0 to 65535, converting in row chunks (no full float copy)."""
    out = np.empty(linear.shape, np.uint16)
    for start in range(0, linear.shape[0], CHUNK_ROWS):
        chunk = np.nan_to_num(
            linear[start : start + CHUNK_ROWS], nan=0.0, posinf=1.0, neginf=0.0
        )
        np.clip(chunk, 0.0, 1.0, out=chunk)
        chunk *= UINT16_MAX
        np.rint(chunk, out=chunk)
        out[start : start + CHUNK_ROWS] = chunk
    return out


def _crop_xmp(crop: Rect, shape: tuple[int, int]) -> bytes:
    """Camera Raw settings packet with the crop normalized to the stored image."""
    height, width = shape
    top, left = crop.top / height, crop.left / width
    bottom, right = crop.bottom / height, crop.right / width
    packet = (
        '<?xpacket begin="\ufeff" id="W5M0MpCehiHzreSzNTczkc9d"?>\n'
        '<x:xmpmeta xmlns:x="adobe:ns:meta/">\n'
        '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">\n'
        '<rdf:Description rdf:about=""'
        ' xmlns:crs="http://ns.adobe.com/camera-raw-settings/1.0/"'
        ' crs:ProcessVersion="11.0"'
        ' crs:HasSettings="True"'
        ' crs:HasCrop="True"'
        f' crs:CropTop="{top:.6f}"'
        f' crs:CropLeft="{left:.6f}"'
        f' crs:CropBottom="{bottom:.6f}"'
        f' crs:CropRight="{right:.6f}"'
        ' crs:CropAngle="0"'
        ' crs:AlreadyApplied="False"/>\n'
        "</rdf:RDF>\n"
        "</x:xmpmeta>\n"
        '<?xpacket end="w"?>'
    )
    return packet.encode("utf-8")


def _srational(values: npt.NDArray[np.floating]) -> list[int]:
    out: list[int] = []
    for value in np.asarray(values, np.float64).ravel():
        out.extend((round(float(value) * RATIONAL_DENOMINATOR), RATIONAL_DENOMINATOR))
    return out


def _dng_tags(
    xyz_to_cam: npt.NDArray[np.floating], camera: str, xmp: bytes
) -> list[DngTag]:
    return [
        (50706, "B", 4, (1, 4, 0, 0), True),  # DNGVersion
        (50707, "B", 4, (1, 4, 0, 0), True),  # DNGBackwardVersion
        (50708, "s", 0, camera, True),  # UniqueCameraModel
        (50721, "2i", 9, _srational(xyz_to_cam), True),  # ColorMatrix1
        (50778, "H", 1, ILLUMINANT_D65, True),  # CalibrationIlluminant1
        (50728, "2I", 3, (1, 1, 1, 1, 1, 1), True),  # AsShotNeutral
        (50730, "2i", 1, (0, 1), True),  # BaselineExposure
        (274, "H", 1, 1, True),  # Orientation
        (700, "B", len(xmp), xmp, True),  # XMP packet
    ]
