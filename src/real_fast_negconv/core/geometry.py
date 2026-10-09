"""Geometry primitives: rectangles, detected frame, deskew and user orientation."""

from dataclasses import dataclass
from typing import Literal

import cv2
import numpy as np
import numpy.typing as npt

type Rotation = Literal[0, 90, 180, 270]

MEASURE_INSET = 0.10  # per side; statistics use the inner 80 % (spec 12.A)


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

    def iou(self, other: "Rect") -> float:
        """Intersection over union with another rectangle."""
        height = min(self.bottom, other.bottom) - max(self.top, other.top)
        width = min(self.right, other.right) - max(self.left, other.left)
        inter = max(0, height) * max(0, width)
        return inter / (self.area + other.area - inter)


@dataclass(frozen=True)
class FrameGeometry:
    """Detected image frame in coordinates of the deskewed analysis image."""

    source_shape: tuple[int, int]
    angle_deg: float
    center: tuple[float, float]
    size: tuple[float, float]
    confident: bool
    aspect: str
    reason: str = ""  # why the crop and rotation are what they are (spec 12.Q)

    def crop_rect(self, shape: tuple[int, int], inset: float = 0.01) -> Rect:
        """Return the frame for an image of `shape`, pulled inwards by `inset`."""
        scale = shape[1] / self.source_shape[1]
        cx, cy = self.center[0] * scale, self.center[1] * scale
        width, height = self.size[0] * scale, self.size[1] * scale
        pad = inset * max(width, height)
        rect = Rect(
            round(cy - height / 2 + pad),
            round(cx - width / 2 + pad),
            round(cy + height / 2 - pad),
            round(cx + width / 2 - pad),
        )
        return rect.clamp(shape[0], shape[1])


def deskew[T: np.generic](
    img: npt.NDArray[T],
    angle_deg: float,
    *,
    interpolation: int = cv2.INTER_LINEAR,
    border: int = cv2.BORDER_REPLICATE,
) -> npt.NDArray[T]:
    """Rotate `img` counter-clockwise by `angle_deg` around its centre."""
    if angle_deg == 0.0:
        return img
    height, width = img.shape[:2]
    matrix = cv2.getRotationMatrix2D((width / 2.0, height / 2.0), angle_deg, 1.0)
    rotated = cv2.warpAffine(
        img, matrix, (width, height), flags=interpolation, borderMode=border
    )
    return np.asarray(rotated, dtype=img.dtype)


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
