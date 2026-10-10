"""Contact sheet: one JPEG with thumbnails of every JPEG a run produced."""

import io
import logging
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from real_fast_negconv.fileio.atomic import atomic_write

log = logging.getLogger(__name__)

NAME_PREFIX = "_Kontaktabzug"
COLUMNS = 6
THUMB_SIZE = (320, 240)  # each thumbnail fits into this box
LABEL_HEIGHT = 28
GAP = 16
MARGIN = 24
FONT_SIZE = 14
QUALITY = 85
# pictures per sheet (50 rows): a larger run gets several sheets "... Teil 2"
SHEET_MAX_PICTURES = COLUMNS * 50
BACKGROUND = (255, 255, 255)
TEXT_COLOR = (0, 0, 0)
ELLIPSIS = "\N{HORIZONTAL ELLIPSIS}"

type Font = ImageFont.FreeTypeFont | ImageFont.ImageFont


def is_contact_sheet(path: Path) -> bool:
    """True for a contact sheet written by this module."""
    return path.name.startswith(NAME_PREFIX + " ")


def sheet_path(photos_dir: Path, now: datetime, part: int | None = None) -> Path:
    """`_Kontaktabzug JJJJ-MM-TT HH-MM.jpg` (with `part`: `... Teil N.jpg`),
    or `..._2.jpg` etc. if taken."""
    stem = f"{NAME_PREFIX} {now:%Y-%m-%d %H-%M}"
    if part is not None:
        stem = f"{stem} Teil {part}"
    candidate = photos_dir / f"{stem}.jpg"
    n = 2
    while candidate.exists():
        candidate = photos_dir / f"{stem}_{n}.jpg"
        n += 1
    return candidate


def _font() -> Font:
    try:
        return ImageFont.load_default(size=FONT_SIZE)
    except TypeError:  # pragma: no cover - Pillow < 10.1 has no sized default
        return ImageFont.load_default()


def _label(text: str, font: Font, width: int) -> str:
    """`text`, shortened with an ellipsis until it fits `width` pixels."""
    if font.getlength(text) <= width:
        return text
    while text and font.getlength(text + ELLIPSIS) > width:
        text = text[:-1]
    return text + ELLIPSIS


def _thumbnail(path: Path) -> Image.Image | None:
    try:
        with Image.open(path) as image:
            image.draft("RGB", THUMB_SIZE)
            thumb = image.convert("RGB")
    except (OSError, ValueError) as exc:
        log.warning("Contact sheet: cannot read %s: %s", path.name, exc)
        return None
    thumb.thumbnail(THUMB_SIZE, Image.Resampling.LANCZOS)
    return thumb


def render_sheet(jpegs: Sequence[Path]) -> Image.Image:
    """Fixed grid, sorted by file name; each cell a thumbnail and its name."""
    ordered = sorted(jpegs, key=lambda p: (p.name.casefold(), p.name))
    columns = min(COLUMNS, max(1, len(ordered)))
    rows = (len(ordered) + COLUMNS - 1) // COLUMNS
    cell_w, cell_h = THUMB_SIZE[0], THUMB_SIZE[1] + LABEL_HEIGHT
    width = 2 * MARGIN + columns * cell_w + (columns - 1) * GAP
    height = 2 * MARGIN + rows * cell_h + max(0, rows - 1) * GAP
    sheet = Image.new("RGB", (width, height), BACKGROUND)
    draw = ImageDraw.Draw(sheet)
    font = _font()
    for index, path in enumerate(ordered):
        row, column = divmod(index, COLUMNS)
        x = MARGIN + column * (cell_w + GAP)
        y = MARGIN + row * (cell_h + GAP)
        thumb = _thumbnail(path)
        if thumb is not None:
            offset = (
                x + (THUMB_SIZE[0] - thumb.width) // 2,
                y + (THUMB_SIZE[1] - thumb.height) // 2,
            )
            sheet.paste(thumb, offset)
        label = _label(path.name, font, cell_w)
        text_x = x + (cell_w - int(font.getlength(label))) // 2
        draw.text((text_x, y + THUMB_SIZE[1] + 6), label, fill=TEXT_COLOR, font=font)
    return sheet


def write_contact_sheet(
    jpegs: Sequence[Path],
    photos_dir: Path,
    now: datetime | None = None,
    written: list[Path] | None = None,
) -> list[Path]:
    """Write the contact sheet(s) of `jpegs` into `photos_dir` (atomically).

    Up to SHEET_MAX_PICTURES pictures make one sheet; more are split, in name
    order, into "Teil 1", "Teil 2", ... Each part is appended to `written` as
    soon as it is on disk, so a caller still knows the finished parts when a
    later one fails.
    """
    ordered = sorted(jpegs, key=lambda p: (p.name.casefold(), p.name))
    chunks = [
        ordered[i : i + SHEET_MAX_PICTURES]
        for i in range(0, len(ordered), SHEET_MAX_PICTURES)
    ]
    stamp = now or datetime.now()
    written = [] if written is None else written
    for number, chunk in enumerate(chunks, start=1):
        sheet = render_sheet(chunk)
        buffer = io.BytesIO()
        sheet.save(buffer, format="JPEG", quality=QUALITY)
        data = buffer.getvalue()
        del sheet, buffer
        part = number if len(chunks) > 1 else None
        target = sheet_path(photos_dir, stamp, part)

        def write(tmp: Path, data: bytes = data) -> None:
            tmp.write_bytes(data)

        atomic_write(target, write)
        log.info("Contact sheet: %s (%d pictures)", target.name, len(chunk))
        written.append(target)
    return written
