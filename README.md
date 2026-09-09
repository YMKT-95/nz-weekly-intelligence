# NZ IT Graduate Weekly Intelligence

A personal, local Python tool for IT graduates seeking employment in New Zealand. The goal is to research relevant information each week, compare changes over time, and generate a Markdown report supported by traceable evidence.

**Phase 2: Direct-source research** is implemented. The script determines the report week, retrieves public source material, and saves a local research snapshot with source URLs, retrieval timestamps, and any collection failures. It runs without API keys. Validated fact extraction, LLM integration, historical comparison, scoring, and Markdown report generation are planned for later phases.

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

A run that collects at least one usable document and saves the snapshot exits with code `0`, even when other sources fail. Partial coverage is logged and recorded in the snapshot. Invalid configuration, an output error, or no usable source documents results in exit code `1`. When all sources fail, the script still saves the failure details if the output directory is writable.

The final log line after collecting usable material is:

```text
[INFO] Research collected. Fact extraction and report generation are not yet connected.
```

Each run saves a separate JSON file under `data/research/YYYY-WXX/`, named with its start timestamp, including microseconds and UTC offset. Repeated runs preserve earlier snapshots, including when a later run fails. Generated research files are excluded from Git.

These snapshots are collected source material, not verified weekly facts or finished reports. `data/weekly/` and `reports/` remain reserved for later phases.

## Direct Sources

The source list is defined in `src/research.py`:

- [Stats NZ unemployment indicator](https://www.stats.govt.nz/indicators/unemployment-rate/).
- [Stats NZ CPI indicator](https://www.stats.govt.nz/indicators/consumers-price-index-cpi/).
- [RBNZ monetary policy decisions](https://www.rbnz.govt.nz/monetary-policy/monetary-policy-decisions).
- [MBIE Jobs Online](https://www.mbie.govt.nz/business-and-employment/employment-and-skills/labour-market-reports-data-and-analysis/jobs-online).
- [SEEK NZ newsroom](https://nz.seek.com/about/news), plus the first employment report linked on that page. The URL is discovered on each run rather than hard-coded to a particular month. Its position does not establish that it was published during the report week.

HTTPX retrieves the pages, and BeautifulSoup extracts readable content. Stats NZ indicator pages embed their content in a `pageViewData` JSON attribute; the collector reads the indicator labels, periods, text blocks, and chart CSV text directly from that payload. It excludes unrelated CMS metadata and does not calculate or infer metric values.

The collector uses sequential requests and an identifying user agent. It checks `robots.txt` once per origin per run, using Protego to handle wildcard rules, and observes crawl delays and request rates with a minimum one-second interval. Unavailable or HTML-challenged robots responses cause that origin to be skipped; HTTP 404/410 is treated as no published robots file. Policies requiring an interval above 60 seconds or restricted visit times are skipped for manual review.

Requests have a 2 MB decompressed response limit. The collector follows at most three same-origin redirects, checking the destination against robots rules before each request. Cross-origin redirects, HTTP errors, unsupported content types, and missing or unusable page content are recorded as failures. There is no browser automation, access-control bypass, automatic retry loop, or broad crawl. Linked PDFs and spreadsheets are recorded as links but are not downloaded in this phase.

Access can vary by source and network. Check the saved failures to see which sources were actually collected. Live collection results are documented in [project progress](PROGRESS.md).

## Tests

Install the development dependencies and run the offline suite:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Tests use synthetic HTML/JSON and HTTPX mock responses. They cover source parsing, period and date preservation, access rules, redirects, timeouts, partial failures, snapshot persistence, and CLI failure handling. Live HTTP is blocked by the test setup.

## Project Structure

```text
nz-weekly-intelligence/
├── main.py              # Startup, report week calculation, collection, and saving
├── src/
│   ├── __init__.py
│   ├── config.py        # Environment variables, timezone, and project paths
│   ├── models.py        # Pydantic research, evidence, and weekly data models
│   └── research.py      # Direct-source collection, parsing, and snapshot saving
├── data/
│   ├── research/        # Local source snapshots grouped by report week
│   └── weekly/          # Future validated weekly evidence
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

`SourceDocument` records the requested and final source URLs, title, collected text, retrieval time, collection method, content hash, and links. Explicit publication and update metadata are retained as raw strings when available, otherwise `None`. Retrieval time is never used as a replacement publication date. Data periods remain in the source text for Phase 3 extraction.

`ResearchBatch` groups documents and failures with the report week and run timestamps. Its status is `complete`, `partial`, or `unavailable`. Here, `complete` means that all configured collection targets succeeded; it does not mean that the MVP report is complete or that all information is current. Collected text is untrusted input and must be treated as evidence, never as instructions, when LLM extraction is added.

`WeeklyFact` stores a category, metric, numerical value or textual fact, unit, data period, source name, HTTP(S) source URL, publication date, timezone-aware retrieval time, and confidence level. The source, data period, and value must be present and non-empty. An unknown publication date is represented by `None` and must not be replaced with the retrieval date. Structural validation does not verify factual accuracy; source support will be checked during evidence extraction.

`WeeklyData` stores the report week, its start and end dates, a timezone-aware run timestamp, and a list of facts. It supports Pydantic JSON serialisation. The entry point currently uses an empty instance for report metadata; research collection does not populate validated facts yet.

## Next Steps

Phase 3 will turn collected material into structured, validated evidence and select an LLM service if needed. Search API integration is deferred by choice; direct sources need no search credentials. Graduate vacancy discovery, broader international context, and additional source coverage remain future work. Historical comparison, deterministic scoring, and report generation follow in their respective phases.
