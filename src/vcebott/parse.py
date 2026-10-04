"""Parse VCAA external assessment reports into tidy per-question mark distributions.

Both eras carry the same table shape per question:

    Question 1a.
     Marks   0    1    2    Average
        %   42   58   0.6

PDF reports (up to 2019) are parsed via pdftotext -layout; DOCX reports (2020+)
via python-docx. Output is a tidy long table: one row per (session, question, mark).
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

_QUESTION_RE = re.compile(r"^\s*Question\s+(\d+[a-z]*)\s*[.:]?\s*$", re.IGNORECASE)
_INT_RE = re.compile(r"^\d+$")
_FLOAT_RE = re.compile(r"^-?\d+(?:\.\d+)?$")


@dataclass(frozen=True)
class QuestionStats:
    question: str
    marks_available: int
    distribution: dict[int, float]  # mark -> percentage of the state
    average: float | None


def _tokens(line: str) -> list[str]:
    return line.split()


def _num(token: str) -> float:
    """Numeric token, treating '--'/'-'/'—' placeholders as zero."""
    if token in {"--", "-", "—", "–"}:
        return 0.0
    return float(token.replace(",", ""))


def parse_report_pdf(path: Path) -> list[QuestionStats]:
    text = subprocess.run(
        ["pdftotext", "-layout", str(path), "-"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    lines = text.splitlines()
    stats: list[QuestionStats] = []
    label: str | None = None
    i = 0
    while i < len(lines):
        line = lines[i]
        match = _QUESTION_RE.match(line)
        if match:
            label = match.group(1).lower()
            i += 1
            continue
        if re.match(r"^\s*Marks\b", line):
            header = _tokens(line)
            marks_tokens = header[1:]
            has_average = "Average" in header
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines) and lines[j].lstrip().startswith("%"):
                pct_tokens = _tokens(lines[j].lstrip())[1:]
                parsed = _match_rows(marks_tokens, pct_tokens, has_average)
                if parsed is not None and label is not None:
                    stats.append(_make_stats(label, *parsed))
            label = None  # a Marks table consumes the pending label
        i += 1
    return stats


def _match_rows(
    marks_tokens: list[str], pct_tokens: list[str], has_average: bool
) -> tuple[int, dict[int, float], float | None] | None:
    marks = [int(tok) for tok in marks_tokens if _INT_RE.match(tok)]
    if not marks or "Average" in marks_tokens and not has_average:
        return None
    values = [
        _num(tok)
        for tok in pct_tokens
        if _FLOAT_RE.match(tok) or tok in {"--", "-", "—", "–"}
    ]
    if len(pct_tokens) != len(values):
        return None
    average: float | None = None
    if has_average and len(values) == len(marks) + 1:
        average = values[-1]
        values = values[:-1]
    elif has_average and len(marks_tokens) - 1 == len(marks):
        # 'Average' column header present but empty in the % row.
        pass
    if len(values) != len(marks):
        return None
    return marks[-1], dict(zip(marks, values, strict=True)), average


def _make_stats(
    question: str,
    marks_available: int,
    distribution: dict[int, float],
    average: float | None,
) -> QuestionStats:
    return QuestionStats(
        question=question,
        marks_available=marks_available,
        distribution=distribution,
        average=average,
    )


def parse_report_docx(path: Path) -> list[QuestionStats]:
    doc = Document(str(path))
    stats: list[QuestionStats] = []
    label: str | None = None
    for child in doc.element.body.iterchildren():
        if child.tag.endswith("}p"):
            text = Paragraph(child, doc).text.strip()
            match = _QUESTION_RE.match(text)
            label = match.group(1).lower() if match else label
        elif child.tag.endswith("}tbl"):
            table = Table(child, doc)
            parsed = _parse_docx_table(table)
            if parsed is not None and label is not None:
                stats.append(_make_stats(label, *parsed))
            label = None
    return stats


def _parse_docx_table(
    table: Table,
) -> tuple[int, dict[int, float], float | None] | None:
    rows = [[cell.text.strip() for cell in row.cells] for row in table.rows]
    if len(rows) < 2:
        return None
    header = rows[0]
    if not header or header[0].strip().lower() != "marks":
        return None
    has_average = any(cell.lower() == "average" for cell in header[1:])
    marks_tokens = [cell for cell in header[1:] if cell.lower() != "average"]
    pct_row = rows[1]
    pct_tokens = [cell for cell in pct_row[1:] if cell.strip().lower() != "average"]
    if pct_row and pct_row[0].strip().lower() not in {"%", ""}:
        return None
    return _match_rows(marks_tokens, pct_tokens, has_average)


def parse_report(path: Path) -> list[QuestionStats]:
    if path.suffix.lower() == ".pdf":
        return parse_report_pdf(path)
    if path.suffix.lower() == ".docx":
        return parse_report_docx(path)
    raise ValueError(f"unsupported report format: {path}")


def tidy_table(
    subject: str, year: int, exam: int | None, nht: bool, stats: list[QuestionStats]
) -> pd.DataFrame:
    rows = []
    for item in stats:
        for mark, pct in sorted(item.distribution.items()):
            rows.append(
                {
                    "subject": subject,
                    "year": year,
                    "exam": exam,
                    "nht": nht,
                    "question": item.question,
                    "marks_available": item.marks_available,
                    "mark": mark,
                    "pct": pct,
                    "average": item.average,
                }
            )
    return pd.DataFrame(rows)


def parse_subject_reports(subject: str) -> pd.DataFrame:
    """Parse every report under data/raw/<subject>/ into one tidy DataFrame."""
    import json

    from .config import manifest_path

    manifest = (
        json.loads(manifest_path().read_text()) if manifest_path().exists() else {}
    )
    frames: list[pd.DataFrame] = []
    nht_without_stats: list[str] = []
    for entry in manifest.get(subject, {}).get("entries", []):
        if entry["kind"] != "report":
            continue
        path = Path(entry["path"])
        if not path.exists():
            continue
        stats = parse_report(path)
        frame = tidy_table(subject, entry["year"], entry["exam"], entry["nht"], stats)
        if frame.empty:
            nht_without_stats.append(
                f"{entry['year']} exam{entry['exam']} NHT" if entry["nht"] else str(entry["year"])
            )
            continue
        frames.append(frame)
    if nht_without_stats:
        print(
            f"no mark-distribution tables in {len(nht_without_stats)} NHT reports "
            "(VCAA publishes sample answers only for NHT): "
            + ", ".join(nht_without_stats)
        )
    if not frames:
        return pd.DataFrame(
            columns=[
                "subject",
                "year",
                "exam",
                "nht",
                "question",
                "marks_available",
                "mark",
                "pct",
                "average",
            ]
        )
    return pd.concat(frames, ignore_index=True)
