"""Processing description embedded in every output file."""

from real_fast_negconv.core.converter import Triple

_TRANSLITERATION = str.maketrans(
    {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "\N{DEGREE SIGN}": " deg"}
)
CROP_REASON_MARKER = " | crop: "  # the reason is always the last part


def describe(
    *,
    version: str,
    is_bw: bool,
    d_min_used: Triple,
    fallback_applied: bool,
    confident: bool,
    aspect: str,
    crossover: str = "",
    reason: str = "",
) -> str:
    """One ASCII line documenting how the frame was processed.

    `crossover` (crossover_note, spec 12.S) is added as `crossover: <note>`
    when not empty; `reason` (FrameGeometry.reason) is appended last as
    `crop: <reason>`.
    """
    d_min = ",".join(f"{value:.3f}" for value in d_min_used)
    parts = [
        f"rfnegconv {version}",
        "bw" if is_bw else "color",
        f"dmin={d_min}",
        f"fallback={'yes' if fallback_applied else 'no'}",
        f"crop={aspect if confident else 'uncertain'}",
    ]
    if crossover:
        parts.append(f"crossover: {crossover}")
    if reason:
        parts.append(f"crop: {reason}")
    text = " | ".join(parts).translate(_TRANSLITERATION)
    return text.encode("ascii", "replace").decode("ascii")
