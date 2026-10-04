"""Fetch VCAA subject pages and turn their download links into structured records."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin

import httpx
from lxml import html as lxml_html

from .config import REQUEST_TIMEOUT_S, VCAA_BASE

# Link texts we never care about (marking guides, sample material, videos).
_SKIP_PATTERNS = (
    "assessment guide",
    "sample",
    "specifications",
    "transcript",
    "formula sheet",
    "answer sheet",
    "chief assessor",
    "professional learning",
    "timetable",
)

_YEAR_RE = re.compile(r"\b(20\d{2})\b")
_EXAM_RE = re.compile(r"\b(?:examination|exam)\s*(\d)\b", re.IGNORECASE)
_REPORT_EXAM_RE = re.compile(r"\breport\s*(\d)\b", re.IGNORECASE)
_SUBJECT_EXAM_RE = re.compile(
    r"\b(?:mathematical\s+methods|mathematics|maths|methods|specialist|general)\s*(\d)\b",
    re.IGNORECASE,
)
_FILENAME_EXAM_RE = re.compile(r"(?:mm(?:cas)?|math(?:ematics|s)?|methods|sm)[-_]?(\d)", re.IGNORECASE)


@dataclass(frozen=True)
class DocLink:
    text: str
    url: str
    filename: str


@dataclass(frozen=True)
class DocRecord:
    """A past exam or external assessment report worth downloading."""

    subject: str
    year: int
    kind: str  # "paper" | "report"
    exam: int | None
    nht: bool
    url: str
    filename: str


def fetch_doc_links(client: httpx.Client, page_url: str) -> list[DocLink]:
    page = client.get(page_url, timeout=REQUEST_TIMEOUT_S)
    page.raise_for_status()
    tree = lxml_html.fromstring(page.text)
    links: list[DocLink] = []
    seen: set[str] = set()
    for anchor in tree.xpath("//a[@href]"):
        href = anchor.get("href", "")
        if not re.search(
            r"^(?:https?://[^/]+)?/?sites/default/files/.*\.(pdf|docx?)(\?.*)?$",
            href,
            re.IGNORECASE,
        ):
            continue
        url = urljoin(VCAA_BASE + "/", href.lstrip("/"))
        if url in seen:
            continue
        seen.add(url)
        text = " ".join(anchor.itertext()).strip() or href.rsplit("/", 1)[-1]
        links.append(
            DocLink(text=text, url=url, filename=url.split("?")[0].rsplit("/", 1)[-1])
        )
    return links


def _wanted(text: str) -> bool:
    lowered = text.lower()
    return not any(pat in lowered for pat in _SKIP_PATTERNS)


def classify_link(subject: str, link: DocLink) -> DocRecord | None:
    """Map a VCAA download link to a paper/report record, or None if irrelevant."""
    if not _wanted(link.text):
        return None
    year_match = _YEAR_RE.search(link.text)
    if not year_match:
        return None
    lowered = link.text.lower()
    is_report = "report" in lowered
    is_paper = ("examination" in lowered or "exam" in lowered) and not is_report
    if not (is_report or is_paper):
        return None
    exam_match = (
        _EXAM_RE.search(link.text)
        or _REPORT_EXAM_RE.search(link.text)
        or _SUBJECT_EXAM_RE.search(link.text)
        or _FILENAME_EXAM_RE.search(link.filename)
    )
    return DocRecord(
        subject=subject,
        year=int(year_match.group(1)),
        kind="report" if is_report else "paper",
        exam=int(exam_match.group(1)) if exam_match else None,
        nht="nht" in lowered,
        url=link.url,
        filename=link.filename,
    )


def collect_records(
    client: httpx.Client, subject: str, page_url: str
) -> list[DocRecord]:
    records: list[DocRecord] = []
    for link in fetch_doc_links(client, page_url):
        rec = classify_link(subject, link)
        if rec is not None:
            records.append(rec)
    return records
