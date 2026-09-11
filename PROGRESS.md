# Project Progress

Incrementally build a local Python weekly intelligence tool, using the [MVP specification](docs/mvp-specification.md) to define the scope.

## Phase Status

- [x] Phase 1 — Foundation: entry point, environment configuration, logging, basic evidence models, output directories, and setup instructions.
- [x] Phase 2 — Research: implement direct-source collection for Stats NZ, RBNZ, MBIE, and SEEK, with explicit reporting of unavailable sources.
- [ ] Phase 3 — Structured Evidence (in progress): Stats NZ and bounded SEEK extraction are live-verified; MBIE HTML extraction is tested but live access remains unavailable; RBNZ collection/extraction is explicitly deferred pending publisher permission.
- [ ] Phase 4 — Comparison: load historical data, compare metrics, and identify significant changes.
- [ ] Phase 5 — Job Search Index: define component scoring rules and calculate the index deterministically in Python.
- [ ] Phase 6 — Report Generation: generate Markdown reports from supplied evidence.
- [ ] Phase 7 — Testing and Refinement: complete tests with mocked data and end-to-end acceptance checks.

## 2026-09-11 — Phase 3 MBIE Extraction and RBNZ Access Decision

Access investigation:

- MBIE's official Jobs Online page still returned a 212-character access-challenge shell through the project's robots-aware collector. Official source descriptions identify downloadable CSV/XLSX series, but their actual files and layouts were not retrieved or verified. No values from search results were inserted into research snapshots or accepted facts.
- RBNZ's website and the separate download host linked by its official data-file index both returned HTTP 403 for robots.txt. Its terms require prior written permission for this type of automated access. RBNZ collection and OCR extraction are explicitly deferred; no permission request was sent on the user's behalf.
- Source references and conditions for reopening coverage are recorded in the README's MBIE/RBNZ access section.

Implemented:

- `src/mbie_extraction.py` maps the recognised first national quarterly result to `mbie_job_ads_annual_change`, retaining the percentage unit, annual comparison basis, three-month quarter, national scope, and explicit unadjusted-index context. It does not report a vacancy count or calculate a new comparison.
- Evidence includes exact statement, period, methodology, and visible update-date spans. Validation rejects changed source identity, tampered content, mismatched quarters, unknown wording/units, conflicting totals, and invalid or conflicting dates. Page update dates do not become report publication dates.
- RBNZ's configured target records `kind: deferred` before any network request. Access failures use `kind: unavailable`; older snapshots remain readable. Both types stay in the weekly audit, with separate counts in the logs.
- No API keys, new dependencies, download parsers, or OCR values were added.

Validation: 168 offline tests pass with warnings treated as errors, including mocked MBIE collection through extraction and saving, RBNZ deferral without HTTP requests, source/text validation, and regression coverage for Stats NZ/SEEK.

The full live run exited successfully and saved `data/research/2026-W37/20260911T101729764656+1200.json`, `data/weekly/2026-W37.json`, and an immutable extraction audit. It accepted five facts (four Stats NZ and one SEEK), rejected SEEK's inconsistent job-ad period, skipped the SEEK discovery page, and retained MBIE as unavailable and RBNZ as deferred. Existing research/run archives were preserved; the canonical weekly file was updated with this run's evidence. MBIE produced no live fact.

Status: this increment completes the access investigation and adds a tested MBIE extractor, but does not claim working live MBIE/RBNZ coverage. Phase 3 remains in progress. MBIE requires a permitted usable response for live validation; RBNZ requires permission and inspection of accessible official data before extraction can be implemented. CSV/XLSX, regional/industry data, and qualitative evidence remain outside this increment.

## 2026-09-11 — Phase 3 SEEK Article Evidence

Implemented a second Phase 3 increment, without API keys:

- Added exact text evidence spans with supporting quotations, character offsets, and roles for statements, national scope, report periods, lag notes, and methodology. Stats NZ structured-field references remain supported.
- Added `src/seek_extraction.py` for recognised national job-ad and applications-per-ad percentage-change statements. Month-on-month and year-on-year comparisons remain separate; regional, industry, and AI-specific figures are excluded from national metrics.
- Require an explicit report year in the heading or a consistent national chart caption. Preserve the applications reporting lag, including January/December year boundaries. Publication metadata remains separate; missing dates are not inferred from the URL or retrieval time.
- Withhold a metric when its summary and detailed text disagree about its data period, or when its wording is unsupported. Conflicting values are rejected with supporting text for review.
- Added national scope and adjustment metadata to series identity. Recognised SEEK job-ad methodology can establish trend estimates; applications adjustment is not inferred from that statement.
- Weekly outputs now use schema version 3, with continued reading support for version 2. Research snapshots remain version 2; no collection-format change was needed.

Validation: 131 offline tests pass with warnings treated as errors. Tests cover text and metadata tampering, source identity, lag and year boundaries, missing period context, ambiguous wording, national scope, conflicting values, backwards reading, and combined command output.

Replayed the saved 10 September research snapshot, without new network requests: five facts accepted (four Stats NZ observations and SEEK applications per ad, +1.6% for June 2026), one metric rejected, one discovery document skipped, and two original collection failures retained. SEEK's summary describes its 0.8% job-ad decline as July, while the detailed national section says June. The extractor withholds that metric rather than choosing a month. Exact text spans and archive/weekly JSON round-tripping were verified in a temporary directory; existing weekly files were not replaced by this replay.

Limitations: the rules support a bounded article layout and observed-change wording, not general natural-language understanding. Unrecognised statements need review. Chart images, regional/industry breakdowns, CSV/spreadsheet references, qualitative claims, and newsroom-derived article publication dates are not implemented. MBIE and RBNZ access was not retested in this increment, and neither has an evidence extractor yet. Phase 3 remains in progress.

## 2026-09-10 — Phase 3 Stats NZ Evidence Extraction

Scope: deterministic extraction of the Stats NZ unemployment rate, quarterly percentage-point change, unemployed people count, and annual CPI change. Narrative extraction is deferred; no LLM or search API is needed for this increment.

This is the first completed increment of Phase 3, not completion of evidence extraction across all configured sources. Next is SEEK employment-report extraction, including month-on-month/year-on-year distinctions and the reporting lag for applications per advertisement. MBIE and RBNZ evidence extraction remains dependent on obtaining accessible source material through permitted routes; neither source currently contributes accepted facts.

Implemented:

- Research snapshots now preserve original Stats NZ indicator fields and their array positions, with a separate structured-data checksum. Older snapshots remain readable but require recollection before extraction.
- `src/extraction.py` maps recognised names and descriptions to metrics, parses explicit numbers and units, preserves period text, and normalises period date boundaries.
- Validation checks required fields, numerical types and bounds, data periods, dates, source identity, checksums, and agreement between each candidate and its source fields. Publication, source update, and retrieval dates remain distinct.
- Accepted facts include a saved snapshot reference, content hashes, a JSON pointer, exact supporting fields, and an explanation of extraction confidence. Duplicate observations are collapsed; conflicting values are rejected for review.
- Weekly output separates accepted facts, rejected candidates, unprocessed source documents, and collection failures. Each run has an archived extraction audit; a non-empty result atomically updates `data/weekly/YYYY-WXX.json`. Runs with no accepted facts preserve the existing weekly file and exit nonzero.
- Added synthetic extraction and validation tests and updated command-level tests for the new success criteria.

Live validation on 10 September 2026 collected four source documents and produced four accepted facts, zero rejected candidates, and two skipped SEEK documents. RBNZ and MBIE remained unavailable, with both collection failures preserved in the evidence output. The command exited successfully and saved `data/weekly/2026-W37.json` plus a per-run audit. The older Stats NZ data periods remain explicit; these observations are not labelled as newly released this week.

Validation: 90 offline tests pass. The saved live facts can be traced to their original snapshot, structured blocks, and supporting fields. No comparison, score, or Markdown report is generated yet.

Limitations: accepted facts currently cover the four supported Stats NZ observations only. Narrative sources, historical chart observations, new metrics, and unfamiliar labels require additional extraction rules or a future LLM integration. Checksums detect changes to saved content, not errors made by the original publisher. Confidence describes extraction support rather than statistical certainty.

## 2026-09-10 — Phase 2 Direct-Source Research Complete

Decision: start with directly accessible public sources. Search API and LLM provider selection are deferred; research runs without API keys.

Implemented:

- `src/research.py` collects five configured pages and discovers one employment report from the SEEK NZ newsroom.
- Stats NZ indicator content is read from the JSON embedded in its public pages. Standard HTML parsing covers the remaining sources.
- Collection respects robots rules, crawl delays, response size limits, and per-request timeouts. Access failures are recorded without bypassing restrictions.
- Each run saves a separate snapshot under `data/research/YYYY-WXX/`, preserving source text, URLs, timestamps, explicit date metadata, content hashes, links, and failures. Generated research stays local and is excluded from Git.
- `main.py` orchestrates collection and saving. Partial collection returns success with warnings; no usable documents or an output failure returns a nonzero exit code.
- Added an offline pytest suite using synthetic source data and mocked HTTP responses.

Live validation on 10 September 2026 collected four documents: Stats NZ unemployment, Stats NZ CPI, the SEEK NZ newsroom, and its linked employment report. RBNZ's robots endpoint returned HTTP 403; MBIE's Jobs Online page returned an access-challenge shell without usable content. Both were recorded as unavailable. The saved snapshot has `partial` status and the command exited successfully.

Validation: all 38 offline tests pass on Python 3.14, installed dependencies are consistent, and the live snapshot validates against `ResearchBatch`. No validated weekly evidence or Markdown report was generated prematurely.

Limitations: RBNZ and MBIE content could not be collected on the tested network. Collection status does not establish source freshness or factual accuracy. This phase does not yet extract validated facts, discover individual graduate vacancies, compare historical indicators, call an LLM, calculate scores, or generate a Markdown report. Linked PDFs and spreadsheets are not downloaded.

## 2026-09-10 — English Documentation

Translated the README and progress log into English, including setup instructions, configuration notes, data model descriptions, and phase status. Updated the README's project tree to include the specification and progress log. Application behaviour is unchanged.

## 2026-09-08 — Phase 1 Complete

Implemented:

- `python main.py` initialises local directories and logs the report week and run time.
- Report periods use the `Pacific/Auckland` timezone and Monday-to-Sunday ISO weeks by default.
- Configuration supports `.env` and existing environment variables; API settings may remain empty for now.
- Pydantic models capture evidence sources, data periods, retrieval timestamps, and weekly data.
- An isolated virtual environment and installation and execution instructions are provided.

Validation record: smoke checks passed locally on Python 3.14 for startup, dependency consistency, model validation, JSON round-trip serialisation, ISO week numbering across a year boundary, execution from another working directory, invalid timezone handling, and keeping API keys out of logs. These checks have not yet been added as a persistent automated test suite.

Current limitations: external research and LLM services are not connected. The script does not yet generate actual reports or calculate the Job Search Index.

## Decisions for Upcoming Phases

- Select an LLM service for evidence extraction; add a search service when broader discovery is needed.
- Define how evidence maps to component scores and how missing data should be handled.

## Progress Tracking

Record each verifiable increment in a separate commit with a message describing the specific change. At the end of each phase, update this file with the implementation, validation results, and known limitations.
