"""Roll context: group frames by film-base hue and repair high-key frames."""

import logging
import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from real_fast_negconv.core.analyzer import FrameAnalysis, look_stats_for
from real_fast_negconv.core.converter import NO_CROSSOVER, Triple
from real_fast_negconv.core.crossover import (
    CrossoverSource,
    crossover_per_frame,
    frame_mids,
)
from real_fast_negconv.core.look import (
    LookParams,
    LookStats,
    look_params,
)

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RollSettings:
    """Thresholds for grouping, high-key fallback (5.5) and crossover (12.S)."""

    hue_tol: float = 0.06
    highkey_delta: float = 0.10
    uniform_ratio: float = 2.0
    crossover_limit: float = 0.15


@dataclass(frozen=True)
class RollDecision:
    """Film base, colour/bw, look and crossover actually used for a frame."""

    d_min_used: Triple
    fallback_applied: bool
    group_id: int
    is_bw: bool
    look: LookParams
    crossover: Triple = NO_CROSSOVER
    crossover_source: CrossoverSource = "none"


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
    """Choose film base per frame, borrowing roll baseline for high-key frames.

    Crossover (spec 12.S): measured per colour frame with the film base
    finally used, combined with the roll's value. Look (spec 12.V): contrast and
    saturation from the median statistics of its group (high-key frames left
    out while others exist); the statistics are those of the
    crossover-corrected preview.
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
    # BW frames are not measured; a roll group is all BW or all colour (12.C)
    # and a roll value needs three measured frames, so BW frames get none.
    mids = [
        None if bw else frame_mids(a.density_sample, d_min, a.d_white)
        for a, d_min, bw in zip(analyses, d_min_used, is_bw, strict=True)
    ]
    crossover = crossover_per_frame(mids, groups, settings.crossover_limit)
    stats = [
        look_stats_for(analysis, k)
        for analysis, (k, _) in zip(analyses, crossover, strict=True)
    ]
    decisions: list[RollDecision] = []
    for index, group in enumerate(groups):
        regular = [
            st
            for st, g, b in zip(stats, groups, baselines, strict=True)
            if g == group and b is None
        ]
        everyone = [st for st, g in zip(stats, groups, strict=True) if g == group]
        look = look_params(stats[index], is_bw[index], _group_tone(regular or everyone))
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
            )
        )
    return decisions


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


def _high_key_baseline(
    analysis: FrameAnalysis,
    members: Sequence[FrameAnalysis],
    settings: RollSettings,
) -> Triple | None:
    if len(members) < 2:
        return None
    d_mins = np.array([m.d_min for m in members])
    baseline = np.quantile(d_mins, 0.25, axis=0)
    excess = np.array(analysis.d_min) - baseline
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
        return (float(baseline[0]), float(baseline[1]), float(baseline[2]))
    return None
