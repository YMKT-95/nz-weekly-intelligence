# NZ IT Graduate Weekly Intelligence

A personal, local Python tool for IT graduates seeking employment in New Zealand. The goal is to research relevant information each week, compare changes over time, and generate a Markdown report supported by traceable evidence.

**Phase 3 is in progress:** structured Stats NZ indicators and supported national statements from SEEK employment reports can now be extracted into validated weekly JSON. Accepted facts retain their original fields or exact article passages, including period and scope context. Rejected candidates and unprocessed sources are recorded separately. It runs without API keys. Broader article extraction, MBIE/RBNZ evidence support, LLM integration, historical comparison, scoring, and Markdown report generation remain outstanding.

See the [MVP specification](docs/mvp-specification.md) for the project scope and [project progress](PROGRESS.md) for phase status and validation records.

## Requirements and Setup

Python 3.12 or later is required. Run the following commands from the project directory on macOS or Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Activating the virtual environment uses its Python interpreter and dependencies without modifying the global Python environment. `tzdata` provides timezone data on systems without a timezone database.

## Configuration

Direct-source research runs without a `.env` file or API keys. To customise local settings, copy the template during initial setup:

```bash
cp .env.example .env
```

- `REPORT_TIMEZONE`: defaults to `Pacific/Auckland`.
- `RESEARCH_TIMEOUT_SECONDS`: HTTP connect/read/write/pool timeout; defaults to `20`, with an allowed range greater than `0` and at most `120`. This is not a deadline for the entire run.
- `LLM_API_KEY`, `LLM_MODEL`, and `SEARCH_API_KEY`: reserved for future service integrations and may remain empty for now.

Existing environment variables take precedence over `.env`. The configuration file is always loaded from the project root, regardless of the working directory. Do not commit real credentials; `.env` is excluded by `.gitignore`, and API keys are not written to logs.

## Running the Script

```bash
source .venv/bin/activate
python main.py
```

The logs show the ISO report week, its Monday-to-Sunday date range, the actual run time with its timezone, and the output directories. During a midweek run, Sunday marks the end of the report week; it does not imply that information from future dates has been collected.

A run that extracts at least one accepted fact and saves the evidence exits with code `0`, even when other sources fail. Partial research coverage, rejected candidates, and unprocessed sources are recorded in the output. Invalid configuration, an output error, or no accepted facts results in exit code `1`. Even if no facts are accepted, the script saves the research and extraction audit when the output directory is writable, preserving any existing weekly evidence file.

The final log line after saving accepted facts is:

```text
[INFO] Evidence extraction complete. Comparison, scoring, and reports are not yet connected.
```

Each run saves a separate JSON file under `data/research/YYYY-WXX/`, named with its start timestamp, including microseconds and UTC offset. Repeated runs preserve earlier snapshots, including when a later run fails. Generated research files are excluded from Git.

Research snapshots remain collected source material. Accepted facts and the validation audit are saved separately:

- `data/weekly/YYYY-WXX.json`: the most recent run with at least one accepted fact for that week.
- `data/weekly/runs/YYYY-WXX/<timestamp>.json`: a preserved audit for each extraction run, including runs that accepted no facts.

The weekly file is replaced atomically only after its new content is written successfully. A later partial run with accepted facts replaces it with that run's evidence; facts from different runs are not silently combined. Earlier results remain in the run archive. A run with no accepted facts leaves the weekly file unchanged, so always check the command's exit code and output timestamps. No Markdown report is generated yet. All generated files are excluded from Git.

## Direct Sources

The source list is defined in `src/research.py`:

- [Stats NZ unemployment indicator](https://www.stats.govt.nz/indicators/unemployment-rate/).
- [Stats NZ CPI indicator](https://www.stats.govt.nz/indicators/consumers-price-index-cpi/).
- [RBNZ monetary policy decisions](https://www.rbnz.govt.nz/monetary-policy/monetary-policy-decisions).
- [MBIE Jobs Online](https://www.mbie.govt.nz/business-and-employment/employment-and-skills/labour-market-reports-data-and-analysis/jobs-online).
- [SEEK NZ newsroom](https://nz.seek.com/about/news), plus the first employment report linked on that page. The URL is discovered on each run rather than hard-coded to a particular month. Its position does not establish that it was published during the report week.

HTTPX retrieves the pages, and BeautifulSoup extracts readable content. Stats NZ indicator pages embed their content in a `pageViewData` JSON attribute; the collector reads the indicator labels, periods, text blocks, and chart CSV text directly from that payload. It also preserves exact indicator fields in `structured_data`, with original `PageBlocks` array positions and a separate checksum. Unrelated CMS metadata is excluded. Non-indicator blocks are represented by `null` in that retained structure, while their readable content remains in the source text.

## Fact Extraction and Validation

`src/extraction.py` coordinates extraction and supports four observations from the configured Stats NZ pages:

- `unemployment_rate`: percent, level.
- `unemployment_rate_change`: percentage points, quarter-on-quarter.
- `unemployed_people`: non-negative integer count of people.
- `cpi_annual_change`: percent, year-on-year.

Indicator names and descriptions determine the metric; slot numbers alone do not. Values, signs, units, and data periods must be explicit. Quarter periods are converted to calendar quarter boundaries; a period such as `June 2026 year` represents the year ending in June, not a single quarter. The original period text is retained. Future observation periods, invalid numbers, ambiguous labels, mismatched units, and invalid dates are rejected. Unknown publication or update dates remain `null`; they are never filled with retrieval time.

Validation has two parts: Pydantic checks field types and required metadata, then the validator compares the candidate with the saved source mapping, including its meaning, dates, source URL, and evidence reference. Each fact points to its research snapshot, document hashes, and a JSON pointer such as `/PageBlocks/0/Value2` within that document's `structured_data`. Its supporting fields are also retained verbatim. Hashes help detect accidental changes; they do not establish that a publisher's statistic is correct.

`src/seek_extraction.py` adds two national SEEK series: `seek_job_ads_change` and `seek_applications_per_ad_change`. Recognised observed-change sentences in the National Insights sections supply percentage changes. Explicit month-on-month and year-on-year statements remain separate; an implicit monthly change requires the recognised national monthly chart-caption context. Regional, industry, AI-specific, and graduate-specific figures are not mapped to these national aggregates.

SEEK text evidence uses `kind: "text"` and a list of `spans`. Each span records an exact quotation, its role (statement, section, report heading/period, lag, or methodology), and zero-based Unicode character offsets into the saved document's `text`; `end` is exclusive. The candidate validator recreates the supported source mapping and checks all metadata and spans. These references point to saved plain text, not to HTML byte offsets or a later version of the website. Stats NZ JSON references remain supported unchanged.

The SEEK report month comes from its explicit heading. The year must appear in that heading or a consistent, recognised national chart caption; it is never inferred from the URL or retrieval time. Captions provide period context only, not numbers from unseen chart images. Applications require the explicit one-month lag note, including the previous-year transition for January reports. A disagreement between the summary, detailed statement, and expected data period withholds that metric for review. Unknown wording, unsupported comparisons, and ambiguous periods also produce audit issues.

`scope: "all"` denotes the supported national aggregate, not IT graduate vacancies. The `adjustment` field records `trend` for SEEK job ads only when the recognised methodology text supports it for that period; otherwise it stays `not_stated`. The applications series is not automatically assigned the job-ad adjustment. Missing publication metadata stays `null`; the newsroom link's date is not currently promoted to an article publication date.

Identical observations for the same publisher, metric, unit, comparison basis, geography, scope, adjustment, and period are deduplicated. Conflicting values are excluded from accepted facts and flagged for review. Different periods and comparison bases remain separate. Accepted direct mappings receive `high` extraction confidence with an explanation; this is not a guarantee of statistical accuracy or freshness.

The weekly file separates `facts`, `rejected`, `skipped`, and `collection_failures`. The SEEK newsroom is a discovery document and remains skipped; its linked employment article is processed by the SEEK rules. Other unsupported sources remain explicitly skipped. A processed article can have accepted facts and rejected metric candidates at the same time. Historical chart series are retained as source material but not extracted into current facts in this phase.

Older Phase 2 snapshots remain readable, but do not contain the original structured fields needed for Stats NZ extraction. SEEK article extraction can use existing snapshots when they contain the required text and context. Run `python main.py` to collect a fresh snapshot; the script does not reconstruct missing fields from flattened text.

The collector uses sequential requests and an identifying user agent. It checks `robots.txt` once per origin per run, using Protego to handle wildcard rules, and observes crawl delays and request rates with a minimum one-second interval. Unavailable or HTML-challenged robots responses cause that origin to be skipped; HTTP 404/410 is treated as no published robots file. Policies requiring an interval above 60 seconds or restricted visit times are skipped for manual review.

Requests have a 2 MB decompressed response limit. The collector follows at most three same-origin redirects, checking the destination against robots rules before each request. Cross-origin redirects, HTTP errors, unsupported content types, and missing or unusable page content are recorded as failures. There is no browser automation, access-control bypass, automatic retry loop, or broad crawl. Linked PDFs and spreadsheets are recorded as links but are not downloaded in this phase.

Access can vary by source and network. Check the saved failures to see which sources were actually collected. Live collection results are documented in [project progress](PROGRESS.md).

## Tests

Install the development dependencies and run the offline suite:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Tests use synthetic HTML/JSON and HTTPX mock responses. They cover source parsing, period and date preservation, access rules, redirects, timeouts, partial failures, source-to-fact matching, numerical validation, exact text spans, reporting lags, national scope, monthly/annual distinctions, conflicting evidence, snapshot persistence, and CLI failure handling. Live HTTP is blocked by the test setup.

## Project Structure

```text
nz-weekly-intelligence/
├── main.py              # Startup, report week calculation, collection, and saving
├── src/
│   ├── __init__.py
│   ├── config.py        # Environment variables, timezone, and project paths
│   ├── extraction.py    # Deterministic extraction, validation, and evidence saving
│   ├── models.py        # Pydantic research, evidence, and weekly data models
│   ├── research.py      # Direct-source collection, parsing, and snapshot saving
│   └── seek_extraction.py # National SEEK statements, periods, and text evidence
├── data/
│   ├── research/        # Local source snapshots grouped by report week
│   └── weekly/          # Accepted weekly facts and per-run extraction audits
├── reports/             # Future Markdown reports
├── tests/               # Offline collection and CLI tests
├── docs/
│   └── mvp-specification.md
├── .env.example
├── .gitignore
├── requirements.txt
├── requirements-dev.txt
├── PROGRESS.md
└── README.md
```

## Data Models

`SourceDocument` records the requested and final source URLs, title, collected text, retrieval time, collection method, content hash, and links. Stats NZ documents also retain structured indicator fields and their hash. Explicit publication and update metadata are retained as raw strings when available, otherwise `None`. Retrieval time is never used as a replacement publication date.

`ResearchBatch` groups documents and failures with the report week and run timestamps. Its status is `complete`, `partial`, or `unavailable`. Here, `complete` means that all configured collection targets succeeded; it does not mean that the MVP report is complete or that all information is current. Collected text is untrusted input and must be treated as evidence, never as instructions, when LLM extraction is added.

`WeeklyFact` now represents an accepted numerical observation with an explicit unit, comparison basis, original period text and date boundaries, geography, source, dates, and `EvidenceReference`. Its evidence reference includes the snapshot path and hash plus either Stats NZ structured fields and a JSON pointer, or SEEK text spans and their document hash. Schema validation alone does not verify source support; acceptance requires the source-matching validator too.

`WeeklyData` stores the report week, collection timestamp, research snapshot reference and coverage status, accepted facts, rejected candidates, skipped documents, and collection failures. It supports Pydantic JSON serialisation. Research snapshots use schema version 2 while continuing to accept version 1 inputs; new weekly outputs use schema version 3 and the reader still accepts version 2. Version 3 adds text evidence, monthly comparisons, scope, and adjustment metadata. Older code that only supports version 2 cannot read these new outputs.

## Next Steps

Phase 3 now covers structured Stats NZ indicators and a bounded set of national SEEK article statements. Broader article layouts, CSV/spreadsheet evidence, and qualitative claims require additional rules or a future LLM service. Investigating permitted MBIE/RBNZ source access and documenting implemented or deferred coverage remain the next Phase 3 work. Search API integration is deferred by choice. Graduate vacancy discovery, broader international context, and additional source coverage remain future work. Historical comparison, deterministic scoring, and report generation follow in their respective phases.
