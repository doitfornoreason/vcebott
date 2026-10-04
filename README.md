# vcebott

# ! Work in progress

VCE maths analytics built from VCAA examination statistics: question difficulty
("separators"), state-wide quantiles for your marks, per-question topic
classification, and a local dashboard for students.

## Plan

- **Scrape** — downloads every published exam paper and external assessment
  report for a subject (VCAA 2006-2026, NHT sessions included) into `data/raw/`,
  with a `manifest.json` listing every file and its hash.
- **Parse** — extracts per-question mark distributions ("% of the state
  achieving each mark") from reports (PDF up to 2019, DOCX 2020+) into tidy
  parquet tables.
- **Analyze** — ranks separator questions per exam session (gap between the
  mean mark of the top 25% of the state and the overall mean) and cross-checks
  computed averages against VCAA's published ones.
- **Classify** — labels every question with a topic using a local
  [Simple Jev](https://github.com/featherless-ai/simple-jev) classifier
  (Qwen 0.8B, CPU, no API key).
- **Serve** — a dashboard where students enter their marks per question and get
  per-question percentiles vs the state, an exam-level percentile estimate, a
  weak-topic breakdown, and a what-if simulator (edit any mark and resubmit).

## Quickstart

```bash
uv sync
uv run vcebott scrape methods     # ~116 documents, rate-limited
uv run vcebott parse methods      # mark distributions -> parquet
uv run vcebott analyze methods    # separator rankings
uv run vcebott serve              # http://127.0.0.1:8000
```

Topic labels (optional but used by the dashboard):

```bash
# one-time: run a local Simple Jev server (see below)
uv run vcebott classify methods            # label all questions
uv run vcebott classify methods --evaluate # accuracy vs tests/fixtures/topic-sample.jsonl
```

Simple Jev server (keyless, local, CPU):

```bash
git clone https://github.com/featherless-ai/simple-jev /tmp/simple-jev
uv venv /tmp/jev-venv --python 3.13
uv pip install --python /tmp/jev-venv/bin/python -e /tmp/simple-jev/hf-server
/tmp/jev-venv/bin/python /tmp/simple-jev/hf-server/hf_server.py \
  --model Qwen/Qwen3.5-0.8B --device cpu --dtype float32 \
  --classifier-prompt-policy baseline --max-model-len 4096 \
  --max-batch-size 4 --max-batch-tokens 4096 --port 8777
```

Override the endpoint with a `JevConfig` if you host it elsewhere.

## Data notes (read before trusting the numbers)

- **NHT reports contain no statistics.** VCAA publishes sample answers only for
  Northern Hemisphere Timetable sessions; those reports parse to zero rows and
  are logged explicitly by `parse`.
- **Exam-level percentiles assume independence** across questions. Per-question
  percentiles are exact for the published distribution; the exam total is a
  convolution estimate and is labelled as approximate in the UI.
- **VCAA's printed "Average" column sometimes disagrees with its own mark
  distribution** (systematically in 2017 exam 1 and 2012 exam 1 Q9b; mildly for
  2006-2008). The distributions are authoritative here; `analyze` reports every
  mismatch it finds.
- Data is scraped from public VCAA pages, rate-limited, cached on disk.

## Container

```bash
docker build -t vcebott .
docker run -p 8000:8000 -v "$(pwd)/data:/app/data" vcebott
```

The image needs the parsed parquet files, so mount your `data/` directory.

## Layout

```
data/raw/<subject>/<year>-exam<N>[-nht]/  papers and reports
data/manifest.json                        scrape manifest (url, sha256, size)
data/processed/                           parquet: marks, separators, topics...
src/vcebott/                              package
tests/                                    unit tests + labeled topic sample
```

## Subjects

`methods` is fully verified. `specialist` and `general` run through the same
pipeline (best-effort smoke-tested; report layouts may vary).
