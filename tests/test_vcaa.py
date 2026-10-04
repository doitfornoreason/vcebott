import pytest

from vcebott.vcaa import DocLink, classify_link

CASES = [
    (
        "2025 VCE Mathematical Methods examination 1",
        "2025-MathMethods1.pdf",
        {"year": 2025, "kind": "paper", "exam": 1, "nht": False},
    ),
    (
        "2025 VCE Mathematical Methods 1 external assessment report",
        "2025-MathematicalMethods1-report.docx",
        {"year": 2025, "kind": "report", "exam": 1, "nht": False},
    ),
    (
        "2023 VCE (NHT) Mathematical Methods exam report 1",
        "2023mathmethods1-NHT-report.docx",
        {"year": 2023, "kind": "report", "exam": 1, "nht": True},
    ),
    (
        "2018 VCE (NHT) Mathematical Methods exam report2",
        "mathsmethods2nht_examrep18.pdf",
        {"year": 2018, "kind": "report", "exam": 2, "nht": True},
    ),
    (
        "2019 VCE (NHT) Mathematical Methods exam report 1",
        "mm1nht_examrep19.pdf",
        {"year": 2019, "kind": "report", "exam": 1, "nht": True},
    ),
    (
        "2023 Mathematical Methods exam 2 report",
        "2023mathmethods2-report.docx",
        {"year": 2023, "kind": "report", "exam": 2, "nht": False},
    ),
    (
        "2023 VCE Mathematical Methods examination 2",
        "2023MM2-w.pdf",
        {"year": 2023, "kind": "paper", "exam": 2, "nht": False},
    ),
]


@pytest.mark.parametrize("text,filename,expected", CASES)
def test_classify_link(text, filename, expected):
    record = classify_link("methods", DocLink(text=text, url="https://x/" + filename, filename=filename))
    assert record is not None
    for field, value in expected.items():
        assert getattr(record, field) == value, field


def test_skips_assessment_guides_and_samples():
    for text in (
        "2024 VCE Mathematical Methods exam 1 assessment guide",
        "Sample questions for written examination 1",
        "Mathematics Methods Examination 1 transcript",
        "Examination specifications",
        "Sample multiple-choice answer sheet",
    ):
        assert classify_link("methods", DocLink(text=text, url="https://x/a.docx", filename="a.docx")) is None


def test_skips_links_without_year():
    assert classify_link("methods", DocLink(text="Formula sheet", url="https://x/f.pdf", filename="f.pdf")) is None