# Project Progress

Incrementally build a local Python weekly intelligence tool, using the [MVP specification](docs/mvp-specification.md) to define the scope.

## Phase Status

- [x] Phase 1 — Foundation: entry point, environment configuration, logging, basic evidence models, output directories, and setup instructions.
- [x] Phase 2 — Research: implement direct-source collection for Stats NZ, RBNZ, MBIE, and SEEK, with explicit reporting of unavailable sources.
- [x] Phase 3 — Structured Evidence (supported MVP scope): Stats NZ and bounded SEEK extraction are live-verified; MBIE HTML extraction is fixture-tested. MBIE live validation and RBNZ permission/extraction remain explicit coverage follow-ups, not completed live integrations.
- [x] Phase 4 — Comparison: select previous available weekly evidence, classify observations/revisions/missing coverage, calculate comparable differences, and flag changes with explicit review thresholds.
- [ ] Phase 5 — Job Search Index (engine implemented; full live index pending): strict six-component calculation, provisional supported mappings, freshness/coverage rules, scoring history, and persistence are implemented. Suitable evidence/mappings for all six live components remain outstanding.
- [ ] Phase 6 — Report Generation (pipeline implemented; live LLM validation pending): Markdown reports and optional OpenAI interpretation with template fallback are implemented and tested offline. A live report was generated; a credential-backed OpenAI call remains pending.
- [ ] Phase 7 — Testing and Refinement: complete tests with mocked data and end-to-end acceptance checks.

## 2026-09-13 — Phase 6 Reports and OpenAI Integration

Decision: proceed with report generation while the full live six-component index remains unavailable. The user requested LLM API configuration now. OpenAI was used as the stated default while provider preference was pending; no key was supplied in the session.

Implemented:

- Added `src/reporting.py` and connected the report stage after scoring in `main.py`. Reports include the specification's sections, accepted numbers and source links, explicit observation/date metadata, historical comparison semantics, provisional components, coverage gaps, and general job-search suggestions.
- Validate that saved stage inputs refer to the same immutable evidence run and exact accepted facts. Historical input hashes must still match. Reports include input and scoring-policy checksums for audit.
- Added `src/narration.py` using OpenAI's Responses API and strict JSON-schema output through HTTPX. The model receives a compact evidence summary and returns short interpretation notes with existing fact IDs. Python retains control of all numerical sections and citations.
- LLM output is labelled as interpretation requiring review. Schema/reference checks, numeric/link/markup restrictions, input/response limits, refusals, incomplete results, API errors and timeouts lead to a visibly labelled template fallback. These checks do not prove semantic entailment or remove all hallucination risk.
- Added explicit provider/model/timeout configuration, setup instructions and an ignored local `.env` with a blank key. The initial model is the documented `gpt-4.1-mini-2025-04-14` snapshot. One request per run, no retries/tools/redirects, bounded output tokens, and `store=false`; no raw articles or local evidence paths are sent.
- Save an immutable Markdown report and narration audit before atomically replacing `reports/YYYY-WXX.md`. Report failures preserve previous reports and earlier pipeline stages; unavailable narration alone still produces a successful template report.

Validation: 305 offline tests pass with warnings treated as errors. Added report structure, dates/units/citations, missing and synthetic complete indices, history/revision semantics, input tampering, output persistence/failures, API request contracts, safe error diagnostics, references, malformed/refused output, response limits, and configuration checks. `git diff --check` passes.

The live end-to-end run exited `0`, producing `reports/2026-W37.md` and the report/audit archive for `20260913T032721710436+1200`. It accepted five facts, rejected the inconsistent SEEK job-ad period, retained MBIE as unavailable and RBNZ as deferred, and scored competition/economy with 35% component-weight coverage and no overall index. Research: `data/research/2026-W37/20260913T032655356578+1200.json`. Evidence: `data/weekly/runs/2026-W37/20260913T032721710436+1200.json`.

The live report used the template fallback because `LLM_API_KEY` is missing. No paid OpenAI request was made. Live API compatibility/account access and interpretation quality remain unverified until the user adds a key locally. Phase 6 is therefore not marked fully complete. Phase 7 will refine end-to-end acceptance and prose quality; broader evidence coverage and the full six-component index remain separate follow-ups. Changes were left unstaged and uncommitted for the user.

## 2026-09-12 — Phase 5 Provisional Scoring Engine

Scope: implement the scoring engine with honest incomplete results, rather than claim a live six-component index. The supported mappings are deliberately provisional and documented in `docs/scoring-policy.md`.

Implemented:

- Added `src/scoring.py` with fixed specification weights, strict numeric/range validation, decimal weighted calculation, explicit HALF_UP rounding, component models, and aggregate consistency checks.
- Added separate job-availability mappings for eligible SEEK monthly trend growth and fallback MBIE annual unadjusted growth. Added a national applications-growth proxy for competition and an unemployment-only economic proxy. These are judgments, not objectively calibrated measures of graduate prospects.
- Source/unit/basis/adjustment/method and period shape must match. Freshness uses the evidence period end, not retrieval or page-update recency. Conflicting latest observations are not replaced by convenient older values. Selected evidence, rules, ages, issues, and limitations are preserved.
- Graduate availability, IT demand, and automation pressure remain unavailable. An overall index requires all six components; missing data is never zero, neutral, backfilled, or reweighted. Coverage percentage is explicitly not confidence.
- Added scoring history with input hashes, policy version/checksum, and method compatibility checks. Incomplete indices, changed methods, same-period revisions, and older/incompatible evidence do not produce a misleading numerical trend.
- Connected scoring to `main.py`, with atomic weekly views and immutable run archives under `data/weekly/scores/`. Honest incomplete results are saved successfully; write failures return nonzero while preserving evidence and comparison.

Validation: 256 offline tests pass with warnings treated as errors. Added coverage for weights, bounds, rounding, missing values, mapping anchors, source/basis mismatch, freshness boundaries, conflicting evidence, fallback sources, incomplete history, method switches, revisions, persistence, and command-level scoring failure. Complete six-component fixtures are explicitly synthetic.

The full live run exited successfully and saved `data/weekly/scores/2026-W37.json` and its immutable audit. Five source facts yielded two provisional component scores: competition 4.2 and the unemployment-based economy proxy 6.75, covering 35% of specified component weight. The overall index is `null` with `insufficient_evidence`. Job availability remains unscored because the SEEK observation is rejected and MBIE unavailable; the other three missing components have no suitable implemented evidence mapping. No historical score is available for comparison.

Research snapshot: `data/research/2026-W37/20260912T193446913700+1200.json`. Evidence archive: `data/weekly/runs/2026-W37/20260912T193511153226+1200.json`. Earlier archives are preserved.

Status: the bounded Phase 5 engine is implemented and verified. The full live index remains outstanding, so Phase 5 is not marked fully complete. Phase 6 can generate reports from existing evidence and explicitly state these gaps. Publishing the original complete six-component index still requires additional evidence and evaluated rules.

## 2026-09-12 — Phase 4 Historical Comparison

Phase 3 is closed for the supported MVP scope, following the decision to proceed with documented unavailable/deferred sources. This does not resolve MBIE live access or implement RBNZ OCR extraction; those remain coverage follow-ups.

Implemented:

- `src/analysis.py` loads the most recent valid, non-empty earlier weekly file. Current-week reruns and future files are excluded; malformed files are skipped with audit notes, and missing weeks are represented by the actual week gap.
- Matching includes publisher, metric/category, unit, comparison basis, geography, scope, and adjustment. Each file contributes its latest observation for each series. Conflicting latest observations and incompatible periods produce no arithmetic.
- Comparison distinguishes baselines, newly covered/missing series, repeated observations, same-period revisions, later periods, older observations, and incompatible evidence. Missing values never become zero; repeated data never establishes a stable market.
- Differences in percentage rates use percentage points, while people-count differences use people. New-period review flags use explicit, editable thresholds; they are not claims of statistical significance. Revisions retain their differences separately.
- A limited national labour-direction interpretation requires new-period evidence across at least two supported themes. It is not a graduate hiring assessment or the Job Search Index.
- `main.py` saves a comparison after evidence extraction. Each comparison references the immutable current evidence archive and selected earlier file with hashes, original facts, and fact pointers. Outputs have a per-run archive and atomic weekly view under `data/weekly/comparisons/`.
- No history is a successful baseline run. Comparison failure returns nonzero while preserving saved evidence and any previous comparison view. No API, dependency, score, or report generation was added.

Validation: 208 offline tests pass with warnings treated as errors. Added cases for increases/decreases/unchanged values, percentage-point versus count units, revisions, missing series, incompatible metadata, rolling periods, variable month lengths, historical gaps/corruption, ISO-year boundaries, conflicting observations, review thresholds, direction interpretation, and output failures.

The live run on 12 September exited successfully and saved five accepted facts plus `data/weekly/comparisons/2026-W37.json` and its immutable run archive. There is no earlier weekly file in this workspace, so all five comparisons correctly have `baseline` status and labour direction is `insufficient_data`. Cross-week movements were verified using synthetic historical fixtures, not invented live history. Research is archived at `data/research/2026-W37/20260912T174125821475+1200.json`.

Remaining limits: MBIE is still unavailable and RBNZ deferred. SEEK's inconsistent job-ad period remains rejected. Thresholds require future calibration; multi-year extremes, policy/news interpretation, and complete revised historical series are outside this bounded comparison increment. Phase 5 scoring is next.

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

- OpenAI report interpretation is implemented; validate it with a local API key. LLM evidence extraction and broader search discovery remain deferred.
- Expand evidence coverage and evaluate provisional scoring mappings before publishing the full six-component index.

## Progress Tracking

Record each verifiable increment in a separate commit with a message describing the specific change. At the end of each phase, update this file with the implementation, validation results, and known limitations.
