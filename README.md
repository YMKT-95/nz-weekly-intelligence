# NZ IT Graduate Weekly Intelligence

A personal, local Python tool for IT graduates seeking employment in New Zealand. The goal is to research relevant information each week, compare changes over time, and generate a Markdown report supported by traceable evidence.

**Phase 6 report generation is implemented, with optional OpenAI interpretation and a local template fallback.** The script collects sources, validates facts, compares history, calculates supported provisional components, and saves a Markdown report. The full live six-component index remains unavailable. MBIE live access, RBNZ permission, graduate availability, IT demand, and automation-pressure coverage remain unresolved. Live LLM validation requires your own API key; this is not yet the complete original MVP.

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
- `LLM_PROVIDER`: `none` by default; set `openai` to request interpretation. The example file selects OpenAI.
- `LLM_API_KEY`: your OpenAI API key; never commit it. A missing key produces a visibly labelled template fallback.
- `LLM_MODEL`: defaults to `gpt-4.1-mini-2025-04-14`; choose a model available to your API account that supports Responses structured outputs.
- `LLM_TIMEOUT_SECONDS`: connect/read/write/pool timeout for the LLM call, default `45`, greater than `0` and at most `120`; not an overall run deadline.
- `SEARCH_API_KEY`: reserved for a future search integration.

Existing environment variables take precedence over `.env`. The configuration file is always loaded from the project root, regardless of the working directory. Do not commit real credentials; `.env` is excluded by `.gitignore`, and API keys are not written to logs.

## Running the Script

```bash
source .venv/bin/activate
python main.py
```

The logs show the ISO report week, its Monday-to-Sunday date range, the actual run time with its timezone, and the output directories. During a midweek run, Sunday marks the end of the report week; it does not imply that information from future dates has been collected.

A run that extracts at least one accepted fact and saves evidence, comparison, scoring, and a Markdown report exits with code `0`, even when other sources fail, there is no previous weekly file, or the overall index is unavailable because evidence is incomplete. Partial research coverage, rejected candidates, and unprocessed sources are recorded in the output. Invalid configuration, an output error, or no accepted facts results in exit code `1`. Even if no facts are accepted, the script saves the research and extraction audit when the output directory is writable, preserving any existing weekly evidence file.

The final log line identifies the generated report, for example:

```text
[INFO] Weekly Markdown report saved: /path/to/nz-weekly-intelligence/reports/2026-W37.md
```

Each run saves a separate JSON file under `data/research/YYYY-WXX/`, named with its start timestamp, including microseconds and UTC offset. Repeated runs preserve earlier snapshots, including when a later run fails. Generated research files are excluded from Git.

Research snapshots remain collected source material. Accepted facts and the validation audit are saved separately:

- `data/weekly/YYYY-WXX.json`: the most recent run with at least one accepted fact for that week.
- `data/weekly/runs/YYYY-WXX/<timestamp>.json`: a preserved audit for each extraction run, including runs that accepted no facts.

The weekly file is replaced atomically only after its new content is written successfully. A later partial run with accepted facts replaces it with that run's evidence; facts from different runs are not silently combined. Earlier results remain in the run archive. A run with no accepted facts leaves the weekly file unchanged, so always check the command's exit code and output timestamps. Existing reports are preserved on an evidence failure; their timestamps may therefore be older than the failed attempt. All generated files are excluded from Git.

## Historical Comparison

`src/analysis.py` compares the current run's immutable evidence archive with the most recent usable earlier canonical file under `data/weekly/`. It accepts evidence schema versions 2 and 3 and validates the report's ISO week, calendar boundaries, collection timestamp, and fact retrieval timestamps. Current-week reruns, future weeks, nested run archives, and unrelated files are not historical baselines. Invalid, unreadable, or empty earlier files are skipped with audit notes. A missing week is allowed, and `weeks_apart` records the actual gap. All metrics use the same selected historical file; values are not silently filled from different older weeks.

Each series is identified by publisher, category, metric, unit, comparison basis, geography, scope, and adjustment. The latest data period for that series is selected in each file. Conflicting latest values are retained for review without arithmetic. A changed publisher, unit, adjustment, or comparison basis creates separate series rather than an invalid numerical comparison.

Comparison statuses distinguish:

- `baseline`: no usable earlier weekly file; change is unknown.
- `new_series`: no matching series in the selected earlier file; this does not prove a new publication.
- `missing_current`: a previous series is absent now; its value is not zero.
- `unchanged_observation`: the same value and period were collected again; this does not establish a stable market.
- `revised_observation`: the recorded value for the same period changed; a revision/correction difference is kept separately from new-period movement.
- `new_observation`: a later period with the same period definition is available, even when its value is unchanged.
- `older_observation`: current coverage contains an older period; no backwards change is calculated.
- `not_comparable`: latest values conflict or period definitions differ; no change is calculated.

Percentage levels and percentage growth rates are subtracted in **percentage points**. For example, 5.4% to 5.6% is +0.2 percentage points, and -4% annual growth to -2% is +2 percentage points in the growth rate, while growth remains negative. People counts produce count differences. These are differences between the recorded data periods, not newly calculated weekly/monthly/annual growth rates. Rolling annual windows may overlap; full calendar months remain comparable despite different numbers of days. Only later comparable periods receive review flags; repeated observations and revisions do not enter new-period direction assessment.

`REVIEW_RULES` in `src/analysis.py` defines editable MVP thresholds: 0.2 percentage points for unemployment rate and its quarterly change, 5,000 people for unemployed count, 0.5 percentage points for CPI annual growth, 1 percentage point for supported SEEK growth rates, and 2 percentage points for MBIE annual growth. Absolute differences at or above a threshold are `review_worthy`. These are initial analytical choices to calibrate with experience, not statistical significance tests. Unknown series semantics have no threshold.

`labour_direction` is a limited interpretation of supported new-period national signals across unemployment, job availability, and competition. At least two themes must have new comparable observations; unemployment rate/count/change are not treated as three independent themes. Significant favourable and adverse movements produce `mixed`; only favourable or adverse movements produce `improving` or `deteriorating`; movements below the review thresholds produce `stable`. Otherwise the result is `insufficient_data`. CPI has no automatic favourable/adverse classification. This does not estimate graduate hiring prospects or calculate the Job Search Index.

Comparison output is saved separately:

- `data/weekly/comparisons/YYYY-WXX.json`: the latest successfully saved comparison for that week.
- `data/weekly/comparisons/runs/YYYY-WXX/<evidence-run-timestamp>.json`: immutable comparison audit for that evidence run.

The output records both input file paths, hashes, report weeks, selected facts with their original evidence references and `/facts/<index>` locations, history notes, statuses, deltas, and review rules. Paths refer to local files; all generated outputs remain ignored by Git. Comparison trusts the accepted evidence format and does not rerun source extraction on old facts; hashes and embedded facts identify exactly what was compared.

The comparison file is replaced atomically after archiving. If comparison fails, already-saved evidence is retained and the command exits `1`; an older comparison file may remain, so check the exit code and its referenced current evidence file. If no facts are accepted, the command preserves existing weekly evidence and comparison files and exits `1`. A successful first run saves baseline statuses and an insufficient-data direction.

## Provisional Scoring

`src/scoring.py` implements the six-component calculator and three bounded proxy mappings. Read [the scoring policy](docs/scoring-policy.md) for the formulas, source criteria, provisional age limits, fallback behaviour, and limitations. These rules represent declared judgments rather than objective measurements or calibrated hiring probabilities. They do not use Phase 4 review flags to add or subtract points.

The weights are job availability 25%, graduate availability 20%, competition 20%, economy 15%, IT demand 10%, and automation pressure 10%. Every scored component retains its exact accepted fact, evidence-file reference, selected rule, data age, reason, and limitations. Job availability prefers eligible SEEK monthly trend growth and otherwise uses the separately defined MBIE annual unadjusted mapping. Competition uses lagged national applications-per-ad growth. The economy mapping uses unemployment alone as a narrow proxy, without mechanically scoring CPI or double-counting unemployment measures.

Graduate availability, IT demand, and automation pressure have no supported mapping yet. Missing, stale, incompatible, or conflicting evidence produces an unavailable component. There is no neutral placeholder, zero substitution, historical backfill, or weight redistribution. `overall_score` stays `null` and `status` is `insufficient_evidence` until all six components are scored. `covered_weight_percent` describes the share of component weight with scores, not confidence or a partial index.

Data age is measured from the data period's end to the evidence run's collection date. Recollection and page updates do not refresh old observations. Component formulas are clipped to 0–10 and rounded to two decimals; the complete weighted index is rounded to one decimal with decimal ROUND_HALF_UP. The output records a policy version and checksum. Index comparisons require two complete results with compatible methods and input definitions; source switches, policy changes, revisions, and older observations do not produce a new-period index trend.

Outputs are separate from factual evidence and comparison:

- `data/weekly/scores/YYYY-WXX.json`: latest successfully saved scoring result, including incomplete results.
- `data/weekly/scores/runs/YYYY-WXX/<evidence-run-timestamp>.json`: immutable audit for each scoring run.

An incomplete scoring result replaces an older weekly score view, preventing an obsolete complete index from being presented as current. A scoring failure returns exit code `1` and leaves already-saved evidence/comparison intact; an old score view may remain, so inspect the command exit code and referenced evidence before using it. With no accepted facts, the existing extraction failure path preserves earlier views and exits nonzero.

The latest validated live run scored only competition and the unemployment-based economic proxy, covering 35% of the specified weight. It correctly produced no overall index. Synthetic complete-input tests verify all six-component arithmetic and history handling; they do not establish six-component live evidence coverage.

## Markdown Reports and OpenAI Setup

`src/reporting.py` renders the specification's report sections from saved evidence, comparison, and scoring archives. It checks that the inputs reference the same evidence path, week, checksum, timestamp, and fact pointers. Selected historical files must still match their recorded hashes. This checks provenance; it does not repeat extraction or independently validate the publishers' statistics.

Facts retain their units, comparison basis, observation periods, source links, and known/unknown publication and update dates. Baselines, repeated observations, revisions, later periods, and missing series remain distinct. Unsupported graduate, global, and NZX coverage is explicit. The overall index remains unavailable until every component has a supported score. General job-search suggestions and heuristic/LLM interpretation are labelled separately from facts.

Outputs:

- `reports/YYYY-WXX.md`: the latest successfully saved weekly report.
- `reports/runs/YYYY-WXX/<evidence-run-timestamp>.md`: immutable report archive.
- `reports/runs/YYYY-WXX/<evidence-run-timestamp>.json`: report checksum and narration audit, including status, configured model, prompt version, request checksum, response ID when available, and accepted interpretation notes.

The report records evidence/comparison/scoring hashes. Archives and the audit are written before the weekly view is atomically replaced. If reporting fails, the command exits `1`, preserves the earlier weekly report, and retains already-saved pipeline stages. Outputs from a failed run can therefore have different ages; inspect exit status and provenance. A narration failure alone is a successful, visibly labelled template fallback. Re-running `main.py` creates a fresh evidence/report run; replaying the exact same run into the same report directory cannot overwrite its archive.

To enable OpenAI:

1. Create an API key in the [OpenAI API dashboard](https://platform.openai.com/api-keys), following the [official quickstart](https://developers.openai.com/api/docs/quickstart). The account must have API access and sufficient quota/billing for the chosen model.
2. Create `.env` from `.env.example` if it does not already exist. Edit the existing file otherwise; do not overwrite your credentials.
3. Set `LLM_PROVIDER=openai`, paste the key into `LLM_API_KEY`, and keep `LLM_MODEL=gpt-4.1-mini-2025-04-14` for the initial integration. This documented [model snapshot](https://developers.openai.com/api/docs/models/gpt-4.1-mini) supports Responses and structured outputs; account access can vary.
4. Run `python main.py`. Check `Report narration:` in the logs and the report's status. `generated` means interpretation passed the format/reference checks; `fallback` explains why only the template was used. To disable API calls, set `LLM_PROVIDER=none`.

`src/narration.py` uses the [Responses structured-output API](https://developers.openai.com/api/docs/guides/structured-outputs) through the existing HTTPX dependency. Each enabled run sends one compact summary of accepted public evidence, comparison statuses, provisional scores, and coverage gaps to OpenAI. It does not send raw articles, credentials in prompts, local file paths, or source snapshots. The request has no search/tools, no automatic retries or redirects, a 1,200-output-token limit, bounded input/response sizes, and `store=false`. This is not a promise of zero provider retention. API use is billed by the provider; repeated runs can incur further charges.

Python writes every factual/numerical section and source link. The LLM returns only short interpretation notes plus existing fact IDs. Unknown references, digits, percentage/currency symbols, URLs, selected markup, malformed output, refusals, incomplete responses, and transport/API errors trigger a template fallback with a safe diagnostic. Provider response bodies and exceptions are not echoed into logs. Source-derived text and generated prose are escaped before Markdown rendering.

These checks constrain format and references; they **do not prove semantic support or eliminate hallucinations**, including unsupported claims expressed in words. Generated notes are labelled as requiring review. No LLM text enters accepted evidence, comparison arithmetic, or scoring. Live quality evaluation and stronger semantic checks belong to Phase 7; LLM extraction and search remain deferred.

## Direct Sources

The source list is defined in `src/research.py`:

- [Stats NZ unemployment indicator](https://www.stats.govt.nz/indicators/unemployment-rate/).
- [Stats NZ CPI indicator](https://www.stats.govt.nz/indicators/consumers-price-index-cpi/).
- [RBNZ monetary policy decisions](https://www.rbnz.govt.nz/monetary-policy/monetary-policy-decisions): explicitly deferred; no HTTP requests are made for this target.
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

`src/mbie_extraction.py` supports `mbie_job_ads_annual_change` from the national quarterly overview on the official Jobs Online HTML page. It requires a recognised overview heading, the first national result, matching explicit quarters, percentage-change wording, and supporting index/adjustment methodology. The result is an annual percentage change in an unadjusted job-advertisement index, not a vacancy count or a graduate hiring measure. Its data period is the three-month quarter; `year_on_year` describes the comparison to that quarter a year earlier. No comparison is calculated in this increment.

The MBIE reference retains exact text spans, including a visible page update date when available. Page update and report publication dates remain distinct. Unsupported layouts, missing methodology, mismatched periods, conflicting totals, or invalid dates are rejected. Downloadable CSV/XLSX data is not yet parsed; the HTML rules can operate only after usable page content has been collected. The implementation is tested with synthetic HTML and mocked HTTP, but has not produced a live MBIE fact because the tested network still receives an access-challenge page.

Identical observations for the same publisher, metric, unit, comparison basis, geography, scope, adjustment, and period are deduplicated. Conflicting values are excluded from accepted facts and flagged for review. Different periods and comparison bases remain separate. Accepted direct mappings receive `high` extraction confidence with an explanation; this is not a guarantee of statistical accuracy or freshness.

The weekly file separates `facts`, `rejected`, `skipped`, and `collection_failures`. The SEEK newsroom is a discovery document and remains skipped; its linked employment article is processed by the SEEK rules. Other unsupported sources remain explicitly skipped. A processed article can have accepted facts and rejected metric candidates at the same time. Historical chart series are retained as source material but not extracted into current facts in this phase.

Older Phase 2 snapshots remain readable, but do not contain the original structured fields needed for Stats NZ extraction. SEEK article extraction can use existing snapshots when they contain the required text and context. Run `python main.py` to collect a fresh snapshot; the script does not reconstruct missing fields from flattened text.

The collector uses sequential requests and an identifying user agent. It checks `robots.txt` once per origin per run, using Protego to handle wildcard rules, and observes crawl delays and request rates with a minimum one-second interval. Unavailable or HTML-challenged robots responses cause that origin to be skipped; HTTP 404/410 is treated as no published robots file. Policies requiring an interval above 60 seconds or restricted visit times are skipped for manual review.

Requests have a 2 MB decompressed response limit. The collector follows at most three same-origin redirects, checking the destination against robots rules before each request. Cross-origin redirects, HTTP errors, unsupported content types, and missing or unusable page content are recorded as failures. There is no browser automation, access-control bypass, automatic retry loop, or broad crawl. Linked PDFs and spreadsheets are recorded as links but are not downloaded in this phase.

Access can vary by source and network. Check the saved failures to see which sources were actually collected. Live collection results are documented in [project progress](PROGRESS.md).

## MBIE and RBNZ Access Status

On 11 September 2026, the script still received a challenge shell from MBIE's Jobs Online page. The [official page](https://www.mbie.govt.nz/business-and-employment/employment-and-skills/labour-market-reports-data-and-analysis/jobs-online) advertises monthly CSV and quarterly CSV/XLSX downloads. Their actual file layouts were not retrieved or verified in this increment, so no download extractor or guessed download URL was added. Search-engine descriptions were used for source investigation only and are never inserted into the script's evidence snapshots.

RBNZ's [terms of use](https://www.rbnz.govt.nz/about-our-site/terms-of-use) require prior written permission for this kind of automated collection and provide an allow-list request route. Its [official data-file index](https://www.rbnz.govt.nz/statistics/series/data-file-index-page) links the B2 daily workbook, which is a possible future OCR source. Both the configured website and the separately published download host returned HTTP 403 for their robots files during the access investigation. No workbook was downloaded and no OCR extractor is implemented.

The RBNZ target now has an explicit `deferred_reason` in `src/research.py`. Collection records `kind: "deferred"` before any HTTP request for that target. Ordinary access failures have `kind: "unavailable"`; older snapshots without `kind` retain that default. Both remain in the weekly `collection_failures` audit, and logs distinguish their counts. Existing collection status remains `partial` when other sources succeed.

To reopen MBIE live coverage, obtain a usable response through a permitted route and verify the extractor against the saved HTML, or inspect an official download before adding its parser. To reopen RBNZ, obtain the publisher's written permission, confirm the allowed access route, and inspect the official OCR data before implementing extraction. A permission request has not been submitted on the user's behalf. Neither unavailable source is counted as successful live evidence coverage.

## Tests

Install the development dependencies and run the offline suite:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Tests use synthetic HTML/JSON and HTTPX mock responses. They cover source parsing, period and date preservation, access rules, redirects, timeouts, partial failures, source-to-fact matching, historical file selection, period-aware comparisons, revisions, missing coverage, review thresholds, numerical validation, exact text spans, reporting lags, national scope, monthly/annual distinctions, conflicting evidence, snapshot persistence, scoring weights, rounding, missing/stale data, method compatibility, report provenance, API contracts/fallbacks, and CLI failure handling. Live HTTP is blocked by the test setup.

## Project Structure

```text
nz-weekly-intelligence/
├── main.py              # Startup, report week calculation, collection, and saving
├── src/
│   ├── __init__.py
│   ├── analysis.py      # Historical selection, comparison, review flags, and saving
│   ├── config.py        # Environment variables, timezone, and project paths
│   ├── extraction.py    # Deterministic extraction, validation, and evidence saving
│   ├── mbie_extraction.py # MBIE national annual changes and text evidence
│   ├── models.py        # Pydantic research, evidence, and weekly data models
│   ├── research.py      # Direct-source collection, parsing, and snapshot saving
│   ├── reporting.py     # Markdown report rendering and atomic persistence
│   ├── narration.py     # Optional OpenAI interpretation with validated references
│   ├── scoring.py       # Provisional components, strict aggregation, and scoring history
│   └── seek_extraction.py # National SEEK statements, periods, and text evidence
├── data/
│   ├── research/        # Local source snapshots grouped by report week
│   └── weekly/          # Accepted weekly facts and per-run extraction audits
├── reports/             # Weekly Markdown reports and per-run audits
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

`WeeklyFact` now represents an accepted numerical observation with an explicit unit, comparison basis, original period text and date boundaries, geography, source, dates, and `EvidenceReference`. Its evidence reference includes the snapshot path and hash plus either Stats NZ structured fields and a JSON pointer, or SEEK/MBIE text spans and their document hash. Schema validation alone does not verify source support; acceptance requires the source-matching validator too.

`WeeklyData` stores the report week, collection timestamp, research snapshot reference and coverage status, accepted facts, rejected candidates, skipped documents, and collection failures. It supports Pydantic JSON serialisation. Research snapshots use schema version 2 while continuing to accept version 1 inputs; new weekly outputs use schema version 3 and the reader still accepts version 2. Version 3 adds text evidence, monthly comparisons, scope, and adjustment metadata. Older code that only supports version 2 cannot read these new outputs.

## Next Steps

Phase 5's engine is implemented; sufficient evidence and defensible mappings for the complete live six-component index remain outstanding. Phase 6 now generates reports that explicitly communicate this limitation. Next is a credential-backed OpenAI smoke test and Phase 7 end-to-end/quality refinement. Historical comparison is implemented, while broader history analysis (multi-year highs/lows and revision-aware reconstruction of entire series) remains future work.

Source-coverage follow-ups remain tracked separately: live validation of MBIE when permitted usable content is available, and RBNZ permission/access investigation before implementing OCR extraction. Broader article layouts, CSV/spreadsheet evidence, qualitative claims, graduate vacancy discovery, and international context remain extensions. Search API integration is deferred by choice.
