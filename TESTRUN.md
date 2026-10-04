# TEST RUN PLAN - QUESTION BANK SLICE

Date: 2026-10-05. Status: planned, awaiting API key and start confirmation.
Companion files: `PLAN.md` (build plan), `REPORT.md` (cost and time report).
Return-to-it checklist at the bottom.

## 1. Purpose

Validate the two riskiest stages of the question bank on one modern paper and
one legacy paper before committing to the full build: crop boundary detection
across eras, and OCR quality on old Specialist typesetting. Both topic
classification candidates run on every question so their outputs can be
compared from day one.

Test sessions (Specialist Mathematics exam 1, non-NHT, raw files verified):

| Session | Pages | Questions | Heading format |
|---|---|---|---|
| 2018 exam 1 | 14 | 10 | `Question 1 (4 marks)` - modern, marks in heading |
| 2011 exam 1 | 13 | 11 | `Question 1` - legacy, marks only in body text |

The 2011 paper stresses both risky stages: legacy layout for cropping and
older fonts with denser set notation for OCR. The 2018 paper is the control.

## 2. Scope decisions (confirmed)

- Both candidates on every question from these two exams, no subsampling:
  - Candidate B: Gemini Flash-Lite, topics array in the same OCR call.
  - Candidate C: Simple Jev on the OCR plain text, full per-topic
    probability dump for threshold sweep preview.
- Jev endpoint: free hosted demo API
  (`https://simple-jev-demo-api.featherless.ai/v1/`, no key, model
  `featherless-ai/gemma-4-26B-A4B-classifier`, limits 2 requests/second and
  2k-token context per branch). Verified reachable, HTTP 200. Local CPU
  server is the fallback and is not needed for the test run.
- Topic vocabulary: Specialist column of `Topics.csv` (8 topics: Proofs and
  Logic; Counting; Probability and Statistics; Trigonometry; Linear Algebra;
  Algebra over C; Functions, relations and graphs; Calculus). Multi-label.
- Classification granularity: whole question only, never per part.

## 3. Steps

1. **Crop.** PyMuPDF crop module with two era rule sets (2018 style, 2011
   style). One PNG per page segment for multi-page questions, ordered list
   per question. Output: `data/processed/specialist-question-images/` plus an
   index parquet with sha256 and crop rectangles (cache key).
2. **OCR (candidate B).** Flash-Lite REST via httpx, one image per request,
   temperature 0, structured JSON response: `latex`, `plain`, `topics[]` with
   confidences. Cache parquet keyed by file sha256 plus crop rectangle.
3. **Classify (candidate C).** Jev demo API on each question's `plain` text,
   8-topic choice, response includes per-topic probabilities. Probability
   dump stored for threshold sweep preview (0.15, 0.20, 0.25, 0.30, 0.40).
4. **Review artifact.** Throwaway static HTML:
   crop image | KaTeX render of OCR latex | plain text | B labels vs C
   probability table, one block per question. Opened in the browser for
   manual spot-checking.
5. **Measured test report.** Console summary plus this file updated with
   actuals: bounded crops vs fallback count per era, seconds per crop,
   seconds per OCR question, USD actual versus estimate, era-specific rule
   differences found, spot-check verdicts.

## 4. Acceptance criteria

- 2018: 10 of 10 questions cleanly bounded.
- 2011: at least 8 of 11 cleanly bounded, every fallback documented with the
  rule that would have fixed it.
- OCR total cost at most USD 0.02 (approximately 21 to 30 images across the
  two sessions including page segments).
- Owner spot-check: LaTeX quality confirmed on a sample of questions from
  both eras, side by side with the crop.

## 5. Effort, cost, prerequisites

- Effort: 0.5 to 1 day (2011 crop rules dominate). Orchestration is solo in
  the main thread (small surface; fan-out earns its keep only at the full
  build), with `cavecrew-reviewer` auditing the diff afterward.
- Cost: under USD 0.02 total.
- Prerequisites:
  1. Gemini API key: NOT yet set (checked 2026-10-05; no `GEMINI_API_KEY` in
     environment). Owner exports it or places it in `.env`; `.env` must be
     added to `.gitignore` first (verified absent).
  2. pymupdf dependency added to the project.
  3. Jev demo API: nothing needed (keyless, verified reachable).

## 6. Carry-forward versus throwaway

- Carries into the full build: crop module and era rules, OCR client with
  cache, index parquet conventions, C classification wiring.
- Deleted after acceptance: review HTML generator, test-run report
  scaffolding, any hardcoded session-specific tweaks that do not generalize.

## 7. Link to the full build

This test run is the pilot for build phases 1 to 3 in `PLAN.md`. Its outputs
feed the classification bake-off: B labels and C probabilities on real
Specialist questions preview the fixture-based comparison; the formal bake-off
still runs on the labeled fixture set with threshold sweep and a manual
disagreement review.

## 8. Return-to-it checklist

1. Owner: set `GEMINI_API_KEY` (shell export or `.env`; I add `.env` to
   `.gitignore` first).
2. Say "go" - no re-planning needed; this file is the brief.
3. Steps 1 to 5 run in order with the acceptance gates in section 4.
4. Actuals recorded in section 5 and this file marked "done" with date.