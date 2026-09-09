# Project Progress

Incrementally build a local Python weekly intelligence tool, using the [MVP specification](docs/mvp-specification.md) to define the scope.

## Phase Status

- [x] Phase 1 — Foundation: entry point, environment configuration, logging, basic evidence models, output directories, and setup instructions.
- [ ] Phase 2 — Research: select services and integrate Stats NZ, RBNZ, and one labour market source.
- [ ] Phase 3 — Structured Evidence: extract facts, validate evidence, and save structured JSON.
- [ ] Phase 4 — Comparison: load historical data, compare metrics, and identify significant changes.
- [ ] Phase 5 — Job Search Index: define component scoring rules and calculate the index deterministically in Python.
- [ ] Phase 6 — Report Generation: generate Markdown reports from supplied evidence.
- [ ] Phase 7 — Testing and Refinement: complete tests with mocked data and end-to-end acceptance checks.

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

- Select search and LLM services.
- Define how evidence maps to component scores and how missing data should be handled.

## Progress Tracking

Record each verifiable increment in a separate commit with a message describing the specific change. At the end of each phase, update this file with the implementation, validation results, and known limitations.
