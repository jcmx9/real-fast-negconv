"""Pass 2 for one file: convert the negative and write DNG, TIFF and JPEG."""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt
from PIL import Image

from real_fast_negconv import __version__
from real_fast_negconv.config import Config
from real_fast_negconv.core.analyzer import FrameAnalysis
from real_fast_negconv.core.color import (
    apply_matrix,
    camera_to_srgb_matrix,
    srgb_encode,
)
from real_fast_negconv.core.converter import (
    FloatImage,
    ToneParams,
    apply_black_point,
    black_point,
    density_to_linear,
    to_density,
    to_mono,
)
from real_fast_negconv.core.crossover import crossover_note
from real_fast_negconv.core.geometry import Rect, deskew, orient
from real_fast_negconv.core.look import apply_look_params
from real_fast_negconv.core.metadata import describe
from real_fast_negconv.core.rolls import RollDecision
from real_fast_negconv.fileio import raw_loader
from real_fast_negconv.fileio.dng_writer import write_dng
from real_fast_negconv.fileio.exiftool import ExifTool
from real_fast_negconv.fileio.raster_writer import write_jpeg, write_tiff
from real_fast_negconv.fileio.raw_loader import RawImage

log = logging.getLogger(__name__)

CROP_DETAIL = "crop_detail"  # LogRecord flag: console shows the line from -v on

OUTPUT_SUFFIXES = (".dng", ".tif", ".jpg")
FALLBACK_CAMERA = "real-fast-negconv"
PREVIEW_LONG_EDGE = 1024


@dataclass(frozen=True)
class OutputPaths:
    """Target files of one frame; `dng` is None when DNG output is disabled."""

    dng: Path | None
    tiff: Path
    jpeg: Path


@dataclass(frozen=True)
class Developed:
    """Result of developing one frame."""

    linear: FloatImage
    crop: Rect
    srgb: FloatImage
    description: str


def assign_outputs(
    stems: Sequence[str], photos_dir: Path, with_dng: bool
) -> list[OutputPaths]:
    """Collision-free output names; never overwrites existing files."""
    taken: set[str] = set()
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
                tiff=photos_dir / f"{name}.tif",
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
    params = ToneParams(
        d_min=decision.d_min_used,
        d_white=analysis.d_white,
        gamma=gamma,
        crossover=decision.crossover,
    )
    xyz_to_cam = raw.xyz_to_cam
    linear = density_to_linear(to_density(raw.take_rgb(), inplace=True), params)
    linear = deskew(linear, analysis.geometry.angle_deg)
    crop = analysis.geometry.crop_rect((linear.shape[0], linear.shape[1]))
    linear, crop = orient(linear, crop, cfg.rotate, cfg.mirror)
    # the DNG keeps values outside 0-1; TIFF/JPEG use them limited to 0-1
    black = black_point(linear, crop.inner(cfg.measure_inset))
    apply_black_point(linear, black, clip=False)
    if decision.is_bw:
        srgb = srgb_encode(to_mono(linear[crop.slices()], clip=True), inplace=True)
        linear = to_mono(linear)
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
        confident=analysis.geometry.confident,
        aspect=analysis.geometry.aspect,
        crossover=crossover_note(decision.crossover, decision.crossover_source),
        reason=analysis.geometry.reason,
    )
    return Developed(linear=linear, crop=crop, srgb=srgb, description=description)


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
) -> str:
    """Load, develop and write all outputs of one file; returns the description.

    Memory: the RAW buffer is consumed by develop, the full-size linear image
    is dropped right after the DNG, before TIFF/JPEG are produced.
    """
    raw = raw_loader.load(source)
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
        analysis.geometry.reason,
        extra={CROP_DETAIL: True},
    )
    description = developed.description
    del developed
    camera = (
        exiftool.camera_name(source) if exiftool.available else None
    ) or FALLBACK_CAMERA
    camera = camera.encode("ascii", "replace").decode("ascii")
    written: list[Path] = []
    try:
        if outputs.dng is not None:
            if linear.ndim == 2:
                linear = np.repeat(linear[..., None], 3, axis=2)
            write_dng(
                outputs.dng,
                linear,
                crop=crop,
                preview=make_preview(srgb),
                xyz_to_cam=matrix,
                camera=camera,
                description=description,
                integer=cfg.dng_finder_preview,
            )
            written.append(outputs.dng)
        del linear
        corrected = apply_look_params(srgb, decision.look)
        write_tiff(outputs.tiff, corrected, description=description)
        written.append(outputs.tiff)
        write_jpeg(
            outputs.jpeg,
            corrected,
            description=description,
            quality=cfg.jpeg_quality,
        )
        written.append(outputs.jpeg)
        if exiftool.available and not exiftool.copy_metadata(source, written):
            log.warning("%s: EXIF metadata could not be copied", source.name)
    except BaseException:
        for path in written:
            path.unlink(missing_ok=True)
        raise
    return description
