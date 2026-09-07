# Personal NZ IT Graduate Weekly Intelligence Script

## 1. Project Definition

Build a **personal, local Python automation script** that I can run once a week to automatically research the New Zealand economy and IT graduate job market, analyse meaningful changes, and generate a personalised weekly intelligence report.

This is **not a web application and not a SaaS product**.

The purpose is to automate a repetitive personal workflow:

```text
Search multiple sources
        ↓
Collect relevant information
        ↓
Extract important facts and metrics
        ↓
Compare with previous weeks
        ↓
Analyse what changed
        ↓
Assess impact on NZ IT graduates
        ↓
Calculate Personal Job Search Index
        ↓
Generate weekly Markdown report
```

The final output should resemble the existing report format:

> 🇳🇿 NZ Economy & IT Graduate Weekly Intelligence Report  
> Week: 3–9 August 2026

---

# 2. Primary User

The only intended user is **myself**.

The perspective of the report is:

> An IT graduate in New Zealand looking for an entry-level / junior software or IT position.

The report should therefore not become a generic economic or technology news report.

The key question throughout the analysis is:

> **"What does this week's information mean for an IT graduate looking for their first IT/software job in New Zealand?"**

---

# 3. MVP Scope

The MVP should do five things well:

1. Research relevant current information.
2. Extract and structure reliable facts.
3. Compare the current situation with previous available data.
4. Analyse implications for an NZ IT graduate.
5. Generate a concise weekly Markdown report.

The MVP should be runnable locally with:

```bash
python main.py
```

The script should generate something like:

```text
reports/
└── 2026-W32.md
```

and optionally:

```text
data/
└── 2026-W32.json
```

---

# 4. Explicitly Out of Scope

Do NOT build:

- user authentication
- user accounts
- registration/login
- frontend
- dashboard
- REST API
- mobile application
- PostgreSQL
- Redis
- Kafka
- microservices
- Kubernetes
- Docker
- cloud infrastructure
- payment system
- multi-user functionality

Do not build infrastructure simply because it might be useful in the future.

This is a **small personal automation tool**.

Prefer a simple Python script and local files.

---

# 5. Recommended Technology

Use:

- Python 3.12+
- `httpx` for HTTP requests where appropriate
- BeautifulSoup where appropriate
- Pydantic for structured data validation
- an LLM API for extraction/analysis/report generation
- a web-search/research API or tool
- JSON for structured data
- Markdown for final reports
- pytest for tests

Use environment variables for API keys.

Example:

```text
LLM_API_KEY=
LLM_MODEL=
SEARCH_API_KEY=
```

Never hard-code credentials.

---

# 6. Simple Project Structure

Start with a simple structure:

```text
nz-weekly-intelligence/
│
├── main.py
│
├── src/
│   ├── research.py
│   ├── extraction.py
│   ├── analysis.py
│   ├── scoring.py
│   └── report.py
│
├── data/
│   └── weekly/
│
├── reports/
│
├── tests/
│
├── .env
├── .env.example
├── requirements.txt
└── README.md
```

Do not create unnecessary classes or abstractions.

If the project later becomes more complex, refactor then.

---

# 7. Overall Pipeline

`main.py` should orchestrate the following process:

```text
1. Determine current report week
        ↓
2. Load previous weekly data/report
        ↓
3. Conduct web research
        ↓
4. Extract structured facts
        ↓
5. Validate facts
        ↓
6. Compare with previous data
        ↓
7. Identify significant changes
        ↓
8. Calculate Personal Job Search Index
        ↓
9. Generate report
        ↓
10. Save Markdown + structured JSON
```

The process should continue if a non-critical source is unavailable.

---

# 8. Research Areas

The research should cover five main areas.

## 8.1 New Zealand Economy

Monitor important indicators such as:

- unemployment
- employment
- wage growth
- CPI
- underlying/core inflation
- OCR
- GDP
- business confidence
- consumer confidence
- immigration where relevant
- major government economic policies

Prioritise primary sources such as:

- Stats NZ
- Reserve Bank of New Zealand
- NZ Treasury
- MBIE

Important rule:

**Do not pretend that old data is new data.**

For example:

```text
CPI: 4.1% y/y
Data period: quarter ending June 2026
```

The report should make clear that this is the latest available CPI data, even if it was not released during the current week.

---

# 9. NZ Labour Market

Research the broader NZ employment environment.

Important signals include:

- job advertisements
- applications per job advertisement
- unemployment
- employment growth
- labour demand
- hiring trends
- industry-level employment changes

Important sources may include:

- SEEK NZ
- Stats NZ
- MBIE
- other reputable NZ employment sources

For SEEK, when available, capture:

```text
job ads month-on-month
job ads year-on-year
applications per job advertisement
```

The report should distinguish:

```text
current change
month-on-month change
year-on-year change
```

---

# 10. NZ IT / Software Graduate Job Market

This is the most important research area.

Research current vacancies and hiring signals for:

```text
Software Engineer
Software Developer
Backend Developer
Frontend Developer
Full Stack Developer
C# Developer
.NET Developer
Java Developer
JavaScript Developer
TypeScript Developer
Cloud Engineer
DevOps Engineer
QA Engineer
Test Engineer
IT Graduate
Graduate Developer
Graduate Software Engineer
Junior Developer
Entry-level Developer
```

The system should pay particular attention to:

```text
Internship
Graduate
Entry Level
Junior
```

and distinguish them from:

```text
Mid Level
Senior
```

The report should never make the following mistake:

```text
1,400 software jobs
=
1,400 graduate opportunities
```

These are fundamentally different signals.

For example:

```text
Total software-related jobs: 1,427
Entry-level jobs: 426
Internships: 38
```

should be treated as three separate indicators.

---

# 11. Job Market Search Strategy

The script should use web search and/or publicly available sources to identify current job-market information.

Possible sources include:

- SEEK
- LinkedIn Jobs
- Trade Me Jobs
- company career pages
- graduate-program pages
- reputable employment reports

Do not implement aggressive scraping.

Do not bypass authentication, CAPTCHAs, robots restrictions, or other access controls.

If a website cannot be reliably accessed automatically, use another legitimate source or web-search results.

The system should record the source of important information.

---

# 12. Global Context

Research selected international developments that could reasonably affect NZ employment or the technology sector.

## United States

Relevant topics:

- unemployment
- nonfarm payrolls
- Federal Reserve decisions
- technology employment
- technology layoffs
- technology hiring

## China

Relevant topics:

- exports
- imports
- AI
- semiconductors
- technology exports
- domestic demand

## Global Technology

Relevant topics:

- AI employment
- AI-related hiring
- cloud computing
- software engineering demand
- technology layoffs
- semiconductor industry
- outsourcing

### Important filtering rule

Do not include international news merely because it is interesting.

Only include it when it has a plausible connection to:

- NZ economy
- NZ employment
- NZ technology sector
- IT hiring
- software engineering
- graduate employment prospects

---

# 13. NZ Technology / Business Signals

Monitor relevant NZ business and technology developments.

Examples:

- NZX overall trend
- major NZ technology companies
- major technology employers
- technology investment
- major contracts
- government technology spending
- hiring announcements
- layoffs
- technology-sector developments

This is not an investment report.

The purpose is to identify useful signals about the NZ technology/business environment.

---

# 14. Research Philosophy

The system should prioritise:

```text
Relevance > Quantity
Primary sources > Secondary sources
Evidence > Opinion
Change > Repetition
NZ graduate impact > General news
```

Do not try to collect every piece of news.

The objective is to answer:

> **What materially changed this week, and why should an NZ IT graduate care?**

---

# 15. Structured Evidence

Before generating the final report, convert important information into structured objects.

Example:

```json
{
  "category": "NZ Labour Market",
  "metric": "job advertisements",
  "value": -4,
  "unit": "percent_mom",
  "period": "July 2026",
  "source": "SEEK",
  "source_url": "...",
  "publication_date": "2026-08-...",
  "confidence": "high"
}
```

Another example:

```json
{
  "category": "NZ Economy",
  "metric": "unemployment_rate",
  "value": 5.6,
  "unit": "percent",
  "period": "2026-Q2",
  "source": "Stats NZ",
  "source_url": "...",
  "confidence": "high"
}
```

Qualitative evidence can use:

```json
{
  "category": "Global Technology",
  "claim": "US technology hiring weakened during the latest reporting period.",
  "source": "source name",
  "source_url": "...",
  "relevance": "medium",
  "confidence": "medium"
}
```

---

# 16. Evidence Rules

Every important numerical statement in the final report must have supporting evidence.

At minimum:

```text
value
period
source
source URL
```

The system must:

- never invent numerical values;
- never invent source URLs;
- never invent publications;
- never present estimates as official statistics;
- identify the data period;
- distinguish facts from interpretation;
- prefer primary sources when sources disagree.

If a metric is unavailable:

```text
Data unavailable
```

is acceptable.

Do not guess.

---

# 17. Fact vs Interpretation vs Prediction

The report should distinguish three levels.

### Fact

Example:

> NZ unemployment increased to 5.6%.

### Interpretation

Example:

> This suggests stronger competition for available entry-level positions.

### Prediction

Example:

> Graduate hiring may remain challenging in the near term.

The system should not present predictions as facts.

---

# 18. Previous Week Comparison

The script should use the previous available report/data as context.

For example:

```text
Previous week:
Job Search Index = 6.8

Current week:
Job Search Index = 6.6

Change:
-0.2
```

Also compare important metrics:

```text
Unemployment:
5.4% → 5.6%

Job advertisements:
-22% y/y → -26% y/y

Applications per job:
+8% m/m → +11% m/m
```

The analysis should classify the overall direction as:

```text
Improving
Stable
Deteriorating
Mixed
```

when appropriate.

---

# 19. Significant Change Detection

Do not report every small numerical movement.

Prioritise:

- large month-on-month changes;
- large year-on-year changes;
- new multi-year highs/lows;
- major policy changes;
- important employment announcements;
- significant technology-sector events;
- meaningful changes in graduate hiring;
- significant changes in competition.

The goal is to identify signals that can affect job-search decisions.

---

# 20. Personal Job Search Index

Create a score from:

```text
0–10
```

Higher score = more favourable environment for finding an IT graduate job.

Initial weighting:

```text
Job availability                    25%
Graduate/entry-level availability  20%
Competition                         20%
NZ economic conditions              15%
IT-sector demand                    10%
AI/automation pressure              10%
```

Each component receives a 0–10 score.

Example:

```text
Job availability:                  6.0
Graduate availability:             4.0
Competition:                       3.5
NZ economy:                        6.0
IT-sector demand:                  7.0
AI/automation pressure:            6.5
```

Calculate:

```text
score =
    job_availability * 0.25
  + graduate_availability * 0.20
  + competition * 0.20
  + economy * 0.15
  + it_demand * 0.10
  + ai_pressure * 0.10
```

Round to one decimal place.

### Important

The LLM must **not arbitrarily choose the final score**.

The calculation must be performed deterministically by Python.

The LLM can provide evidence and interpretation supporting each component.

---

# 21. Final Report Format

Generate the following structure:

```markdown
# 🇳🇿 NZ Economy & IT Graduate Weekly Intelligence Report

**Week: DD–DD Month YYYY**

## Executive Summary

- Major development 1
- Major development 2
- Major development 3
- Major development 4

## 🇳🇿 NZ Economy

### Key Indicators

[important current indicators and comparison]

### What Changed

[analysis]

## 💼 NZ Labour Market

[analysis]

## 💻 NZ IT Graduate Job Market

### Current Job-Market Signals

[data and evidence]

### Graduate / Entry-Level Situation

[analysis]

## 🌎 Global Context

[only relevant international developments]

## 📈 NZX / Business Signals

[relevant developments]

## 🎯 Personal Job Search Index

**X.X / 10**

Previous week: **X.X / 10**

Trend: **↑ / → / ↓**

### Why

[explanation]

## 🎓 What This Means for an IT Graduate

[personalised interpretation]

## ✅ Recommended Actions

1. ...
2. ...
3. ...
```

The report should be concise enough to read weekly.

Avoid turning it into a long news digest.

---

# 22. LLM Responsibilities

The LLM should primarily perform:

```text
information extraction
synthesis
prioritisation
interpretation
report writing
```

The LLM should NOT be trusted to independently invent:

```text
statistics
source URLs
historical values
scores
```

The final report-generation prompt should explicitly say:

```text
Use only the supplied evidence.

Do not invent facts, statistics, sources or URLs.

If information is missing, say that it is unavailable.

Clearly distinguish facts from interpretation and prediction.

Prioritise information relevant to an IT graduate seeking employment in New Zealand.

Do not include news simply because it is recent or interesting.
```

---

# 23. Output Files

Each weekly run should produce:

```text
reports/
└── 2026-W32.md
```

Optionally also:

```text
data/
└── weekly/
    └── 2026-W32.json
```

The JSON should contain the structured facts used to produce the report.

This allows future historical analysis without introducing a database.

---

# 24. CLI

The MVP only needs one command:

```bash
python main.py
```

This should execute the complete pipeline:

```text
Research
→ Extract
→ Validate
→ Compare
→ Analyse
→ Score
→ Generate
→ Save
```

Do not create multiple CLI commands unless they become necessary.

---

# 25. Error Handling

A failed source should not necessarily stop the entire report.

Example:

```text
Stats NZ       ✓
RBNZ           ✓
SEEK           ✓
LinkedIn       ✗
```

The script should continue if LinkedIn is unavailable.

Log the failure:

```text
[WARNING] LinkedIn data unavailable
```

The report should not fabricate replacement information.

---

# 26. Logging

Provide simple useful logs:

```text
[INFO] Starting weekly intelligence report
[INFO] Report period: 2026-08-03 → 2026-08-09

[INFO] Researching NZ economy
[INFO] Researching NZ labour market
[INFO] Researching IT graduate market
[INFO] Researching global context

[INFO] Extracted 25 facts
[INFO] Validated 23 facts
[INFO] Detected 6 significant changes

[INFO] Calculating Personal Job Search Index
[INFO] Job Search Index: 6.6/10

[INFO] Generating report
[INFO] Report saved: reports/2026-W32.md
```

---

# 27. Testing

The MVP should include basic tests for:

## Scoring

Test:

- weighted calculation;
- rounding;
- minimum/maximum values;
- missing inputs.

## Comparison

Test:

- increase;
- decrease;
- no change;
- missing previous value.

## Validation

Test:

- missing source;
- missing value;
- missing date;
- invalid data.

## Report

Test that the generated report contains all required sections.

Use mocked research data for tests.

Do not make automated tests dependent on live websites.

---

# 28. Future Scheduling

The script should be designed so that it can later be run automatically.

For example:

```text
Cron
GitHub Actions
Windows Task Scheduler
```

But scheduling is **not part of the core MVP**.

The only requirement is that:

```bash
python main.py
```

works reliably.

---

# 29. Development Strategy

Do not implement the entire system in one step.

Implement incrementally.

## Phase 1 — Foundation

Create:

```text
Python project
main.py
configuration
logging
basic data structures
report output directory
```

Make sure:

```bash
python main.py
```

runs successfully.

## Phase 2 — Research

Implement research for a small number of reliable sources first.

Start with approximately:

```text
Stats NZ
RBNZ
SEEK / labour-market source
```

Do not implement every source immediately.

## Phase 3 — Structured Evidence

Implement:

```text
web research
→ structured JSON facts
```

with validation.

## Phase 4 — Comparison

Implement:

```text
current week
vs
previous week
```

## Phase 5 — Job Search Index

Implement deterministic scoring in Python.

## Phase 6 — Report Generation

Use the LLM to generate the final Markdown report.

## Phase 7 — Testing and Refinement

Run the complete pipeline and compare the generated report with the desired weekly-report format.

Only after the MVP works should additional sources or features be considered.

---

# 30. Definition of Done

The MVP is complete when:

```bash
python main.py
```

successfully performs the complete workflow and produces:

```text
reports/YYYY-WXX.md
```

The generated report must:

- cover the NZ economy;
- cover the NZ labour market;
- cover the NZ IT graduate job market;
- include relevant global context;
- include relevant NZ technology/business signals;
- contain source-backed facts;
- distinguish current data from older data;
- compare against the previous week when possible;
- calculate a deterministic Personal Job Search Index;
- explain what the current environment means for an IT graduate;
- provide practical recommendations;
- continue operating when a non-critical source fails.

The system should be **simple enough for one developer to understand and modify easily**.

Do not optimise for scalability.

Do not build infrastructure for hypothetical future users.

Optimise for:

1. **Reliable information**
2. **Traceable evidence**
3. **Useful weekly analysis**
4. **Simple code**
5. **Easy maintenance**

---

# 31. Initial Instruction to the Coding Agent

Do NOT implement the entire specification immediately.

Start with **Phase 1 only**.

First:

1. Inspect this specification.
2. Propose the minimal project structure.
3. Create the Python project.
4. Create `main.py`.
5. Create configuration and logging.
6. Create the directories for data and reports.
7. Create minimal data models for weekly facts.
8. Create `.env.example`.
9. Create `README.md` with setup and execution instructions.
10. Make sure `python main.py` runs successfully.

Do not add a frontend, database, authentication, Docker, cloud infrastructure, or unnecessary abstractions.

After Phase 1 is complete, explain what was created and how it works before moving to Phase 2.