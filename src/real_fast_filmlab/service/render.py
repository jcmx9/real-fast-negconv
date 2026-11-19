"""Pass 2 for one file: convert the negative and write DNG, TIFF and JPEG."""

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import numpy.typing as npt
from PIL import Image

from real_fast_filmlab import __version__
from real_fast_filmlab.config import Config
from real_fast_filmlab.core.analyzer import FrameAnalysis
from real_fast_filmlab.core.color import (
    apply_matrix,
    camera_to_srgb_matrix,
    srgb_encode,
)
from real_fast_filmlab.core.converter import (
    FloatImage,
    ToneParams,
    apply_black_point,
    black_point,
    density_to_linear,
    mono_weights,
    to_density,
    to_mono,
)
from real_fast_filmlab.core.crossover import crossover_note
from real_fast_filmlab.core.geometry import (
    PICTURE_INTERPOLATION,
    Rect,
    deskew,
    orient,
)
from real_fast_filmlab.core.look import apply_look_linear, apply_look_params
from real_fast_filmlab.core.metadata import describe
from real_fast_filmlab.core.rolls import RollDecision
from real_fast_filmlab.fileio import flatfield, raw_loader
from real_fast_filmlab.fileio.dng_writer import write_dng
from real_fast_filmlab.fileio.exiftool import ExifTool
from real_fast_filmlab.fileio.raster_writer import write_jpeg, write_tiff
from real_fast_filmlab.fileio.raw_loader import RawImage

log = logging.getLogger(__name__)

CROP_DETAIL = "crop_detail"  # LogRecord flag: console shows the line from -v on

OUTPUT_SUFFIXES = (".dng", ".tif", ".jpg")
FALLBACK_CAMERA = "real-fast-filmlab"
PREVIEW_LONG_EDGE = 1024


@dataclass(frozen=True)
class OutputPaths:
    """Target files of one frame; `dng`/`tiff` are None when switched off."""

    dng: Path | None
    tiff: Path | None
    jpeg: Path


@dataclass(frozen=True)
class Developed:
    """Result of developing one frame."""

    linear: FloatImage
    crop: Rect
    srgb: FloatImage
    description: str


def assign_outputs(
    stems: Sequence[str],
    photos_dir: Path,
    with_dng: bool,
    with_tiff: bool = True,
    taken: set[str] | None = None,
) -> list[OutputPaths]:
    """Output names that are free now and differ from each other.

    `taken` (lower-case names already given out; the new ones are added)
    lets a later call keep away from the names of an earlier one. A name
    is not reserved by this: the files are written exclusively, and a name
    that was taken in the meantime is given up (see batch).
    """
    taken = set() if taken is None else taken
    result: list[OutputPaths] = []
    for stem in stems:
        n = 1
        while True:
            name = stem if n == 1 else f"{stem}_{n}"
            exists = any((photos_dir / f"{name}{s}").exists() for s in OUTPUT_SUFFIXES)
            if name.lower() not in taken and not exists:
                break
            n += 1
        taken.add(name.lower())
        result.append(
            OutputPaths(
                dng=photos_dir / f"{name}.dng" if with_dng else None,
                tiff=photos_dir / f"{name}.tif" if with_tiff else None,
                jpeg=photos_dir / f"{name}.jpg",
            )
        )
    return result


def develop(
    raw: RawImage,
    analysis: FrameAnalysis,
    decision: RollDecision,
    cfg: Config,
) -> Developed:
    """Negative -> neutral positive: density maths, deskew, orientation, crop.

    `linear` (for the DNG) keeps values below the black point and above the
    white point; `srgb` (for TIFF/JPEG) is built from values limited to 0-1.

    Consumes `raw`: its pixel buffer is taken over and converted in place, so
    the original frame is freed as soon as deskew/orientation replace it.
    """
    gamma = cfg.gamma_bw if decision.is_bw else cfg.gamma_color
    geometry = decision.geometry or analysis.geometry
    params = ToneParams(
        d_min=decision.d_min_used,
        d_white=decision.d_white_used or analysis.d_white,
        gamma=gamma,
        crossover=decision.crossover,
    )
    xyz_to_cam = raw.xyz_to_cam
    # rotate the densities, not the positive: dust and the holder are a few
    # density units from the picture there, but thousands of times brighter
    # in the unclipped positive, where a sharp filter would ring visibly
    density = deskew(
        to_density(raw.take_rgb(), inplace=True),
        geometry.angle_deg,
        interpolation=PICTURE_INTERPOLATION,
    )
    linear = density_to_linear(density, params)
    crop = geometry.crop_rect((linear.shape[0], linear.shape[1]))
    linear, crop = orient(linear, crop, cfg.rotate, cfg.mirror)
    # the DNG keeps values outside 0-1; TIFF/JPEG use them limited to 0-1
    black = black_point(linear, crop.inner(cfg.measure_inset))
    apply_black_point(linear, black, clip=False)
    if decision.is_bw:
        # average first, limit afterwards (srgb_encode clips): the BW DNG,
        # rendered, then gives exactly these values
        weights = mono_weights(decision.d_min_used)
        srgb = srgb_encode(to_mono(linear[crop.slices()], weights), inplace=True)
        linear = to_mono(linear, weights)
    else:
        cropped = apply_matrix(
            linear[crop.slices()], camera_to_srgb_matrix(xyz_to_cam), clip_input=True
        )
        srgb = srgb_encode(cropped, inplace=True)
    description = describe(
        version=__version__,
        is_bw=decision.is_bw,
        d_min_used=decision.d_min_used,
        fallback_applied=decision.fallback_applied,
        confident=geometry.confident,
        aspect=geometry.aspect,
        crossover=crossover_note(decision.crossover, decision.crossover_source),
        reason=geometry.reason,
    )
    return Developed(linear=linear, crop=crop, srgb=srgb, description=description)


SHARPEN_SIGMA = 1.0  # pixels: fine detail, not edges
SHARPEN_AMOUNT = 0.5


def sharpen(srgb: FloatImage) -> None:
    """Mild unsharp mask on the sRGB picture, in place (JPEG only).

    out = x + SHARPEN_AMOUNT * (x - blur(x, SHARPEN_SIGMA)), limited to 0-1.
    TIFF and DNG stay as developed: they are meant for further editing.
    """
    blurred = cv2.GaussianBlur(srgb, (0, 0), SHARPEN_SIGMA)
    cv2.addWeighted(srgb, 1.0 + SHARPEN_AMOUNT, blurred, -SHARPEN_AMOUNT, 0.0, dst=srgb)
    np.clip(srgb, 0.0, 1.0, out=srgb)


def make_preview(srgb: FloatImage) -> npt.NDArray[np.uint8]:
    """8-bit RGB preview of a neutral sRGB image, long edge <= PREVIEW_LONG_EDGE."""
    step = max(1, max(srgb.shape[:2]) // (2 * PREVIEW_LONG_EDGE))
    small = srgb[::step, ::step]  # view: no full-size copy
    scaled = np.clip(small, 0.0, 1.0).astype(np.float32, copy=False)  # one copy
    scaled *= np.float32(255.0)
    np.round(scaled, out=scaled)
    data = scaled.astype(np.uint8)
    del scaled
    height, width = data.shape[:2]
    scale = PREVIEW_LONG_EDGE / max(height, width)
    if scale < 1.0:
        size = (max(1, round(width * scale)), max(1, round(height * scale)))
        data = np.asarray(
            Image.fromarray(data).resize(size, Image.Resampling.LANCZOS),
            dtype=np.uint8,
        )
    if data.ndim == 2:
        data = np.repeat(data[..., None], 3, axis=2)
    return data


def render(
    source: Path,
    analysis: FrameAnalysis,
    decision: RollDecision,
    cfg: Config,
    outputs: OutputPaths,
    exiftool: ExifTool,
    on_written: Callable[[Path], None] | None = None,
) -> str:
    """Load, develop and write all outputs of one file; returns the description.

    An output is never written over an existing file (FileExistsError; the
    outputs written before are removed). `on_written` is told each output
    as soon as it has its name.

    Memory: the RAW buffer is consumed by develop, the full-size linear image
    is dropped right after the DNG, before TIFF/JPEG are produced.
    """
    raw = raw_loader.load(source, balance=raw_loader.base_balance(decision.d_min_used))
    flatfield.apply(raw, cfg.flatfield)
    matrix = raw.xyz_to_cam
    developed = develop(raw, analysis, decision, cfg)
    del raw
    linear, crop, srgb = developed.linear, developed.crop, developed.srgb
    note = crossover_note(decision.crossover, decision.crossover_source)
    log.info(
        "%s: crop %d\N{MULTIPLICATION SIGN}%d%s \N{EM DASH} %s",
        source.name,
        crop.width,
        crop.height,
        f", crossover {note}" if note else "",
        (decision.geometry or analysis.geometry).reason,
        extra={CROP_DETAIL: True},
    )
    description = developed.description
    del developed
    camera = (
        exiftool.camera_name(source) if exiftool.available else None
    ) or FALLBACK_CAMERA
    camera = camera.encode("ascii", "replace").decode("ascii")
    # the same gentle correction for all three outputs; the DNG keeps the
    # values outside 0-1 (see apply_look_linear)
    corrected = apply_look_params(srgb, decision.look)
    del srgb
    written: list[Path] = []

    def done(path: Path) -> None:
        written.append(path)
        if on_written is not None:
            on_written(path)

    try:
        if outputs.dng is not None:
            if decision.is_bw:
                apply_look_linear(linear, decision.look)
            else:
                apply_look_linear(linear, decision.look, camera_to_srgb_matrix(matrix))
            if linear.ndim == 2:
                linear = np.repeat(linear[..., None], 3, axis=2)
            write_dng(
                outputs.dng,
                linear,
                crop=crop,
                preview=make_preview(corrected),
                xyz_to_cam=matrix,
                camera=camera,
                description=description,
                integer=cfg.dng_finder_preview,
            )
            done(outputs.dng)
        del linear
        if outputs.tiff is not None:
            write_tiff(outputs.tiff, corrected, description=description)
            done(outputs.tiff)
        if cfg.jpeg_sharpen:
            sharpen(corrected)
        write_jpeg(
            outputs.jpeg,
            corrected,
            description=description,
            quality=cfg.jpeg_quality,
        )
        done(outputs.jpeg)
        if exiftool.available and not exiftool.copy_metadata(source, written):
            log.warning("%s: EXIF metadata could not be copied", source.name)
    except BaseException:
        for path in written:
            path.unlink(missing_ok=True)
        raise
    return description
