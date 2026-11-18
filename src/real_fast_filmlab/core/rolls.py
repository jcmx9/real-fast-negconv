"""Roll context: what the frames of one film tell about each other.

Frames are grouped by the hue of their film base. Within a group the roll
repairs what a single frame cannot know: the film base of high-key frames,
the colour of the white point, the colour crossover, the frame size of
frames whose border could not be found, and the look.
"""

import logging
import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Literal

import numpy as np

from real_fast_filmlab.core.analyzer import FrameAnalysis, look_stats_for
from real_fast_filmlab.core.converter import MIN_SPREAD, NO_CROSSOVER, Triple
from real_fast_filmlab.core.crossover import (
    ROLL_LIMIT,
    CrossoverSource,
    crossover_per_frame,
    frame_mids,
)
from real_fast_filmlab.core.geometry import FrameGeometry
from real_fast_filmlab.core.look import (
    BASE_CONTRAST,
    BASE_SATURATION,
    LookParams,
    LookStats,
    look_params,
)

log = logging.getLogger(__name__)

ROLL_MIN_FRAMES = 3  # frames a roll value (white colour, frame size) needs
SIZE_TOLERANCE = 0.03  # frames this close to the roll's size are left alone
# Scan exposure, judged by the brightest channel of the film base
BASE_TOO_DARK = 0.125  # of the sensor range: three stops of headroom unused
KEYSTONE_TOLERANCE = 0.4  # degrees between opposite frame edges, batch median
BASE_CLIPPED = 0.98  # film base at the sensor's limit

type ExposureFinding = Literal["under", "over"]


@dataclass(frozen=True)
class RollSettings:
    """Thresholds for grouping, high-key fallback, white colour, crossover, look."""

    hue_tol: float = 0.06
    highkey_delta: float = 0.10
    uniform_ratio: float = 2.0
    crossover_limit: float = 0.10
    crossover_roll_limit: float = ROLL_LIMIT
    white_limit: float = 0.10
    contrast: float = BASE_CONTRAST
    saturation: float = BASE_SATURATION


@dataclass(frozen=True)
class RollDecision:
    """Film base, white point, colour/bw, look, crossover and frame actually used.

    `d_white_used` and `geometry` are None where the frame's own measurement
    stands (analysis.d_white, analysis.geometry).
    """

    d_min_used: Triple
    fallback_applied: bool
    group_id: int
    is_bw: bool
    look: LookParams
    crossover: Triple = NO_CROSSOVER
    crossover_source: CrossoverSource = "none"
    d_white_used: Triple | None = None
    geometry: FrameGeometry | None = None


def group_by_signature(
    signatures: Sequence[tuple[float, float]], hue_tol: float
) -> list[int]:
    """Single-linkage grouping; ids follow the order of first appearance."""
    parent = list(range(len(signatures)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, a in enumerate(signatures):
        for j in range(i + 1, len(signatures)):
            b = signatures[j]
            if math.hypot(a[0] - b[0], a[1] - b[1]) < hue_tol:
                parent[find(i)] = find(j)
    labels: dict[int, int] = {}
    return [labels.setdefault(find(i), len(labels)) for i in range(len(signatures))]


def decide(
    analyses: Sequence[FrameAnalysis], settings: RollSettings
) -> list[RollDecision]:
    """Choose film base, white point, crossover, frame and look per frame.

    Film base: a high-key frame borrows the roll baseline. White point: its
    level stays the frame's own, its colour (the ratio of the channels)
    leans on the roll. Crossover: measured per colour frame with the film
    base and white point finally used, combined with the roll's value.
    Frame: a frame whose border was not found, or that came out smaller or
    in another format than the roll's frames, gets the roll's frame size.
    Look: the base look plus a top-up from the median statistics of its
    group (high-key frames left out while others exist); the statistics are
    those of the crossover-corrected preview.
    """
    groups = group_by_signature([a.signature for a in analyses], settings.hue_tol)
    members = [
        [m for m, g in zip(analyses, groups, strict=True) if g == group]
        for group in groups
    ]
    baselines = [
        _high_key_baseline(analysis, group_members, settings)
        for analysis, group_members in zip(analyses, members, strict=True)
    ]
    d_min_used = [
        analysis.d_min if baseline is None else baseline
        for analysis, baseline in zip(analyses, baselines, strict=True)
    ]
    is_bw = [
        _group_is_bw(analysis, group_members)
        for analysis, group_members in zip(analyses, members, strict=True)
    ]
    for index, (analysis, bw) in enumerate(zip(analyses, is_bw, strict=True)):
        if bw != analysis.is_bw:
            log.info(
                "frame %d: roll majority overrides measurement, developed as %s",
                index,
                "bw" if bw else "colour",
            )
    d_white_used = _roll_white(analyses, d_min_used, groups, is_bw, settings)
    # BW frames are not measured; a roll group is all BW or all colour
    # and a roll value needs three measured frames, so BW frames get none.
    mids = [
        None if bw else frame_mids(a.density_sample, d_min, d_white or a.d_white)
        for a, d_min, d_white, bw in zip(
            analyses, d_min_used, d_white_used, is_bw, strict=True
        )
    ]
    crossover = crossover_per_frame(
        mids, groups, settings.crossover_limit, settings.crossover_roll_limit
    )
    stats = [
        look_stats_for(analysis, k)
        for analysis, (k, _) in zip(analyses, crossover, strict=True)
    ]
    geometries = _roll_geometry(analyses, groups)
    decisions: list[RollDecision] = []
    for index, group in enumerate(groups):
        regular = [
            st
            for st, g, b in zip(stats, groups, baselines, strict=True)
            if g == group and b is None
        ]
        everyone = [st for st, g in zip(stats, groups, strict=True) if g == group]
        look = look_params(
            stats[index],
            is_bw[index],
            _group_tone(regular or everyone),
            base_contrast=settings.contrast,
            base_saturation=settings.saturation,
        )
        k, source = crossover[index]
        decisions.append(
            RollDecision(
                d_min_used[index],
                baselines[index] is not None,
                group,
                is_bw[index],
                look,
                crossover=k,
                crossover_source=source,
                d_white_used=d_white_used[index],
                geometry=geometries[index],
            )
        )
    return decisions


def exposure_findings(
    analyses: Sequence[FrameAnalysis], decisions: Sequence[RollDecision]
) -> list[ExposureFinding]:
    """How the scans were exposed, judged by the film base of each roll group.

    The film base is the brightest part of a negative. "under": in some
    group its brightest channel sits (median over the frames) below
    BASE_TOO_DARK of the sensor range, so the picture uses only the noisy
    lower end. "over": it reaches BASE_CLIPPED, so the base (and with it
    the colour) cannot be measured.
    """
    per_group: dict[int, list[float]] = {}
    for analysis, decision in zip(analyses, decisions, strict=True):
        per_group.setdefault(decision.group_id, []).append(10.0 ** -min(analysis.d_min))
    medians = [float(np.median(values)) for values in per_group.values()]
    findings: list[ExposureFinding] = []
    if any(value < BASE_TOO_DARK for value in medians):
        findings.append("under")
    if any(value >= BASE_CLIPPED for value in medians):
        findings.append("over")
    return findings


def keystone_finding(analyses: Sequence[FrameAnalysis]) -> float | None:
    """Degrees by which opposite frame edges are not parallel, or None.

    The camera of a scanning setup stays where it is, so a tilt against the
    film shows in every frame the same way. The median over the frames of
    the angle between top and bottom edge, and between left and right edge
    (at least ROLL_MIN_FRAMES measured frames each), is therefore reliable
    where a single frame is not. Returns the larger of the two medians (as
    a magnitude) if it exceeds KEYSTONE_TOLERANCE.
    """
    worst = 0.0
    for pair in (0, 1):
        values = [
            skew
            for analysis in analyses
            if (skew := analysis.geometry.edge_skew[pair]) is not None
        ]
        if len(values) >= ROLL_MIN_FRAMES:
            worst = max(worst, abs(float(np.median(values))))
    return worst if worst > KEYSTONE_TOLERANCE else None


def _group_tone(stats: Sequence[LookStats]) -> LookStats:
    """Median spread and chroma over the members (a singleton: its own)."""
    values = np.array([(st.spread, st.chroma) for st in stats])
    spread, chroma = (float(v) for v in np.median(values, axis=0))
    return LookStats(spread=spread, chroma=chroma)


def _group_is_bw(analysis: FrameAnalysis, members: Sequence[FrameAnalysis]) -> bool:
    """Majority of the roll group decides; ties and singletons see colour/own."""
    if len(members) < 2:
        return analysis.is_bw
    return sum(m.is_bw for m in members) * 2 > len(members)


def _comparable_base(member: FrameAnalysis, exposures_known: bool) -> np.ndarray:
    """Film base density on a scale shared by scans of different exposure.

    A scan exposed longer measures every density lower by the logarithm of
    the factor; adding the scan exposure takes that out. Without exposure
    data for all frames the measured values are compared as they are.
    """
    base = np.array(member.d_min, np.float64)
    if exposures_known and member.exposure is not None:
        base += member.exposure
    return base


def _high_key_baseline(
    analysis: FrameAnalysis,
    members: Sequence[FrameAnalysis],
    settings: RollSettings,
) -> Triple | None:
    if len(members) < 2:
        return None
    known = all(m.exposure is not None for m in members)
    d_mins = np.array([_comparable_base(m, known) for m in members])
    baseline = np.quantile(d_mins, 0.25, axis=0)
    excess = _comparable_base(analysis, known) - baseline
    lifted = float(excess.min()) > settings.highkey_delta
    uniform = float(excess.max()) <= settings.uniform_ratio * float(excess.min())
    median_sig = np.median(np.array([m.signature for m in members]), axis=0)
    hue_ok = (
        math.hypot(
            analysis.signature[0] - float(median_sig[0]),
            analysis.signature[1] - float(median_sig[1]),
        )
        < settings.hue_tol
    )
    if lifted and uniform and hue_ok:
        # back to this scan's own density scale
        shift = analysis.exposure if known and analysis.exposure is not None else 0.0
        own = baseline - shift
        return (float(own[0]), float(own[1]), float(own[2]))
    return None


def _white_ratio(d_min: Triple, d_white: Triple) -> tuple[np.ndarray, float]:
    """Channel ratio (mean 1) and level of the spread from base to white."""
    spread = np.maximum(
        np.asarray(d_white, np.float64) - np.asarray(d_min, np.float64), MIN_SPREAD
    )
    level = float(spread.mean())
    return spread / level, level


def _roll_white(
    analyses: Sequence[FrameAnalysis],
    d_min_used: Sequence[Triple],
    groups: Sequence[int],
    is_bw: Sequence[bool],
    settings: RollSettings,
) -> list[Triple | None]:
    """White point per frame with the colour of the roll, None = the frame's own.

    The white point of a frame is the density of its brightest part, per
    channel. Its level (mean over the channels) belongs to the frame; the
    ratio of the channels is a property of the film, unless the brightest
    part of the picture is coloured (blue sky, a lamp): then the frame's own
    ratio would turn that colour into white. With at least ROLL_MIN_FRAMES
    colour frames in the group the ratio is the roll's median times half of
    the frame's own deviation from it, limited to +-white_limit. BW frames,
    small groups and white_limit 0 keep the frame's own white point.
    """
    result: list[Triple | None] = [None] * len(analyses)
    if settings.white_limit <= 0.0:
        return result
    ratios = [
        _white_ratio(d_min, a.d_white)
        for a, d_min in zip(analyses, d_min_used, strict=True)
    ]
    for group in set(groups):
        indices = [i for i, g in enumerate(groups) if g == group and not is_bw[i]]
        if len(indices) < ROLL_MIN_FRAMES:
            continue
        roll = np.median(np.array([ratios[i][0] for i in indices]), axis=0)
        roll /= roll.mean()
        for i in indices:
            own, level = ratios[i]
            deviation = np.clip(
                np.sqrt(own / roll),
                1.0 - settings.white_limit,
                1.0 + settings.white_limit,
            )
            ratio = roll * deviation
            ratio /= ratio.mean()
            white = np.asarray(d_min_used[i], np.float64) + level * ratio
            result[i] = (float(white[0]), float(white[1]), float(white[2]))
    return result


def _relative_size(geometry: FrameGeometry) -> tuple[float, float]:
    """Frame size as a fraction of the preview width (previews may differ)."""
    width = float(geometry.source_shape[1])
    return geometry.size[0] / width, geometry.size[1] / width


def _roll_geometry(
    analyses: Sequence[FrameAnalysis], groups: Sequence[int]
) -> list[FrameGeometry | None]:
    """Frame per frame fitted to the roll's frame size, None = the frame's own.

    All frames of a roll have the same size and format. A dark picture edge
    (night sky, a black wall) looks like unexposed film, so a single frame
    may be cut there, snap to a smaller format or find no border at all.
    With at least ROLL_MIN_FRAMES confident frames of one format and
    orientation in the group, their median size is the roll's frame size
    (only frames within SIZE_TOLERANCE of it count). Two kinds of frames
    of the group get that size, placed by their own frame edges
    (FrameGeometry.fitted):
    - a confident frame that is smaller by more than SIZE_TOLERANCE in one
      direction and larger in none: it was cut; the roll's frame covers it.
    - a frame that is not confident (the full film area was kept), if the
      roll's frame lies on clear edges at both ends in both directions.
    A confident frame that is larger in either direction is never touched:
    it may be another format. A frame that cannot be placed stays as it is.
    """
    result: list[FrameGeometry | None] = [None] * len(analyses)
    for group in set(groups):
        indices = [i for i, g in enumerate(groups) if g == group]
        confident = [
            analyses[i].geometry for i in indices if analyses[i].geometry.confident
        ]
        if len(confident) < ROLL_MIN_FRAMES:
            continue
        kinds = Counter((g.aspect, g.size[0] >= g.size[1]) for g in confident)
        (aspect, landscape), count = kinds.most_common(1)[0]
        if count < ROLL_MIN_FRAMES:
            continue
        sizes = np.array(
            [
                _relative_size(g)
                for g in confident
                if (g.aspect, g.size[0] >= g.size[1]) == (aspect, landscape)
            ]
        )
        median = np.median(sizes, axis=0)
        close = np.all(np.abs(sizes / median - 1.0) <= SIZE_TOLERANCE, axis=1)
        if int(close.sum()) < ROLL_MIN_FRAMES:
            continue
        roll_size = np.median(sizes[close], axis=0)
        for i in indices:
            own = analyses[i].geometry
            relative = np.array(_relative_size(own))
            if own.confident:
                larger = np.any(relative > roll_size * (1.0 + SIZE_TOLERANCE))
                smaller = np.any(relative < roll_size * (1.0 - SIZE_TOLERANCE))
                if larger or not smaller:
                    continue
            width = float(own.source_shape[1])
            size = (float(roll_size[0]) * width, float(roll_size[1]) * width)
            fitted = own.fitted(size, aspect, need_edges=not own.confident)
            if fitted is None:
                continue
            note = (
                f"frame size of the roll ({aspect}) used instead of the frame's "
                f"own ({own.aspect if own.confident else 'no format'})"
            )
            result[i] = replace(
                fitted, reason="; ".join(filter(None, [own.reason, note]))
            )
            log.info("frame %d: %s", i, note)
    return result
