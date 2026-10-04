"""Topic classification of exam questions via a Simple Jev classifier endpoint.

Self-hosted Simple Jev (featherless-ai/simple-jev) exposes POST /v1/classifier:
send `state` (question text) + typed `questions`, get calibrated probabilities
back. Runs fully local/keyless against Qwen/Qwen3.5-0.8B by default.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import httpx
import pandas as pd

from .config import processed_dir

TOPICS: dict[str, str] = {
    "algebra-functions": "Functions, relations and graphs: polynomial, exponential, logarithmic and circular functions; maximal domain, range, implied domain; inverse and composite functions; sketching graphs, asymptotes, axial intercepts; transformations. Trigger phrases: 'state the range', 'maximal domain', 'rule of the inverse', 'composite', 'sketch the graph'",
    "algebra-structure": "Algebraic manipulation: solving equations and inequations (including exponential equations like 2^(2x) - 9*2^x + 20 = 0 via substitution), simultaneous equations, factorising, index and logarithm laws. Trigger: 'solve ... for x', 'evaluate ... giving your answer as an integer'",
    "differential-calculus": "Differentiation and rates of change: finding derivatives, gradient of a tangent, stationary points, curve sketching via f', optimisation (maximum/minimum of a real-world quantity), kinematics, average rate of change. Trigger phrases: 'find the derivative', 'dy/dx', 'f'(x)', 'maximum volume/area of a physical object', 'rate of change'",
    "integral-calculus": "Integration: antiderivatives, definite integrals, area under a curve, area between curves, average value of a function over an interval, differential equations by antidifferentiation, numerical area approximation (trapezium or rectangle rule). Trigger phrases: 'dx' with an integral sign, 'area under', 'area enclosed by', 'approximate the area using trapeziums/rectangles', 'average value of the function', 'find f given f''",
    "trigonometry": "Trigonometric identities, exact values, and equations: solving sin/cos/tan equations over a domain, sine rule and cosine rule, exact values of sin(x) + cos(y) with given constraints",
    "probability-discrete": "Discrete probability: coins, dice, selections without replacement, probability rules (Pr of unions, complements, conditional probability, independence), combinatorics, discrete random variables, binomial distribution ('plays n games', 'at least two successes')",
    "probability-continuous": "Continuous probability: probability density functions (piecewise or with unknown constants), expected value, cumulative distribution, Pr(X > a) for continuous X",
    "statistics": "Statistics from samples: sample proportion (P-hat) and its distribution, sample mean, standard deviation of a sample statistic, confidence intervals. Trigger phrases: 'sample proportion', 'randomly selects n', 'P-hat', 'confidence interval'",
}

_MARKS_RE = re.compile(r"\((\d+)\s*marks?\)", re.IGNORECASE)
_HEADING_RE = re.compile(
    r"^\s*Question\s+(\d+[a-z]*)\s*[.:]?\s*(?:\(\d+\s*marks?\))?\s*$", re.IGNORECASE
)
_END_RE = re.compile(r"^\s*(?:END OF|Section\s+\d|SECTION\s+\d)", re.IGNORECASE)
_QNUM_RE = re.compile(r"\d+")


@dataclass(frozen=True)
class JevConfig:
    base_url: str = "http://127.0.0.1:8777"
    model: str = "Qwen/Qwen3.5-0.8B"
    timeout_s: float = 120.0


def classify_text(text: str, config: JevConfig) -> dict:
    """Ask the Jev endpoint which topic a question tests. Returns the raw answer."""
    body = {
        "model": config.model,
        "state": text,
        "questions": {
            "topic": {
                "type": "choice",
                "instructions": (
                    "Which VCE Maths Methods topic does this question primarily test? "
                    "Judge by the mathematics being asked, not surface keywords."
                ),
                "criteria": TOPICS,
            }
        },
    }
    resp = httpx.post(
        f"{config.base_url}/v1/classifier", json=body, timeout=config.timeout_s
    )
    resp.raise_for_status()
    payload = resp.json()
    answer = payload["answers"]["topic"]
    return {
        "topic": answer["choice"],
        "confidence": answer["confidence"],
        "probabilities": answer["probabilities"],
    }


_FURNITURE_RE = re.compile(
    r"do not write in this area|TURN OVER|VM \d|VCE \d|\d{4} (?:MATHMETH|SPECMATH|FURTMAT|GENGMAT) EXAM \d(?: \(NHT\))?|"
    r"^\s*\d+\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def _clean_text(text: str) -> str:
    """Strip page furniture and collapse the whitespace pdftotext scatters."""
    text = _FURNITURE_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def extract_question_blocks(paper: Path) -> dict[str, str]:
    """Split an exam paper PDF into {question_number: text} via pdftotext."""
    text = subprocess.run(
        ["pdftotext", "-layout", str(paper), "-"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    blocks: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        heading = _HEADING_RE.match(line)
        if heading:
            current = heading.group(1).lower()
            blocks[current] = []
            continue
        if _END_RE.match(line):
            current = None
            continue
        if current is not None and line.strip():
            blocks[current].append(line.strip())
    return {num: " ".join(parts).strip() for num, parts in blocks.items() if parts}


def question_text_table(subject: str) -> pd.DataFrame:
    """Extract question text for every scraped paper of a subject."""
    from .config import manifest_path

    manifest = (
        json.loads(manifest_path().read_text()) if manifest_path().exists() else {}
    )
    rows = []
    for entry in manifest.get(subject, {}).get("entries", []):
        if entry["kind"] != "paper":
            continue
        path = Path(entry["path"])
        if not path.exists():
            continue
        for num, text in extract_question_blocks(path).items():
            text = _clean_text(_MARKS_RE.sub("", text))
            rows.append(
                {
                    "subject": subject,
                    "year": entry["year"],
                    "exam": entry["exam"],
                    "nht": entry["nht"],
                    "question": num,
                    "text": text,
                }
            )
    return pd.DataFrame(rows)


def labeled_sample() -> list[dict]:
    """Hand-labeled (year, exam, question) sample used for accuracy evaluation.

    Labels reflect the primary area of study each question examines, judged from
    the published papers. Kept in-repo so accuracy checks are deterministic.
    """
    sample_path = (
        Path(__file__).resolve().parents[2]
        / "tests"
        / "fixtures"
        / "topic-sample.jsonl"
    )
    if not sample_path.exists():
        return []
    return [
        json.loads(line)
        for line in sample_path.read_text().splitlines()
        if line.strip()
    ]


def run_classify(subject: str, *, evaluate: bool = False) -> None:
    config = JevConfig()
    if evaluate:
        _evaluate_sample(config)
        return
    texts = question_text_table(subject)
    if texts.empty:
        raise SystemExit("no question text extracted; run scrape first")
    out_dir = processed_dir()
    texts_path = out_dir / f"{subject}-question-text.parquet"
    texts.to_parquet(texts_path, index=False)
    print(f"question text: {len(texts)} blocks -> {texts_path}")

    labels = []
    for row in texts.itertuples(index=False):
        if len(row.text) < 20:
            continue
        result = classify_text(row.text, config)
        labels.append(
            {
                "subject": subject,
                "year": row.year,
                "exam": row.exam,
                "nht": row.nht,
                "question": row.question,
                "topic": result["topic"],
                "confidence": result["confidence"],
            }
        )
    frame = pd.DataFrame(labels)
    topics_path = out_dir / f"{subject}-topics.parquet"
    frame.to_parquet(topics_path, index=False)
    print(f"topic labels: {len(frame)} questions -> {topics_path}")


def _evaluate_sample(config: JevConfig) -> None:
    sample = labeled_sample()
    if not sample:
        raise SystemExit("labeled sample missing at tests/fixtures/topic-sample.jsonl")
    texts = question_text_table(sample[0].get("subject", "methods"))
    lookup = {
        (row.year, row.exam, row.nht, row.question): row.text
        for row in texts.itertuples(index=False)
    }
    correct = 0
    total = 0
    for item in sample:
        key = (item["year"], item["exam"], item["nht"], item["question"])
        text = lookup.get(key)
        if text is None:
            print(f"  MISS {key}: no extracted text")
            total += 1
            continue
        result = classify_text(text, config)
        ok = result["topic"] == item["topic"]
        total += 1
        correct += ok
        flag = "ok  " if ok else "MISS"
        nht_tag = " NHT" if item["nht"] else ""
        print(
            f"  {flag} {item['year']} exam{item['exam']}{nht_tag} Q{item['question']}: "
            f"got {result['topic']} ({result['confidence']:.2f}), want {item['topic']}"
        )
    accuracy = correct / total if total else 0.0
    print(f"accuracy: {correct}/{total} = {accuracy:.0%} (threshold 90%)")
    if accuracy < 0.9:
        raise SystemExit(1)
