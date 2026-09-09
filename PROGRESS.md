# Project Progress

Incrementally build a local Python weekly intelligence tool, using the [MVP specification](docs/mvp-specification.md) to define the scope.

## Phase Status

- [x] Phase 1 — Foundation: entry point, environment configuration, logging, basic evidence models, output directories, and setup instructions.
- [x] Phase 2 — Research: implement direct-source collection for Stats NZ, RBNZ, MBIE, and SEEK, with explicit reporting of unavailable sources.
- [ ] Phase 3 — Structured Evidence: extract facts, validate evidence, and save structured JSON.
- [ ] Phase 4 — Comparison: load historical data, compare metrics, and identify significant changes.
- [ ] Phase 5 — Job Search Index: define component scoring rules and calculate the index deterministically in Python.
- [ ] Phase 6 — Report Generation: generate Markdown reports from supplied evidence.
- [ ] Phase 7 — Testing and Refinement: complete tests with mocked data and end-to-end acceptance checks.

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
