"""Geometry primitives: rectangles, detected frame, deskew and user orientation."""

from dataclasses import dataclass, field, replace
from typing import Literal

import cv2
import numpy as np
import numpy.typing as npt

type Rotation = Literal[0, 90, 180, 270]

MEASURE_INSET = 0.10  # per side; statistics use the inner 80 %
PICTURE_INTERPOLATION = cv2.INTER_LANCZOS4  # deskew of the developed picture
EDGE_INSET = 0.03  # per side; window for bright picture parts near the border


@dataclass(frozen=True)
class Rect:
    """Axis-aligned pixel rectangle; bottom and right are exclusive."""

    top: int
    left: int
    bottom: int
    right: int

    def __post_init__(self) -> None:
        if self.bottom <= self.top or self.right <= self.left:
            raise ValueError(f"empty rectangle: {self}")

    @property
    def height(self) -> int:
        return self.bottom - self.top

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def area(self) -> int:
        return self.height * self.width

    def inner(self, fraction: float = MEASURE_INSET) -> "Rect":
        """Return the rectangle pulled in by `fraction` of its size per side."""
        dh, dw = int(self.height * fraction), int(self.width * fraction)
        if self.height - 2 * dh < 1 or self.width - 2 * dw < 1:
            return self
        return Rect(self.top + dh, self.left + dw, self.bottom - dh, self.right - dw)

    def slices(self) -> tuple[slice, slice]:
        """Return (row slice, column slice) for numpy indexing."""
        return slice(self.top, self.bottom), slice(self.left, self.right)

    def clamp(self, height: int, width: int) -> "Rect":
        """Return the rectangle restricted to an image of the given size."""
        return Rect(
            max(0, self.top),
            max(0, self.left),
            min(height, self.bottom),
            min(width, self.right),
        )


@dataclass(frozen=True, eq=False)
class EdgeProfiles:
    """Where straight edges cross the film, for fitting a frame of known size.

    `columns[k]` is the vertical edge between preview columns k and k + 1:
    the median over the film's rows of the density step, positive where the
    density rises to the right (unexposed film, then picture: the left
    border of a frame) and negative where it falls (a right border).
    `rows[k]` is the same for horizontal edges, top to bottom. `box` is the
    film's bounding box: a frame never reaches outside it.
    `base_columns[k]` / `base_rows[k]` tell whether
    preview column / row k is unexposed film across the film (rebate, a gap
    between frames, or a dark picture edge): a frame may begin or end with
    such lines but never has them in its middle, where they are the gap to
    the next frame.
    """

    columns: npt.NDArray[np.float32]
    rows: npt.NDArray[np.float32]
    box: Rect
    base_columns: npt.NDArray[np.bool_] | None = None
    base_rows: npt.NDArray[np.bool_] | None = None


@dataclass(frozen=True)
class FrameGeometry:
    """Detected image frame in coordinates of the deskewed analysis image."""

    source_shape: tuple[int, int]
    angle_deg: float
    center: tuple[float, float]
    size: tuple[float, float]
    confident: bool
    aspect: str
    reason: str = ""  # why the crop and rotation are what they are
    edges: EdgeProfiles | None = field(default=None, compare=False, repr=False)
    # degrees between opposite frame edges (top - bottom, left - right)
    edge_skew: tuple[float | None, float | None] = field(
        default=(None, None), compare=False, repr=False
    )

    def span(self, axis: int) -> tuple[float, float]:
        """(low, high) of the frame along x (axis 0) or y (axis 1)."""
        return (
            self.center[axis] - self.size[axis] / 2.0,
            self.center[axis] + self.size[axis] / 2.0,
        )

    def fitted(
        self, size: tuple[float, float], aspect: str, *, need_edges: bool
    ) -> "FrameGeometry | None":
        """This frame with the known `size` (width, height), placed by its edges.

        Per axis the frame of that length is put where the two edges it would
        have are strongest (`edges`). It must cover the detected frame if that
        is shorter (nothing found is given up), or lie inside it if that is
        longer (an uncertain crop holds rebate or neighbouring frames). With
        `need_edges` both ends of each axis must lie on a clear edge (at
        least FIT_EDGE_FACTOR x the typical edge strength on the film): a
        frame of another size, e.g. a panorama, has no such pair of edges
        and is left alone. None if it cannot be placed that way.
        """
        if self.edges is None:
            return None
        box = self.edges.box
        placed: list[float] = []
        for axis, (scores, base, low, high) in enumerate(
            (
                (self.edges.columns, self.edges.base_columns, box.left, box.right),
                (self.edges.rows, self.edges.base_rows, box.top, box.bottom),
            )
        ):
            start = _place(
                scores, self.span(axis), size[axis], (low, high), need_edges, base
            )
            if start is None:
                return None
            placed.append(start + size[axis] / 2.0)
        return replace(
            self,
            center=(placed[0], placed[1]),
            size=size,
            confident=True,
            aspect=aspect,
        )

    def crop_rect(self, shape: tuple[int, int], inset: float = 0.01) -> Rect:
        """Return the frame for an image of `shape`, pulled inwards by `inset`.

        `inset` is a fraction of the longer side; a very narrow frame is
        pulled in only as far as its shorter side leaves a pixel.
        """
        scale = shape[1] / self.source_shape[1]
        cx, cy = self.center[0] * scale, self.center[1] * scale
        width, height = self.size[0] * scale, self.size[1] * scale
        pad = min(inset * max(width, height), max(0.0, (min(width, height) - 1.0) / 2))
        top, left = round(cy - height / 2 + pad), round(cx - width / 2 + pad)
        rect = Rect(
            top,
            left,
            max(top + 1, round(cy + height / 2 - pad)),
            max(left + 1, round(cx + width / 2 - pad)),
        )
        return rect.clamp(shape[0], shape[1])


EDGE_TOLERANCE = 2  # preview pixels an edge may lie beside the expected place
FIT_EDGE_FACTOR = 2.5  # a clear edge: this x the median edge strength on the film


def _place(
    scores: npt.NDArray[np.float32],
    own: tuple[float, float],
    length: float,
    limits: tuple[int, int],
    need_edges: bool = False,
    base: npt.NDArray[np.bool_] | None = None,
) -> float | None:
    """Start of a span of `length` whose two ends lie on the strongest edges.

    Candidates cover `own` if it is shorter than `length`, else lie inside
    it; all stay within `limits`. Edges within EDGE_TOLERANCE count; among
    equals the start with the edges exactly at its ends wins, then the one
    nearest to centring the span on `own`. With `need_edges` the result is
    None unless both ends lie on an edge of at least FIT_EDGE_FACTOR x the
    median strength between the limits.
    """
    size = round(length)
    if size < 2 or size > limits[1] - limits[0]:
        return None
    own_lo, own_hi = round(own[0]), round(own[1])
    if own_hi - own_lo <= size:
        first, last = own_hi - size, own_lo
    else:
        first, last = own_lo, own_hi - size
    first, last = max(first, limits[0]), min(last, limits[1] - size)
    if last < first:
        return None
    # a frame begins with a step up from unexposed film and ends with a
    # step down: the strongest such step within the tolerance of each index
    window = 2 * EDGE_TOLERANCE + 1
    signed = scores.astype(np.float64)
    rising, falling = (
        np.max(
            np.lib.stride_tricks.sliding_window_view(
                np.pad(np.maximum(sign * signed, 0.0), EDGE_TOLERANCE + 1), window
            ),
            axis=1,
        )
        for sign in (1.0, -1.0)
    )

    def edge(index: int, steps: npt.NDArray[np.float64]) -> float:
        # steps[i] covers scores[i - 1 - EDGE_TOLERANCE ... i - 1 + EDGE_TOLERANCE]:
        # the edge of a span starting at column `index` is the step index - 1
        return float(steps[min(max(index, 0), len(steps) - 1)])

    def exact(index: int, sign: float) -> float:
        step = index - 1
        return max(sign * float(signed[step]), 0.0) if 0 <= step < len(signed) else 0.0

    # a run of unexposed lines in the middle is the gap to the next frame
    gaps = _base_runs(base) if base is not None else []
    starts = [
        s
        for s in range(first, last + 1)
        if not any(s < lo and hi < s + size for lo, hi in gaps)
    ]
    if not starts:
        return None
    centred = (own_lo + own_hi - size) / 2.0
    best = max(
        starts,
        key=lambda s: (
            edge(s, rising) + edge(s + size, falling),  # both edges close by
            exact(s, 1.0) + exact(s + size, -1.0),  # ... and exactly here
            -abs(s - centred),
        ),
    )
    if need_edges:
        inside = np.abs(signed[limits[0] : max(limits[0] + 1, limits[1] - 1)])
        clear = FIT_EDGE_FACTOR * float(np.median(inside))
        weakest = min(edge(best, rising), edge(best + size, falling))
        if clear <= 0.0 or weakest < clear:
            return None
    return float(best)


def _base_runs(base: npt.NDArray[np.bool_]) -> list[tuple[int, int]]:
    """(start, end) of every run of True in `base`, end exclusive."""
    padded = np.concatenate(([False], base, [False])).astype(np.int8)
    edges = np.flatnonzero(np.diff(padded))
    return list(zip(edges[::2].tolist(), edges[1::2].tolist(), strict=True))


def deskew[T: np.generic](
    img: npt.NDArray[T],
    angle_deg: float,
    *,
    interpolation: int = cv2.INTER_LINEAR,
    border: int = cv2.BORDER_REPLICATE,
) -> npt.NDArray[T]:
    """Rotate `img` counter-clockwise by `angle_deg` around its centre.

    The default (bilinear) is for masks and the analysis preview; the
    developed picture uses PICTURE_INTERPOLATION, which keeps grain and fine
    detail as sharp as in frames that need no rotation.

    A sharp filter has negative lobes. The unclipped picture holds values far
    outside 0-1 (dust, the holder), which those lobes would spread as a
    checkerboard of extremes, so every result is limited to the range of the
    source pixels around it.
    """
    if angle_deg == 0.0:
        return img
    height, width = img.shape[:2]
    matrix = cv2.getRotationMatrix2D((width / 2.0, height / 2.0), angle_deg, 1.0)
    rotated = np.asarray(
        cv2.warpAffine(
            img, matrix, (width, height), flags=interpolation, borderMode=border
        ),
        dtype=img.dtype,
    )
    if interpolation not in (cv2.INTER_NEAREST, cv2.INTER_LINEAR):
        _limit_to_surroundings(rotated, img, matrix, border)
    return rotated


def _limit_to_surroundings[T: np.generic](
    rotated: npt.NDArray[T],
    source: npt.NDArray[T],
    matrix: npt.NDArray[np.float64],
    border: int,
) -> None:
    """Clip `rotated` in place to the 3 x 3 source range around each pixel.

    The 3 x 3 block around the nearest source pixel holds the four pixels a
    result lies between. One channel at a time keeps the extra memory small.
    """
    size = (rotated.shape[1], rotated.shape[0])
    block = np.ones((3, 3), dtype=np.uint8)
    planes = (
        [(rotated, source)]
        if rotated.ndim == 2
        else [(rotated[..., c], source[..., c]) for c in range(rotated.shape[2])]
    )
    for out, src in planes:
        plane = np.ascontiguousarray(src)
        for extreme, limit in ((cv2.erode, np.maximum), (cv2.dilate, np.minimum)):
            bound = cv2.warpAffine(
                extreme(plane, block),
                matrix,
                size,
                flags=cv2.INTER_NEAREST,
                borderMode=border,
            )
            limit(out, bound, out=out)


def orient[T: np.generic](
    img: npt.NDArray[T], rect: Rect, rotation: Rotation, mirror: bool
) -> tuple[npt.NDArray[T], Rect]:
    """Mirror horizontally (optional), then rotate clockwise; crop follows."""
    if mirror:
        width = img.shape[1]
        img = img[:, ::-1]
        rect = Rect(rect.top, width - rect.right, rect.bottom, width - rect.left)
    for _ in range(rotation // 90):
        height = img.shape[0]
        img = np.rot90(img, k=-1)
        rect = Rect(rect.left, height - rect.bottom, rect.right, height - rect.top)
    return np.ascontiguousarray(img), rect
