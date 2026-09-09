# NZ IT Graduate Weekly Intelligence

A personal, local Python tool for IT graduates seeking employment in New Zealand. The goal is to research relevant information each week, compare changes over time, and generate a Markdown report supported by traceable evidence.

Only **Phase 1: Foundation** is implemented. The script loads configuration, determines the report week, creates output directories, and logs its status. Web research, LLM integration, historical comparison, scoring, and report generation are planned for later phases. The current script makes no API requests and produces no sample statistics or placeholder reports.

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

Phase 1 runs without a `.env` file or API keys. To customise local settings, copy the template during initial setup:

```bash
cp .env.example .env
```

- `REPORT_TIMEZONE`: defaults to `Pacific/Auckland`.
- `LLM_API_KEY`, `LLM_MODEL`, and `SEARCH_API_KEY`: reserved for future service integrations and may remain empty for now.

Existing environment variables take precedence over `.env`. The configuration file is always loaded from the project root, regardless of the working directory. Do not commit real credentials; `.env` is excluded by `.gitignore`, and API keys are not written to logs.

## Running the Script

```bash
source .venv/bin/activate
python main.py
```

The logs show the ISO report week, its Monday-to-Sunday date range, the actual run time with its timezone, and the output directories. During a midweek run, Sunday marks the end of the report week; it does not imply that information from future dates has been collected.

A successful run exits with code `0`. Invalid configuration or a failure to create directories is logged as an error and exits with code `1`. The final log line for a successful Phase 1 run is:

```text
[INFO] Foundation ready. Research and report generation are not yet connected.
```

Repeated runs do not overwrite existing data or reports. Later phases will save actual results to `data/weekly/YYYY-WXX.json` and `reports/YYYY-WXX.md`. The current script only ensures that the directories exist.

## Project Structure

```text
nz-weekly-intelligence/
├── main.py              # Startup, report week calculation, logging, and directory setup
├── src/
│   ├── __init__.py
│   ├── config.py        # Environment variables, timezone, and project paths
│   └── models.py        # Pydantic evidence and weekly data models
├── data/weekly/         # Future structured weekly data
├── reports/             # Future Markdown reports
├── tests/               # Reserved for automated tests
├── docs/
│   └── mvp-specification.md
├── .env.example
├── .gitignore
├── requirements.txt
├── PROGRESS.md
└── README.md
```

## Data Models

`WeeklyFact` stores a category, metric, numerical value or textual fact, unit, data period, source name, HTTP(S) source URL, publication date, timezone-aware retrieval time, and confidence level. The source, data period, and value must be present and non-empty. An unknown publication date is represented by `None` and must not be replaced with the retrieval date. Structural validation does not verify factual accuracy; source support will be checked during evidence extraction.

`WeeklyData` stores the report week, its start and end dates, a timezone-aware run timestamp, and a list of facts. It supports Pydantic JSON serialisation. Phase 1 creates an empty weekly data container in memory only.

## Next Steps

Phase 2 will select search and LLM services and begin research with Stats NZ, RBNZ, and one labour market source. Later phases will add evidence extraction and validation, historical comparison, deterministic scoring, report generation, and comprehensive testing. Research, scoring, and report modules will be added as those features are implemented.
