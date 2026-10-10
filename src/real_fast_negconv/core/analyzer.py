"""Frame detection (OpenCV + projection profiles) and per-frame density statistics."""

import math
import warnings
from dataclasses import dataclass, field, replace

import cv2
import numpy as np
import numpy.typing as npt

from real_fast_negconv.core.color import (
    apply_matrix,
    camera_to_srgb_matrix,
    srgb_encode,
)
from real_fast_negconv.core.converter import (
    MIN_SPREAD,
    NO_CROSSOVER,
    FloatImage,
    ToneParams,
    Triple,
    apply_black_point,
    black_point,
    density_to_linear,
    normalize_density,
    to_density,
    to_mono,
)
from real_fast_negconv.core.crossover import (
    EMPTY_SAMPLE,
    DensitySample,
    sample_window,
)
from real_fast_negconv.core.geometry import (
    MEASURE_INSET,
    FrameGeometry,
    Rect,
    deskew,
)
from real_fast_negconv.core.look import LookStats, inner_sample, measure_sampled

ASPECTS: dict[str, float] = {"1:1": 1.0, "6x7": 1.24, "6x4.5": 1.35, "3:2": 1.5}
PREVIEW_EDGE = 1000
EDGE_BAND_FRACTION = 0.6
GAP_FRACTION = 0.9
EDGE_FACTOR = 2.5  # border: edge score >= this x the segment's typical score
EDGE_WINDOW = 0.06  # search window around a segment end, fraction of the axis
# Deskew from the outer frame edges
EDGE_BAND = 0.04  # band per side of each edge, x longer side of the rough frame
COARSE_STEP = 0.25  # degrees between angles of the coarse search
FINE_STEP = 0.02  # degrees between angles of the fine search around the coarse best
MIN_GAIN = 0.01  # below this score gain over 0 deg: no edge, minAreaRect fallback
# Translucent holder strips
HOLDER_P10 = 0.8  # holder line: 10th percentile >= this x holder_min above base
HOLDER_STEP = 0.005  # base-like line within this fraction of the long edge
# Bare-light strips along the image border
BORDER_MARGIN = 0.02  # border ignored for the first base estimate, x long edge
BARE_GAP = 0.2  # density below the first base estimate: bare light, not film
# Colour or BW: small coloured details count, so a very high percentile
BW_PERCENTILE = 99.9

BARE_NOTE = "bare light (no film) ignored for the film base"

type BoolMask = npt.NDArray[np.bool_]
type Span = tuple[int, int]


@dataclass(frozen=True)
class AnalyzerSettings:
    """Thresholds for frame detection and statistics."""

    holder_delta: float = 1.8
    holder_min: float = 1.0
    gap_delta: float = 0.10
    gap_std: float = 0.03
    loose_delta: float = 0.15
    loose_std: float = 0.08
    aspect_tol: float = 0.08
    dmin_percentile: float = 0.2
    white_percentile: float = 99.5
    bw_threshold: float = 0.03
    measure_inset: float = MEASURE_INSET
    min_skew_deg: float = 0.2
    max_skew_deg: float = 5.0
    gamma_color: float = 0.6
    gamma_bw: float = 0.65


@dataclass(frozen=True, eq=False)
class LookSample:
    """Preview density on the look grid of the inner window.

    The pixels the look statistics and the black point read (every SAMPLE_STEP-th
    pixel), with the gamma and camera matrix of the neutral preview: enough to
    measure the look statistics again with a crossover exponent.
    """

    density: FloatImage  # (rows, cols, 3)
    gamma: float
    xyz_to_cam: npt.NDArray[np.floating]


EMPTY_LOOK_SAMPLE = LookSample(np.empty((0, 0, 3), np.float32), 1.0, np.eye(3))


@dataclass(frozen=True)
class FrameAnalysis:
    """Everything pass 2 needs to convert one frame.

    `density_sample` (inner window, at most 1 MiB) lets the roll context
    measure the crossover with the film base it finally uses, `look_sample`
    (1/16 of the inner window) re-measures the look statistics with the
    crossover.
    """

    geometry: FrameGeometry
    d_min: Triple
    d_white: Triple
    is_bw: bool
    look_stats: LookStats
    density_sample: DensitySample = field(
        default=EMPTY_SAMPLE, compare=False, repr=False
    )
    look_sample: LookSample = field(
        default=EMPTY_LOOK_SAMPLE, compare=False, repr=False
    )

    @property
    def signature(self) -> tuple[float, float]:
        """Hue of the film base: (R - G, B - G) in density."""
        r, g, b = self.d_min
        return (r - g, b - g)


def analyze(
    rgb: FloatImage,
    settings: AnalyzerSettings,
    xyz_to_cam: npt.NDArray[np.floating] | None = None,
) -> FrameAnalysis:
    """Detect the frame and measure film base, white point, colour/BW and look.

    `xyz_to_cam` is the camera matrix of the RAW (identity when omitted); it
    only affects the look statistics.
    """
    stride = max(1, max(rgb.shape[:2]) // PREVIEW_EDGE)
    density = to_density(rgb[::stride, ::stride])
    geometry, film = detect_frame(density.mean(axis=2), settings)
    density = deskew(density, geometry.angle_deg)
    d_min = _triple(np.percentile(density[film], settings.dmin_percentile, axis=0))
    crop_rect = geometry.crop_rect(film.shape)
    crop = density[crop_rect.slices()]
    inner = density[crop_rect.inner(settings.measure_inset).slices()]
    d_white = _triple(
        np.percentile(inner.reshape(-1, 3), settings.white_percentile, axis=0)
    )
    is_bw = _is_bw(crop, d_min, d_white, settings.bw_threshold)
    look_sample = LookSample(
        density=np.array(inner_sample(crop, settings.measure_inset), copy=True),
        gamma=settings.gamma_bw if is_bw else settings.gamma_color,
        xyz_to_cam=np.eye(3) if xyz_to_cam is None else xyz_to_cam,
    )
    look_stats = _look_stats(look_sample, d_min, d_white, is_bw, NO_CROSSOVER)
    return FrameAnalysis(
        geometry=geometry,
        d_min=d_min,
        d_white=d_white,
        is_bw=is_bw,
        look_stats=look_stats,
        density_sample=sample_window(inner),
        look_sample=look_sample,
    )


def look_stats_for(analysis: FrameAnalysis, crossover: Triple) -> LookStats:
    """Look statistics of the frame's neutral preview with `crossover` applied.

    Without a crossover (or without a look sample) the pass-1 statistics. The
    preview always uses the frame's own film base and colour/BW result from
    pass 1, even when the roll decision later changes them (high-key film
    base, roll majority for colour/BW); the roll group's median dampens the
    difference.
    """
    if crossover == NO_CROSSOVER or analysis.look_sample.density.size == 0:
        return analysis.look_stats
    return _look_stats(
        analysis.look_sample,
        analysis.d_min,
        analysis.d_white,
        analysis.is_bw,
        crossover,
    )


def _look_stats(
    sample: LookSample,
    d_min: Triple,
    d_white: Triple,
    is_bw: bool,
    crossover: Triple,
) -> LookStats:
    """Look statistics on a neutral sRGB preview of the crop.

    Same steps as render.develop, on the look grid of the preview density:
    the frame's own pass-1 d_min/d_white, gamma by its pass-1 colour/BW
    result, crossover, black point on the inner window, camera -> sRGB. Every
    step is per pixel or a statistic over the same grid, so with the same
    film base and colour/BW result this equals measuring on the developed
    preview crop.
    """
    params = ToneParams(d_min, d_white, sample.gamma, crossover=crossover)
    linear = density_to_linear(sample.density.copy(), params)
    window = Rect(0, 0, linear.shape[0], linear.shape[1])
    apply_black_point(linear, black_point(linear, window, step=1))
    if is_bw:
        srgb = srgb_encode(to_mono(linear))
    else:
        rgb = apply_matrix(linear, camera_to_srgb_matrix(sample.xyz_to_cam))
        srgb = srgb_encode(rgb, inplace=True)
    return measure_sampled(srgb)


def detect_frame(
    lum: FloatImage, settings: AnalyzerSettings
) -> tuple[FrameGeometry, BoolMask]:
    """Find the image frame on the film strip and its skew angle.

    A first pass without rotation gives the rough frame; its outer edges give
    the skew angle (film outline as fallback); after rotating, the frame
    detection runs again on the deskewed preview. If the fixed holder
    threshold gives no confident frame, translucent holder strips along the
    image borders are taken out of the film mask and the first pass is
    repeated; its result is used only if it is confident. If the
    rotated pass is not confident but the unrotated one was, the unrotated
    frame is kept (angle 0).
    """
    edge = max(lum.shape)
    bare = _bare_light(lum)
    d_ref = _base_reference(lum, bare)
    threshold = d_ref + settings.holder_delta
    film = _film_mask(lum, threshold, edge, bare)
    rough, edges = _locate(lum, film, d_ref, settings, 0.0)
    notes: list[str] = [BARE_NOTE] if bare.any() else []
    if not rough.confident:
        strips = _holder_strips(lum, d_ref, settings, bare=bare)
        if strips.any():
            narrowed = _film_mask(lum, threshold, edge, strips | bare)
            candidate, candidate_edges = _locate(lum, narrowed, d_ref, settings, 0.0)
            if candidate.confident:
                film, rough, edges = narrowed, candidate, candidate_edges
                notes.append(_holder_note(strips))
    angle = _edge_angle(lum, film, edges, settings)
    source = "frame edges"
    if angle is None:
        angle = _skew_angle(film)
        source = "film outline"
    if settings.min_skew_deg <= abs(angle) <= settings.max_skew_deg:
        rotated_note = f"rotated {angle:.2f}\N{DEGREE SIGN} ({source})"
    else:
        rotated_note = _not_rotated_note(settings, angle)
        angle = 0.0
    kept_note = rotated_note
    if not angle:
        return _noted(rough, kept_note, notes), film
    rotated = deskew(
        film.astype(np.uint8),
        angle,
        interpolation=cv2.INTER_NEAREST,
        border=cv2.BORDER_CONSTANT,
    ).astype(bool)
    final = _locate(deskew(lum, angle), rotated, d_ref, settings, angle)[0]
    if rough.confident and not final.confident:
        # an uncertain film-box crop is worse than no rotation
        return _noted(rough, "rotated pass uncertain, kept unrotated", notes), film
    return _noted(final, rotated_note, notes), rotated


def _not_rotated_note(settings: AnalyzerSettings, angle: float) -> str:
    """Why no rotation was applied; `angle` is the measured (rejected) one."""
    degree = "\N{DEGREE SIGN}"
    measured = f"abs angle {abs(angle):.2f}{degree}"
    if abs(angle) > settings.max_skew_deg:
        return f"not rotated ({measured} > {settings.max_skew_deg:g}{degree})"
    return f"not rotated ({measured} < {settings.min_skew_deg:g}{degree})"


def _noted(geometry: FrameGeometry, rotation: str, notes: list[str]) -> FrameGeometry:
    """`geometry` with its reason: rotation, then `notes`, then the crop part."""
    reason = "; ".join([rotation, *notes, geometry.reason])
    return replace(geometry, reason=reason)


def _percent(part: float, whole: float) -> str:
    return f"{100.0 * part / max(1.0, whole):.1f} %"


def _holder_note(strips: BoolMask) -> str:
    """Widths of the removed holder strips, in percent of the image side."""
    height, width = strips.shape
    sides = (
        ("left", int(np.argmin(strips[height // 2])) if strips[height // 2, 0] else 0),
        (
            "right",
            int(np.argmin(strips[height // 2, ::-1])) if strips[height // 2, -1] else 0,
        ),
        ("top", int(np.argmin(strips[:, width // 2])) if strips[0, width // 2] else 0),
        (
            "bottom",
            int(np.argmin(strips[::-1, width // 2])) if strips[-1, width // 2] else 0,
        ),
    )
    parts = [
        f"{name} {_percent(size, width if name in ('left', 'right') else height)}"
        for name, size in sides
        if size
    ]
    return f"translucent holder strips removed ({', '.join(parts)} of the image side)"


def _locate(
    lum: FloatImage,
    film: BoolMask,
    d_ref: float,
    settings: AnalyzerSettings,
    angle: float,
) -> tuple[FrameGeometry, Rect]:
    """Frame rectangle on a preview already rotated by `angle`.

    Also returns the frame edges for the deskew bands: the segment found
    between gaps/rebate before aspect snapping and end-shortening
    moved any side, or the film bounding box when the frame is not confident.
    """
    edge = max(lum.shape)
    x, y, box_w, box_h = cv2.boundingRect(film.astype(np.uint8))
    window = max(3, edge // 100) | 1
    std = _local_std(lum, window, film)
    strict = (lum < d_ref + settings.gap_delta) & (std < settings.gap_std)
    loose = ((lum < d_ref + settings.loose_delta) & (std < settings.loose_std)) | ~film
    strict = strict[y : y + box_h, x : x + box_w]
    loose = loose[y : y + box_h, x : x + box_w]
    min_run = max(2, max(box_w, box_h) // 100)
    if box_w >= box_h:
        (c0, c1), found_c = _long_axis(strict.mean(axis=0), loose.mean(axis=0), min_run)
        (r0, r1), found_r = _trim_edges(loose.mean(axis=1))
    else:
        (r0, r1), found_r = _long_axis(strict.mean(axis=1), loose.mean(axis=1), min_run)
        (c0, c1), found_c = _trim_edges(loose.mean(axis=0))
    segment = (y + r0, x + c0, y + r1, x + c1)
    aspect, (width, height) = _snap_aspect(
        float(c1 - c0), float(r1 - r0), settings.aspect_tol
    )
    axes: list[str] = []
    if aspect != "free":
        dens = lum[y : y + box_h, x : x + box_w] - d_ref
        band = dens[r0:r1, :]
        shrunk, anchors = _shrink_span(band, (c0, c1), width)
        axes.append(
            _explain_shrink(
                (c0, c1), shrunk, anchors, "width", ("left", "right"), lum.shape[1]
            )
        )
        c0, c1 = shrunk
        band = dens[:, c0:c1].T
        shrunk, anchors = _shrink_span(band, (r0, r1), height)
        axes.append(
            _explain_shrink(
                (r0, r1), shrunk, anchors, "height", ("top", "bottom"), lum.shape[0]
            )
        )
        r0, r1 = shrunk
    fraction = width * height / max(1, int(film.sum()))
    confident = aspect != "free" and (found_c or found_r) and 0.25 <= fraction <= 0.98
    if confident:
        center = (x + (c0 + c1) / 2.0, y + (r0 + r1) / 2.0)
        edges = Rect(*segment)
        reason = "; ".join([f"snapped to {aspect}", *filter(None, axes)])
    else:
        aspect = "free"
        center = (x + box_w / 2.0, y + box_h / 2.0)
        width, height = float(box_w), float(box_h)
        edges = Rect(y, x, y + box_h, x + box_w)
        reason = "no format (crop uncertain, full film area kept)"
    geometry = FrameGeometry(
        source_shape=(lum.shape[0], lum.shape[1]),
        angle_deg=angle,
        center=center,
        size=(width, height),
        confident=confident,
        aspect=aspect,
        reason=reason,
    )
    return geometry, edges


def _triple(values: npt.NDArray[np.floating]) -> Triple:
    return (float(values[0]), float(values[1]), float(values[2]))


def _film_mask(
    lum: FloatImage, threshold: float, edge: int, holder: BoolMask | None = None
) -> BoolMask:
    """Largest film region: lum below threshold and outside `holder` strips."""
    film = lum < threshold
    if holder is not None:
        film &= ~holder
    mask = film.astype(np.uint8)
    size = max(3, edge // 100) | 1  # odd: even kernels shift the mask by one pixel
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (size, size))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    if count <= 1:
        return np.ones(lum.shape, dtype=bool)
    largest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    result = np.asarray(labels == largest)
    if holder is not None:
        result &= ~holder  # closing refills strips thinner than the kernel
    return result


def _bare_light(lum: FloatImage) -> BoolMask:
    """Pixels clearly clearer than any film base: bare light.

    The first base estimate ignores a border margin, where a thin strip of bare
    light (film edge, holder gap) would be the lowest density of the image.
    Bare light is whatever lies BARE_GAP below that estimate; film, including
    its clear base, never does.
    """
    margin = max(1, round(BORDER_MARGIN * max(lum.shape)))
    inner = lum[margin:-margin, margin:-margin]
    if inner.size == 0:
        return np.zeros(lum.shape, dtype=bool)
    return np.asarray(lum < float(np.percentile(inner, 0.5)) - BARE_GAP)


def _base_reference(lum: FloatImage, bare: BoolMask | None = None) -> float:
    """Density of the film base: 0.5 % quantile of the image without bare light."""
    if bare is None:
        bare = _bare_light(lum)
    return float(np.percentile(lum[~bare] if bare.any() else lum, 0.5))


def _holder_strips(
    lum: FloatImage,
    d_ref: float,
    settings: AnalyzerSettings,
    bare: BoolMask | None = None,
) -> BoolMask:
    """Translucent holder strips along the four image borders.

    A strip is the run of lines (columns at the left/right border, rows at
    the top/bottom) from the border inwards whose density above d_ref has a
    median >= holder_min and a 10th percentile >= HOLDER_P10 x holder_min
    over the whole side, i.e. uniformly dense along >= 90 % of it. It counts
    only if a base-like line (median <= loose_delta above d_ref) follows
    within HOLDER_STEP of the long edge; the strip then reaches up to that
    line. A motif band at the border (sky) has no base-like line after it.
    Bare-light pixels do not enter the line statistics.
    """
    dens = lum - d_ref
    if bare is not None and bare.any():
        dens = np.where(bare, np.float32(np.nan), dens)
    strips = np.zeros(lum.shape, dtype=bool)
    window = max(2, round(HOLDER_STEP * max(lum.shape)))
    for side, out in (
        (dens, strips),
        (dens[:, ::-1], strips[:, ::-1]),
        (dens.T, strips.T),
        (dens.T[:, ::-1], strips.T[:, ::-1]),
    ):
        out[:, : _holder_width(side, settings, window)] = True
    return strips


def _holder_width(dens: FloatImage, settings: AnalyzerSettings, window: int) -> int:
    """Width of the holder strip at the left border of `dens`, 0 if none."""
    lead = 0  # leading lines without any film pixel (all bare light) are skipped
    while lead < dens.shape[1] and np.isnan(dens[:, lead]).all():
        lead += 1
    if lead:
        width = _holder_width(dens[:, lead:], settings, window)
        return lead + width if width else 0
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # all-bare lines give NaN
        median = np.nanmedian(dens, axis=0)
        p10 = np.nanpercentile(dens, 10, axis=0)
    holder = (median >= settings.holder_min) & (p10 >= HOLDER_P10 * settings.holder_min)
    width = int(np.argmin(holder))  # first line that is not holder
    if not holder[0] or holder[width]:  # no strip, or the whole image
        return 0
    base = np.flatnonzero(median[width : width + window + 1] <= settings.loose_delta)
    return width + int(base[0]) if base.size else 0


def _skew_angle(film: BoolMask) -> float:
    """Angle of the film outline (minAreaRect), normalised to -45..+45 degrees."""
    contours, _ = cv2.findContours(
        film.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    if not contours:
        return 0.0
    _, _, angle = cv2.minAreaRect(max(contours, key=cv2.contourArea))
    angle = float(angle)
    while angle >= 45.0:
        angle -= 90.0
    while angle < -45.0:
        angle += 90.0
    return angle


@dataclass(frozen=True)
class _EdgeBand:
    """Pixels of one band around a frame edge, weighted by gradient magnitude."""

    x: npt.NDArray[np.float64]
    y: npt.NDArray[np.float64]
    weight: npt.NDArray[np.float64]
    horizontal: bool  # top/bottom band: profile over rows, else over columns


def _edge_angle(
    lum: FloatImage, film: BoolMask, edges: Rect, settings: AnalyzerSettings
) -> float | None:
    """Skew angle from the outer edges of the rough frame.

    `edges` are the frame edges before aspect snapping (see _locate), so the
    angle does not depend on how end-shortening cuts the frame.
    Gradient magnitude in bands around the four frame edges only (the frame
    interior is excluded), on the film only: the film/holder boundary is the
    film outline (the minAreaRect fallback), and a holder that sits straight
    on the sensor would otherwise outweigh a tilted frame. The band pixels are
    rotated like geometry.deskew would rotate them; score = sum of squared row
    profiles (top/bottom bands) plus squared column profiles (left/right
    bands). Coarse search, then fine over +-COARSE_STEP around the coarse
    best; ties go to the smaller |angle| (see _best_angle). None when the best
    angle gains less than MIN_GAIN over 0 deg (no usable edge).
    """
    bands = _edge_bands(lum, film, edges)
    center = (lum.shape[1] / 2.0, lum.shape[0] / 2.0)
    steps = int(settings.max_skew_deg / COARSE_STEP)
    coarse = [k * COARSE_STEP for k in range(-steps, steps + 1)]
    scores = {theta: _edge_score(bands, center, theta) for theta in coarse}
    best = _best_angle(scores)
    span = math.ceil(COARSE_STEP / FINE_STEP)  # round(12.5) would give 12
    for k in range(-span, span + 1):
        theta = round(best + k * FINE_STEP, 6)
        if abs(theta) <= settings.max_skew_deg and theta not in scores:
            scores[theta] = _edge_score(bands, center, theta)
    best = _best_angle(scores)
    zero = scores[0.0]
    if zero <= 0.0 or scores[best] < (1.0 + MIN_GAIN) * zero:
        return None
    return best


def _best_angle(scores: dict[float, float]) -> float:
    """Highest score; ties go to the smaller |theta|, then to the negative one."""
    return min(scores, key=lambda theta: (-scores[theta], abs(theta), theta))


def _edge_bands(lum: FloatImage, film: BoolMask, rect: Rect) -> list[_EdgeBand]:
    """Bands of EDGE_BAND x long edge inside and outside each frame edge.

    The profile coordinate gets a fixed sub-pixel dither: without it, pixel
    centres fall exactly on the profile bins at 0 deg only, and linear binning
    would favour 0 deg over every other angle.
    """
    height, width = lum.shape
    half = max(2, round(EDGE_BAND * max(rect.height, rect.width)))
    grad_y, grad_x = np.gradient(lum.astype(np.float64))
    size = max(3, max(height, width) // 100) | 1  # as in _film_mask
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (size, size))
    inside = cv2.erode(film.astype(np.uint8), kernel, borderType=cv2.BORDER_REPLICATE)
    magnitude = np.hypot(grad_x, grad_y) * inside
    rng = np.random.default_rng(0)
    spans = [
        (rect.top - half, rect.top + half, rect.left, rect.right, True),
        (rect.bottom - half, rect.bottom + half, rect.left, rect.right, True),
        (rect.top, rect.bottom, rect.left - half, rect.left + half, False),
        (rect.top, rect.bottom, rect.right - half, rect.right + half, False),
    ]
    bands: list[_EdgeBand] = []
    for top, bottom, left, right, horizontal in spans:
        top, bottom = max(0, top), min(height, bottom)
        left, right = max(0, left), min(width, right)
        if bottom <= top or right <= left:
            continue
        yy, xx = np.mgrid[top:bottom, left:right].astype(np.float64)
        dither = rng.random(yy.shape) - 0.5
        if horizontal:
            yy += dither
        else:
            xx += dither
        weight = magnitude[top:bottom, left:right]
        bands.append(_EdgeBand(xx.ravel(), yy.ravel(), weight.ravel(), horizontal))
    return bands


def _edge_score(
    bands: list[_EdgeBand], center: tuple[float, float], theta: float
) -> float:
    """Sum of squared profiles of the bands rotated counter-clockwise by theta."""
    matrix = cv2.getRotationMatrix2D(center, theta, 1.0)
    total = 0.0
    for band in bands:
        row = matrix[1] if band.horizontal else matrix[0]
        pos = row[0] * band.x + row[1] * band.y
        pos -= np.floor(pos.min())
        index = pos.astype(np.int64)
        frac = pos - index
        size = int(index.max()) + 2
        profile = np.bincount(index, band.weight * (1.0 - frac), size)
        profile += np.bincount(index + 1, band.weight * frac, size)
        total += float(np.dot(profile, profile))
    return total


def _local_std(lum: FloatImage, window: int, valid: BoolMask) -> FloatImage:
    """Local std over `valid` pixels only, so the holder cannot spike the film edge."""
    size = (window, window)
    weight = cv2.blur(valid.astype(np.float32), size)
    safe = np.maximum(weight, np.float32(1e-6))
    masked = np.where(valid, lum, np.float32(0.0)).astype(np.float32)
    mean = cv2.blur(masked, size) / safe
    mean_sq = cv2.blur(masked * masked, size) / safe
    variance = np.maximum(mean_sq - mean * mean, np.float32(0.0))
    return np.asarray(np.sqrt(variance), dtype=np.float32)


def _runs(mask: BoolMask) -> list[Span]:
    padded = np.concatenate(([False], mask, [False])).astype(np.int8)
    edges = np.flatnonzero(np.diff(padded))
    return list(zip(edges[::2].tolist(), edges[1::2].tolist(), strict=True))


def _trim_edges(loose_fraction: npt.NDArray[np.floating]) -> tuple[Span, bool]:
    """Cut base-like bands (rebate, gap rim, holder fringe) touching both ends."""
    n = len(loose_fraction)
    lo, hi = 0, n
    while lo < n and loose_fraction[lo] > EDGE_BAND_FRACTION:
        lo += 1
    while hi > lo and loose_fraction[hi - 1] > EDGE_BAND_FRACTION:
        hi -= 1
    if hi - lo < 0.1 * n:
        return (0, n), False
    return (lo, hi), lo > 0 or hi < n


def _long_axis(
    strict_fraction: npt.NDArray[np.floating],
    loose_fraction: npt.NDArray[np.floating],
    min_run: int,
) -> tuple[Span, bool]:
    """Trim the ends, then split at inter-frame gaps; keep the widest segment."""
    (lo, hi), trimmed = _trim_edges(loose_fraction)
    gaps = [
        (a, b)
        for a, b in _runs(strict_fraction[lo:hi] > GAP_FRACTION)
        if b - a >= min_run
    ]
    cuts = [lo, *(lo + v for gap in gaps for v in gap), hi]
    segments = [(cuts[i], cuts[i + 1]) for i in range(0, len(cuts), 2)]
    best = max(segments, key=lambda s: s[1] - s[0])
    return best, trimmed or bool(gaps)


def _snap_aspect(
    width: float, height: float, tolerance: float
) -> tuple[str, tuple[float, float]]:
    long_side, short_side = max(width, height), min(width, height)
    if short_side <= 0:
        return "free", (width, height)
    ratio = long_side / short_side
    name, target = min(ASPECTS.items(), key=lambda kv: abs(ratio - kv[1]) / kv[1])
    if abs(ratio - target) / target >= tolerance:
        return "free", (width, height)
    if ratio > target:
        long_side = short_side * target
    else:
        short_side = long_side / target
    if width >= height:
        return name, (long_side, short_side)
    return name, (short_side, long_side)


def _shrink_span(
    band: FloatImage, span: Span, length: float
) -> tuple[Span, tuple[int | None, int | None]]:
    """Shrink span to length; also returns the anchors it used.

    band is the density above the film base, shrinking axis along columns and
    the other axis' frame extent along rows. An end with a sharp straight edge
    nearby is a frame border and stays put: excess goes to the other end. With
    both ends anchored the excess is split evenly, unless that would keep a
    band outside an anchoring edge (fog or rebate beyond the border): then the
    split moves just enough to remove it, or centres between both edges when
    they are closer than length. Without any anchor, the excess is taken where
    the removed bands have the lowest summed median density (fog, rebate, gap
    fringe); ties resolve towards the symmetric split. The anchors are the
    edge indices per end (None = not anchored) for the crop reason;
    (None, None) when nothing had to be cut.
    """
    lo, hi = span
    excess = round((hi - lo) - length)
    if excess <= 0:
        return span, (None, None)
    lo_edge, hi_edge = _anchor_edges(band, span)
    if lo_edge is not None and hi_edge is not None:
        start = _split_between_edges(excess, lo_edge + 1 - lo, hi - (hi_edge + 1))
    elif lo_edge is not None:
        start = 0
    elif hi_edge is not None:
        start = excess
    else:
        profile = np.median(band, axis=0)
        cum = np.concatenate(([0.0], np.cumsum(profile[lo:hi], dtype=np.float64)))
        k = np.arange(excess + 1)
        cost = cum[k] + (cum[-1] - cum[len(cum) - 1 - (excess - k)])
        cost = cost + 1e-9 * np.abs(k - excess / 2.0)
        start = int(np.argmin(cost))
    return (lo + start, hi - (excess - start)), (lo_edge, hi_edge)


def _explain_shrink(
    before: Span,
    after: Span,
    anchors: tuple[int | None, int | None],
    axis: str,
    names: tuple[str, str],
    side: int,
) -> str:
    """Reason for the end-shortening of one axis; empty if nothing was cut.

    Sizes are percent of the image side along that axis (analysis preview).
    """
    excess = (before[1] - before[0]) - (after[1] - after[0])
    if excess <= 0:
        return ""
    anchored = [
        f"{name} edge"
        for name, edge in zip(names, anchors, strict=True)
        if edge is not None
    ]
    state = " + ".join(anchored) + " anchored" if anchored else "no edge anchored"
    from_lo, from_hi = after[0] - before[0], before[1] - after[1]
    if from_hi == 0:
        taken = f"taken from the {names[0]}"
    elif from_lo == 0:
        taken = f"taken from the {names[1]}"
    else:
        taken = (
            f"split, {_percent(from_lo, side)} from the {names[0]}"
            f" and {_percent(from_hi, side)} from the {names[1]}"
        )
    if not anchored:
        taken += " (lower density)"
    return f"{axis}: {state}, excess {_percent(excess, side)} of the {axis} {taken}"


def _split_between_edges(excess: int, outer_lo: int, outer_hi: int) -> int:
    """Excess taken at the low end when both ends are anchored.

    outer_lo/outer_hi: span pixels outside the anchoring edge at each end
    (negative when the edge lies outside the span). Start from the even split
    and move it just enough that no outer band stays; if both cannot go, centre
    the frame between the two edges.
    """
    low, high = outer_lo, excess - outer_hi
    start = min(max(excess // 2, low), high) if low <= high else (low + high) // 2
    return min(max(start, 0), excess)


def _anchor_edges(band: FloatImage, span: Span) -> tuple[int | None, int | None]:
    """Sharp straight edge near each end of span, or None.

    Edge score per column = median over rows of |first difference|; an end is
    anchored if the strongest score within EDGE_WINDOW of the axis length
    reaches EDGE_FACTOR x the median score inside the span. Returns the index
    of that strongest step (between columns k and k + 1) per end.
    """
    lo, hi = span
    if hi - lo < 3:  # no inside to compare with (tiny crops)
        return None, None
    scores = np.median(np.abs(np.diff(band, axis=1)), axis=0)
    typical = float(np.median(scores[lo : hi - 1]))
    window = max(1, round(EDGE_WINDOW * band.shape[1]))

    def anchor(end: int) -> int | None:
        first = max(0, end - window)
        near = scores[first : end + window]
        if near.size == 0 or float(near.max()) < EDGE_FACTOR * typical:
            return None
        return int(first + near.argmax())

    return anchor(lo), anchor(hi - 1)


def _is_bw(crop: FloatImage, d_min: Triple, d_white: Triple, threshold: float) -> bool:
    """BW only if no part of the frame is coloured (p99.9 of block deviation).

    A colour photo may be mostly neutral with a few coloured details, while
    black-and-white film has no colour anywhere: a high percentile catches
    even a small coloured share.
    """
    d_min_arr = np.asarray(d_min, np.float32)
    d_hi = np.maximum(
        np.asarray(d_white, np.float32) - d_min_arr, np.float32(MIN_SPREAD)
    )
    norm, _ = normalize_density(crop, d_min_arr, d_hi)
    h, w = norm.shape[0] // 4 * 4, norm.shape[1] // 4 * 4
    if h == 0 or w == 0:
        return False
    blocks = norm[:h, :w].reshape(h // 4, 4, w // 4, 4, 3).mean(axis=(1, 3))
    deviation = np.abs(blocks - blocks.mean(axis=2, keepdims=True)).mean(axis=2)
    return bool(np.percentile(deviation, BW_PERCENTILE) < threshold)
