"""Central configuration: VCAA endpoints and data layout."""

from __future__ import annotations

import os
from pathlib import Path

VCAA_BASE = "https://www.vcaa.vic.edu.au"

_REPORTS_ROOT = "/assessment/vce/examination-specifications-past-examinations-and-examination-reports"

SUBJECT_PAGES: dict[str, str] = {
    "methods": f"{VCAA_BASE}{_REPORTS_ROOT}/mathematical-methods",
    "specialist": f"{VCAA_BASE}{_REPORTS_ROOT}/specialist-mathematics",
    "general": f"{VCAA_BASE}{_REPORTS_ROOT}/general-mathematics",
}

# Politeness limits for VCAA downloads.
REQUEST_TIMEOUT_S = 60.0
REQUEST_RETRIES = 3
MIN_DELAY_S = 0.5


def data_root() -> Path:
    """Directory holding raw downloads, processed tables and the manifest."""
    env = os.environ.get("VCEBOTT_DATA")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2] / "data"


def raw_dir(subject: str) -> Path:
    return data_root() / "raw" / subject


def processed_dir() -> Path:
    return data_root() / "processed"


def manifest_path() -> Path:
    return data_root() / "manifest.json"
