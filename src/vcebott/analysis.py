"""Separator rankings and quantile analytics over parsed report data."""

from __future__ import annotations

import pandas as pd

from .config import processed_dir
from .stats import distribution_mean, separation_metrics


def marks_frame(subject: str) -> pd.DataFrame:
    path = processed_dir() / f"{subject}-marks.parquet"
    if not path.exists():
        raise FileNotFoundError(f"{path} missing; run `vcebott parse {subject}` first")
    return pd.read_parquet(path)


def question_distribution(frame: pd.DataFrame, key: tuple) -> dict[int, float]:
    """Distribution {mark: pct} for one (year, exam, nht, question) key."""
    sub = frame[
        (frame["year"] == key[0])
        & (frame["exam"] == key[1])
        & (frame["nht"] == key[2])
        & (frame["question"] == key[3])
    ]
    return dict(zip(sub["mark"], sub["pct"], strict=True))


def separator_table(frame: pd.DataFrame) -> pd.DataFrame:
    """Per-question separation metrics, ranked by gap within each exam session."""
    rows = []
    for key, group in frame.groupby(["year", "exam", "nht", "question"], sort=True):
        dist = dict(zip(group["mark"], group["pct"], strict=True))
        metrics = separation_metrics(dist)
        rows.append(
            {
                "year": key[0],
                "exam": key[1],
                "nht": key[2],
                "question": key[3],
                "marks_available": metrics["marks_available"],
                "average": metrics["average"],
                "top_quartile_mean": metrics["top_quartile_mean"],
                "gap": metrics["gap"],
                "pct_zero": metrics["pct_zero"],
            }
        )
    table = pd.DataFrame(rows)
    table["gap_rank"] = table.groupby(["year", "exam", "nht"])["gap"].rank(
        ascending=False, method="min"
    )
    return table.sort_values(["year", "exam", "nht", "gap_rank"], ignore_index=True)


def topic_difficulty(frame: pd.DataFrame, topics: pd.DataFrame) -> pd.DataFrame:
    """Aggregate separation by topic across years, given classifier labels.

    `topics` carries paper-block question numbers ('1'); separator labels are
    report labels ('1a') — both map to the leading question number.
    """
    separators = separator_table(frame)
    separators["qnum"] = separators["question"].str.extract(r"^(\d+)", expand=False)
    topics = topics.copy()
    topics["qnum"] = topics["question"].astype(str).str.extract(r"^(\d+)", expand=False)
    joined = topics.merge(
        separators,
        on=["year", "exam", "nht", "qnum"],
        how="inner",
    )
    return (
        joined.groupby("topic")
        .agg(
            questions=("question", "size"),
            mean_gap=("gap", "mean"),
            mean_pct_zero=("pct_zero", "mean"),
            mean_average=("average", "mean"),
        )
        .sort_values("mean_gap", ascending=False)
        .reset_index()
    )


def run_analysis(subject: str) -> None:
    frame = marks_frame(subject)
    separators = separator_table(frame)

    out_dir = processed_dir()
    sep_path = out_dir / f"{subject}-separators.parquet"
    separators.to_parquet(sep_path, index=False)
    print(f"separator table: {len(separators)} questions -> {sep_path}")

    top = separators[separators["gap_rank"] <= 3].sort_values(
        ["year", "exam", "nht", "gap_rank"]
    )
    print("\nTop separating questions per session:")
    for row in top.itertuples(index=False):
        label = f"{row.year} exam{row.exam}" + (" NHT" if row.nht else "")
        print(
            f"  {label:16} Q{row.question:6} "
            f"avg {row.average:.2f}/{row.marks_available}  "
            f"gap {row.gap:.2f}  zero {row.pct_zero:.0f}%"
        )

    topics_path = out_dir / f"{subject}-topics.parquet"
    if topics_path.exists():
        topics = pd.read_parquet(topics_path)
        by_topic = topic_difficulty(frame, topics)
        topic_path = out_dir / f"{subject}-topic-difficulty.parquet"
        by_topic.to_parquet(topic_path, index=False)
        print("\nDifficulty by topic (mean separation gap):")
        for row in by_topic.itertuples(index=False):
            print(
                f"  {row.topic:24} gap {row.mean_gap:.2f}  zero {row.mean_pct_zero:.0f}%"
            )
    else:
        print("\n(no topic labels yet; run `vcebott classify` for topic difficulty)")

    # Sanity: distribution means should match VCAA's published averages.
    mismatch = 0
    for key, group in frame.groupby(["year", "exam", "nht", "question"]):
        if pd.isna(group["average"].iloc[0]):
            continue
        published = float(group["average"].iloc[0])
        computed = distribution_mean(
            dict(zip(group["mark"], group["pct"], strict=True))
        )
        if abs(computed - published) > 0.11:
            mismatch += 1
            if mismatch <= 5:
                label = f"{key[0]} exam{key[1]} Q{key[3]}"
                print(
                    f"  WARN {label}: computed mean {computed:.2f} vs published {published:.2f}"
                )
    print(
        f"\naverage cross-check: {mismatch} mismatches out of {len(separators)} questions"
    )
