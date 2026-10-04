"""vcebott command line interface."""

from __future__ import annotations

import typer

from .config import SUBJECT_PAGES
from .scrape import coverage, download_all, verify, write_manifest
from .vcaa import collect_records

app = typer.Typer(
    help="VCE maths analytics: exam statistics, separators, quantiles, topic classifier.",
    no_args_is_help=True,
)


@app.command()
def scrape(
    subject: str = typer.Argument(
        default="methods", help="Subject key (methods/specialist/general)."
    ),
    force: bool = typer.Option(
        False, "--force", help="Re-download even if files exist."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="List discovered documents without downloading."
    ),
    verify: bool = typer.Option(
        False, "--verify", help="Check manifest coverage instead of downloading."
    ),
) -> None:
    """Download exam papers and external assessment reports from VCAA."""
    if subject not in SUBJECT_PAGES:
        typer.echo(f"unknown subject '{subject}'; known: {', '.join(SUBJECT_PAGES)}")
        raise typer.Exit(2)
    if verify:
        raise typer.Exit(0 if verify_coverage(subject) else 1)
    if dry_run:
        import httpx

        with httpx.Client(follow_redirects=True) as client:
            records = collect_records(client, subject, SUBJECT_PAGES[subject])
        for rec in sorted(records, key=lambda r: (r.year, r.nht, r.exam or 0, r.kind)):
            label = f"{rec.year} exam{rec.exam}" + (" NHT" if rec.nht else "")
            typer.echo(f"{label:16} {rec.kind:6} {rec.filename}")
        typer.echo(f"{len(records)} documents")
        return
    entries = download_all(subject, force=force)
    write_manifest(subject, entries)
    summary = coverage(subject)
    typer.echo(
        f"{subject}: {summary['documents']} documents, {summary['sessions']} sessions, "
        f"{len(summary['gaps'])} gaps"
    )
    for gap in summary["gaps"]:
        label = f"{gap['year']} exam{gap['exam']}" + (" NHT" if gap["nht"] else "")
        typer.echo(f"  GAP {label}: missing {', '.join(gap['missing'])}")


def verify_coverage(subject: str) -> bool:
    return verify(subject)


@app.command()
def parse(
    subject: str = typer.Argument(default="methods"),
) -> None:
    """Parse scraped reports into tidy mark-distribution parquet tables."""
    from .parse import parse_subject_reports

    frame = parse_subject_reports(subject)
    if frame.empty:
        typer.echo("nothing parsed; run scrape first")
        raise typer.Exit(1)
    out = _write_processed(subject, frame)
    typer.echo(f"{subject}: {len(frame)} mark rows -> {out}")


def _write_processed(subject: str, frame) -> object:
    from .config import processed_dir

    processed_dir().mkdir(parents=True, exist_ok=True)
    out = processed_dir() / f"{subject}-marks.parquet"
    frame.to_parquet(out, index=False)
    return out


@app.command()
def analyze(
    subject: str = typer.Argument(default="methods"),
) -> None:
    """Rank separator questions and emit quantile tables."""
    from .analysis import run_analysis

    run_analysis(subject)


@app.command()
def classify(
    subject: str = typer.Argument(default="methods"),
    evaluate: bool = typer.Option(
        False, "--evaluate", help="Score against the labeled sample."
    ),
) -> None:
    """Label exam questions with topics using a local Simple Jev classifier."""
    from .classify import run_classify

    run_classify(subject, evaluate=evaluate)


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8000, "--port"),
) -> None:
    """Serve the student dashboard."""
    import uvicorn

    from .serve import create_app

    uvicorn.run(create_app(), host=host, port=port)


if __name__ == "__main__":
    app()
