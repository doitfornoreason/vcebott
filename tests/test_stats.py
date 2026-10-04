import pytest

from vcebott.stats import (
    distribution_mean,
    exam_percentile,
    normalized,
    percentile_at,
    question_percentiles,
    separation_metrics,
    top_quartile_mean,
    total_score_distribution,
)


def test_normalized_fills_missing_marks():
    norm = normalized({0: 50, 2: 50})
    assert norm == {0: 50.0, 1: 0.0, 2: 50.0}


def test_percentile_at_cumulative():
    dist = {0: 42, 1: 58}
    assert percentile_at(dist, 0) == 42
    assert percentile_at(dist, 1) == 100
    assert percentile_at(dist, 5) == 100


def test_percentile_at_partial():
    # 2018 exam 1 Q1b: 10/39/51 split
    dist = {0: 10, 1: 39, 2: 51}
    assert percentile_at(dist, 0) == 10
    assert percentile_at(dist, 1) == pytest.approx(49)
    assert percentile_at(dist, 2) == 100


def test_distribution_mean():
    assert distribution_mean({0: 42, 1: 58}) == pytest.approx(0.58)
    assert distribution_mean({0: 10, 1: 39, 2: 51}) == pytest.approx(1.41)


def test_top_quartile_mean_exact_bucket():
    dist = {0: 10, 1: 80, 2: 10}
    # top 25% = 10% at mark 2 + 15% at mark 1 -> (2*10 + 1*15)/25
    assert top_quartile_mean(dist) == pytest.approx(1.4)


def test_top_quartile_mean_dominant_top():
    assert top_quartile_mean({0: 42, 1: 58}) == pytest.approx(1.0)
    assert top_quartile_mean({0: 10, 1: 39, 2: 51}) == pytest.approx(2.0)


def test_separation_metrics():
    metrics = separation_metrics({0: 42, 1: 58})
    assert metrics["marks_available"] == 1
    assert metrics["average"] == pytest.approx(0.58)
    assert metrics["top_quartile_mean"] == pytest.approx(1.0)
    assert metrics["gap"] == pytest.approx(0.42)
    assert metrics["pct_zero"] == pytest.approx(42.0)


def test_total_score_distribution_convolution():
    dists = [{0: 50, 1: 50}, {0: 50, 1: 50}]
    probs = total_score_distribution(dists)
    assert probs.shape == (3,)
    assert probs[0] == pytest.approx(0.25)
    assert probs[1] == pytest.approx(0.5)
    assert probs[2] == pytest.approx(0.25)


def test_exam_percentile():
    dists = [{0: 50, 1: 50}, {0: 50, 1: 50}]
    assert exam_percentile(dists, [0, 1]) == pytest.approx(75.0)
    assert exam_percentile(dists, [1, 1]) == pytest.approx(100.0)
    assert exam_percentile(dists, [0, 0]) == pytest.approx(25.0)


def test_question_percentiles():
    dists = [{0: 42, 1: 58}, {0: 10, 1: 39, 2: 51}]
    assert question_percentiles(dists, [1, 0]) == [
        pytest.approx(100),
        pytest.approx(10),
    ]


def test_exam_percentile_length_mismatch():
    with pytest.raises(ValueError):
        exam_percentile([{0: 100}], [0, 0])
