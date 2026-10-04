"""Student dashboard: enter marks, see quantiles, weak topics and separators."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from .config import processed_dir
from .stats import exam_percentile, percentile_at, separation_metrics

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _load(subject: str = "methods") -> dict[str, pd.DataFrame]:
    out_dir = processed_dir()
    frames: dict[str, pd.DataFrame] = {}
    for name in ("marks", "separators", "topics", "question-text"):
        path = out_dir / f"{subject}-{name}.parquet"
        if path.exists():
            frames[name] = pd.read_parquet(path)
    return frames


def _sessions(marks: pd.DataFrame) -> list[dict]:
    rows = []
    for (year, exam, nht), group in marks.groupby(["year", "exam", "nht"], sort=False):
        rows.append({"year": int(year), "exam": int(exam), "nht": bool(nht)})
    return sorted(rows, key=lambda s: (s["year"], s["exam"], s["nht"]))


def _session_questions(marks: pd.DataFrame, year: int, exam: int, nht: bool) -> list[dict]:
    sub = marks[(marks["year"] == year) & (marks["exam"] == exam) & (marks["nht"] == nht)]
    questions: dict[str, dict] = {}
    for row in sub.itertuples(index=False):
        questions.setdefault(
            row.question,
            {
                "question": row.question,
                "marks_available": int(row.marks_available),
                "average": row.average,
            },
        )
    return sorted(questions.values(), key=lambda q: _question_sort_key(q["question"]))


def _question_sort_key(label: str) -> tuple:
    import re

    match = re.match(r"(\d+)([a-z]*)", label)
    if not match:
        return (9999, label)
    return (int(match.group(1)), match.group(2))


def create_app(subject: str = "methods") -> FastAPI:
    app = FastAPI(title="vcebott", docs_url=None, redoc_url=None)

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok"}

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request):
        frames = _load(subject)
        if "marks" not in frames:
            return templates.TemplateResponse(
                request,
                "index.html",
                {"sessions": [], "error": "No parsed data yet — run `vcebott scrape` then `vcebott parse`."},
            )
        return templates.TemplateResponse(
            request, "index.html", {"sessions": _sessions(frames["marks"]), "error": None}
        )

    @app.get("/session/{year}/{exam}/{nht}", response_class=HTMLResponse)
    def session_form(request: Request, year: int, exam: int, nht: bool):
        frames = _load(subject)
        marks = frames.get("marks")
        if marks is None:
            return RedirectResponse("/", status_code=302)
        questions = _session_questions(marks, year, exam, nht)
        return templates.TemplateResponse(
            request,
            "session.html",
            {"year": year, "exam": exam, "nht": nht, "questions": questions},
        )

    @app.post("/session/{year}/{exam}/{nht}", response_class=HTMLResponse)
    async def session_submit(
        request: Request,
        year: int,
        exam: int,
        nht: bool,
    ):
        frames = _load(subject)
        marks_frame = frames["marks"]
        questions = _session_questions(marks_frame, year, exam, nht)
        form = await request.form()
        entered: dict[str, float] = {}
        for question in questions:
            raw = form.get(f"q-{question['question']}", "")
            if raw == "" or raw is None:
                continue
            try:
                value = float(raw)
            except ValueError:
                continue
            entered[question["question"]] = max(0.0, min(value, question["marks_available"]))
        if not entered:
            return RedirectResponse(f"/session/{year}/{exam}/{nht}", status_code=302)

        # Per-question distributions in report-label order.
        sub = marks_frame[(marks_frame["year"] == year) & (marks_frame["exam"] == exam) & (marks_frame["nht"] == nht)]
        dists_by_label: dict[str, dict[int, float]] = defaultdict(dict)
        for row in sub.itertuples(index=False):
            dists_by_label[row.question][int(row.mark)] = float(row.pct)

        per_question = []
        dists_ordered = []
        marks_ordered = []
        for question in questions:
            label = question["question"]
            dist = dists_by_label.get(label, {})
            if not dist:
                continue
            dists_ordered.append(dist)
            mark = entered.get(label, 0.0)
            marks_ordered.append(mark)
            metrics = separation_metrics(dist)
            per_question.append(
                {
                    "question": label,
                    "your_mark": mark,
                    "max": question["marks_available"],
                    "state_avg": question["average"],
                    "percentile": percentile_at(dist, mark),
                    "gap": metrics["gap"],
                    "pct_zero": metrics["pct_zero"],
                }
            )

        exam_pct = exam_percentile(dists_ordered, [int(m) for m in marks_ordered])

        weak_topics = _weak_topics(frames, year, exam, nht, per_question)
        context = {
            "year": year,
            "exam": exam,
            "nht": nht,
            "questions": per_question,
            "exam_percentile": exam_pct,
            "exam_total": sum(q["your_mark"] for q in per_question),
            "exam_max": sum(q["max"] for q in per_question),
            "weak_topics": weak_topics,
            "entered": entered,
        }
        return templates.TemplateResponse(request, "report.html", context)

    @app.get("/separators", response_class=HTMLResponse)
    def separators(request: Request):
        frames = _load(subject)
        if "separators" not in frames:
            return templates.TemplateResponse(
                request, "separators.html", {"rows": [], "topics": [], "error": "No analysis yet — run `vcebott analyze`."}
            )
        table = frames["separators"]
        rows = []
        for (year, exam, nht), group in table.groupby(["year", "exam", "nht"], sort=False):
            top = group[group["gap_rank"] <= 5].sort_values("gap_rank")
            rows.append(
                {
                    "year": int(year),
                    "exam": int(exam),
                    "nht": bool(nht),
                    "questions": [
                        {
                            "question": r.question,
                            "avg": r.average,
                            "max": r.marks_available,
                            "gap": r.gap,
                            "pct_zero": r.pct_zero,
                        }
                        for r in top.itertuples(index=False)
                    ],
                }
            )
        rows.sort(key=lambda s: (s["year"], s["exam"], s["nht"]), reverse=True)
        topics = []
        topics_path = processed_dir() / f"{subject}-topic-difficulty.parquet"
        if topics_path.exists():
            topics = pd.read_parquet(topics_path).to_dict("records")
        return templates.TemplateResponse(
            request, "separators.html", {"rows": rows, "topics": topics, "error": None}
        )

    return app


def _weak_topics(
    frames: dict[str, pd.DataFrame],
    year: int,
    exam: int,
    nht: bool,
    per_question: list[dict],
) -> list[dict]:
    topics = frames.get("topics")
    if topics is None:
        return []
    session_topics = topics[(topics["year"] == year) & (topics["exam"] == exam) & (topics["nht"] == nht)]
    topic_by_label: dict[str, str] = {}
    for row in session_topics.itertuples(index=False):
        topic_by_label[str(row.question)] = row.topic

    import re

    def _qnum(label: str) -> str:
        match = re.match(r"^(\d+)", str(label))
        return match.group(1) if match else ""

    agg: dict[str, dict] = defaultdict(lambda: {"lost": 0.0, "max": 0.0, "questions": 0})
    for question in per_question:
        topic = topic_by_label.get(_qnum(question["question"]))
        if topic is None:
            continue
        bucket = agg[topic]
        bucket["questions"] += 1
        bucket["max"] += question["max"]
        bucket["lost"] += question["max"] - question["your_mark"]
    result = [
        {"topic": topic, "lost": bucket["lost"], "max": bucket["max"], "questions": bucket["questions"]}
        for topic, bucket in agg.items()
    ]
    result.sort(key=lambda item: item["lost"], reverse=True)
    return result