"""Quantile and separator mathematics over per-question mark distributions.

All functions are pure and fixture-tested. Distributions are {mark: percentage}
covering every mark from 0..marks_available; percentages should sum to ~100
(VCAA rounds, so sums may be off by a point or two).
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np


def normalized(dist: Mapping[int, float]) -> dict[int, float]:
    """Percentages normalised to sum exactly 100 over the full mark range."""
    marks = range(max(dist) + 1)
    total = sum(dist.get(m, 0.0) for m in marks)
    if total <= 0:
        raise ValueError("empty or non-positive distribution")
    return {m: dist.get(m, 0.0) * 100.0 / total for m in marks}


def percentile_at(dist: Mapping[int, float], score: float) -> float:
    """Share of the state scoring at or below `score` (0-100)."""
    norm = normalized(dist)
    return sum(p for mark, p in norm.items() if mark <= score)


def distribution_mean(dist: Mapping[int, float]) -> float:
    norm = normalized(dist)
    return sum(mark * p for mark, p in norm.items()) / 100.0


def top_quartile_mean(dist: Mapping[int, float]) -> float:
    """Mean mark of the top 25% of the state, exact under the given distribution."""
    norm = normalized(dist)
    share = 25.0
    weighted = 0.0
    for mark in sorted(norm, reverse=True):
        take = min(norm[mark], share)
        weighted += mark * take
        share -= take
        if share <= 0:
            break
    return weighted / 25.0


def separation_metrics(dist: Mapping[int, float]) -> dict[str, float]:
    """How sharply a question separates strong students from the rest.

    gap = top-quartile mean - overall mean; pct_zero = share scoring nothing.
    """
    norm = normalized(dist)
    avg = distribution_mean(norm)
    tq = top_quartile_mean(norm)
    return {
        "marks_available": max(norm),
        "average": avg,
        "top_quartile_mean": tq,
        "gap": tq - avg,
        "pct_zero": norm.get(0, 0.0),
    }


def total_score_distribution(dists: list[Mapping[int, float]]) -> np.ndarray:
    """Exact distribution of the total score, assuming question-level independence.

    Returns probabilities over total marks 0..sum(marks_available).
    """
    current = np.array([1.0])
    for dist in dists:
        norm = normalized(dist)
        max_mark = max(norm)
        vec = np.zeros(max_mark + 1)
        for mark, p in norm.items():
            vec[mark] = p / 100.0
        current = np.convolve(current, vec)
    return current


def exam_percentile(dists: list[Mapping[int, float]], marks: list[int]) -> float:
    """Share of the state whose total is at or below the student's total (0-100).

    Independence across questions is assumed; treat as an estimate.
    """
    if len(dists) != len(marks):
        raise ValueError("one mark per question distribution required")
    total = np.cumsum(total_score_distribution(dists))
    student_total = sum(marks)
    return float(min(total[student_total], 1.0) * 100.0)


def question_percentiles(
    dists: list[Mapping[int, float]], marks: list[int]
) -> list[float]:
    """Per-question percentile of a student's mark vs the state."""
    if len(dists) != len(marks):
        raise ValueError("one mark per question distribution required")
    return [percentile_at(dist, mark) for dist, mark in zip(dists, marks, strict=True)]
