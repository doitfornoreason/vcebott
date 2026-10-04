"""Polite scraper for VCAA exam papers and external assessment reports."""

from __future__ import annotations

import hashlib
import json
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import httpx

from .config import (
    MIN_DELAY_S,
    REQUEST_RETRIES,
    REQUEST_TIMEOUT_S,
    SUBJECT_PAGES,
    manifest_path,
    raw_dir,
)
from .vcaa import DocRecord, collect_records


def entry_dir(subject: str, year: int, exam: int | None, nht: bool) -> Path:
    parts = [str(year)]
    if exam is not None:
        parts.append(f"exam{exam}")
    if nht:
        parts.append("nht")
    return raw_dir(subject) / "-".join(parts)


def download_all(subject: str, *, force: bool = False) -> list[dict]:
    """Download every paper/report listed on the subject page. Returns manifest entries."""
    entries: list[dict] = []
    with httpx.Client(follow_redirects=True) as client:
        records = collect_records(client, subject, SUBJECT_PAGES[subject])
        records.sort(key=lambda r: (r.year, r.nht, r.exam or 0, r.kind))
        for rec in records:
            dest = entry_dir(rec.subject, rec.year, rec.exam, rec.nht)
            suffix = Path(rec.filename).suffix.lower()
            dest_path = dest / f"{rec.kind}{suffix}"
            entry = _entry_from_record(rec, dest_path, status="cached")
            if force or not dest_path.exists():
                dest.mkdir(parents=True, exist_ok=True)
                _download(client, rec, dest_path)
                entry["status"] = "downloaded"
            entry["sha256"] = _sha256(dest_path)
            entry["bytes"] = dest_path.stat().st_size
            entries.append(entry)
            time.sleep(MIN_DELAY_S)
    return entries


def _entry_from_record(rec: DocRecord, dest_path: Path, status: str) -> dict:
    return {
        "subject": rec.subject,
        "year": rec.year,
        "kind": rec.kind,
        "exam": rec.exam,
        "nht": rec.nht,
        "url": rec.url,
        "path": str(dest_path),
        "status": status,
    }


def _download(client: httpx.Client, rec: DocRecord, dest: Path) -> None:
    last_error: Exception | None = None
    for attempt in range(1, REQUEST_RETRIES + 1):
        try:
            resp = client.get(rec.url, timeout=REQUEST_TIMEOUT_S)
            resp.raise_for_status()
            dest.write_bytes(resp.content)
            return
        except httpx.HTTPError as exc:
            last_error = exc
            time.sleep(min(2**attempt, 8))
    raise RuntimeError(
        f"failed to download {rec.url} after {REQUEST_RETRIES} attempts: {last_error}"
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_manifest(subject: str, entries: list[dict]) -> None:
    manifest_path().parent.mkdir(parents=True, exist_ok=True)
    manifest = _load_manifest()
    manifest[subject] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "entries": entries,
    }
    manifest_path().write_text(json.dumps(manifest, indent=2))


def _load_manifest() -> dict:
    if manifest_path().exists():
        return json.loads(manifest_path().read_text())
    return {}


def coverage(subject: str) -> dict:
    """Summarise which years/exams have paper+report, flagging gaps."""
    manifest = _load_manifest()
    entries = manifest.get(subject, {}).get("entries", [])
    have: dict[tuple[int, int | None, bool], set[str]] = defaultdict(set)
    for entry in entries:
        key = (entry["year"], entry["exam"], entry["nht"])
        have[key].add(entry["kind"])
    gaps = [
        {
            "year": year,
            "exam": exam,
            "nht": nht,
            "missing": sorted({"paper", "report"} - kinds),
        }
        for (year, exam, nht), kinds in sorted(
            have.items(), key=lambda kv: (kv[0][0], kv[0][1] if kv[0][1] is not None else -1, kv[0][2])
        )
        if kinds != {"paper", "report"}
    ]
    return {
        "documents": len(entries),
        "sessions": len(have),
        "complete": len(gaps) == 0,
        "gaps": gaps,
    }


def verify(subject: str) -> bool:
    summary = coverage(subject)
    if not summary["sessions"]:
        print(
            f"{subject}: no scraped data found (run `vcebott scrape {subject}` first)"
        )
        return False
    print(
        f"{subject}: {summary['documents']} documents across {summary['sessions']} sessions"
    )
    for gap in summary["gaps"]:
        label = f"{gap['year']} exam{gap['exam']}" + (" NHT" if gap["nht"] else "")
        print(f"  GAP {label}: missing {', '.join(gap['missing'])}")
    print(f"{subject}: {'OK' if summary['complete'] else 'GAPS FOUND'}")
    return summary["complete"]
