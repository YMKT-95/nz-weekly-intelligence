# Provisional Scoring Policy — v1

The project supplies traceable information and transparent interpretations to help readers make their own decisions. A numerical index is a heuristic summary, not an objective measurement or probability of finding a job. Missing evidence is a valid outcome.

This policy documents the bounded Phase 5 implementation in `src/scoring.py`. Its formulas, source preferences, and age limits are initial engineering choices. They are not fitted to historical hiring outcomes, official statistical thresholds, or validated economic relationships. The code's `RULES`, `WEIGHTS`, and `LIMITATIONS` are authoritative; changing the policy requires reviewing this document and incrementing its version.

## Six components and completeness

The fixed weights are job availability 25%, graduate/entry-level availability 20%, competition 20%, economic conditions 15%, IT demand 10%, and automation pressure 10%. All component scores run from 0 to 10, with higher scores intended to represent more favourable conditions under the declared proxy.

The calculator validates exactly six components, finite numeric inputs within 0–10, and positive weights summing to 100%. Numeric strings and booleans are rejected. It calculates the weighted sum with decimal arithmetic and rounds the result to one decimal place using ROUND_HALF_UP. For example, a total of 5.25 becomes 5.3.

A missing component has `score: null`. The aggregate remains `overall_score: null` and `status: insufficient_evidence` unless all six components are scored. No zero, neutral value, previous-week value, or redistributed weight replaces missing evidence. A genuine observed zero growth rate can map to a neutral anchor; an unknown growth rate cannot.

`covered_weight_percent` is the sum of weights with scored components. It measures implemented evidence coverage, not confidence, reliability, accuracy, or a partial overall index. Even a complete future result remains a provisional heuristic until its rules are evaluated.

## Supported mappings

Each mapping uses only the selected accepted fact from the current evidence run. A rule requires the exact publisher, metric, percentage unit, comparison basis, category, adjustment, extraction method, national geography and aggregate scope. The most recent data period within that rule is considered. Conflicting latest values are not resolved by choosing an older value.

For every rule, the formula result is clipped to 0–10 and then rounded to two decimal places using ROUND_HALF_UP. The final index uses those stored component scores. Stored decimal precision is a computational choice, not a claim about measurement accuracy. Formula coefficients, age limit and source criteria are retained with each scored component.

### Job availability

First preference is the national SEEK monthly job-ad growth series, with explicit trend adjustment and a full calendar-month period:

```text
score = clamp(5 + monthly_growth_percent, 0, 10)
maximum data age = 75 days after period end
```

The anchors are -5% growth → 0, 0% → 5, +5% → 10. These describe job-ad momentum, not the number of available jobs.

If that rule has no eligible evidence, the fallback is MBIE's national unadjusted annual job-ad change for a three-month quarter:

```text
score = clamp(5 + 0.25 × annual_growth_percent, 0, 10)
maximum data age = 150 days after quarter end
```

The anchors are -20% annual growth → 0, 0% → 5, +20% → 10. The two publishers are not averaged and their monthly/annual rates are not treated as interchangeable. The fallback is explicitly recorded; switching the selected mapping prevents an index trend comparison. Failed preferred-rule checks remain in the component's issues.

Both are broad national proxies. Neither supplies graduate-specific vacancy evidence. The current live SEEK job-ad figure is rejected because of inconsistent periods, and MBIE collection is unavailable, so this component currently remains unscored.

### Competition

Use the national SEEK applications-per-ad month-on-month growth, its explicit lagged full-calendar-month period, and the currently retained `not_stated` adjustment:

```text
score = clamp(5 - 0.5 × monthly_applications_growth_percent, 0, 10)
maximum data age = 100 days after the applications data period ends
```

The anchors are -10% growth → 10, 0% → 5, +10% → 0. This represents a hypothesis about competition momentum. It does not establish how many applications each job receives, how competitive junior IT roles are, or whether growth has reversed. A positive growth rate that slows still means applications per ad are increasing.

### Economic conditions

Use the Stats NZ national unemployment-rate level for a three-month quarter, with the currently retained `not_stated` adjustment:

```text
score = clamp(13.75 - 1.25 × unemployment_rate_percent, 0, 10)
maximum data age = 150 days after quarter end
```

The anchors are unemployment 3% → 10, 7% → 5, 11% → 0. Values must be within the possible 0–100% source range. This is explicitly an unemployment proxy, not a comprehensive economic assessment. CPI is retained elsewhere as evidence but is not mechanically converted into a favourable/adverse score. The unemployed count and unemployment-rate change are not added as independent economic inputs.

### Components without implemented mappings

Graduate availability, IT demand, and automation pressure remain unavailable. We do not derive them from general unemployment, national job-ad growth, or AI mentions. Future mappings require suitable evidence, source support, a documented interpretation, and tests. The engine tests all six-component arithmetic using synthetic scores; that does not prove six-component live coverage.

## Freshness, quality and interpretation

Age is measured from the observation's period end to the evidence run's collection date, inclusive of the configured limit. Recollection, page updates and publication dates do not reset that age. The applications limit accounts for a lagged monthly measure; quarterly limits allow for reporting delay. These are provisional operational limits, not guarantees of freshness. Release-calendar-aware rules remain future work.

Source values and periods are validated upstream. Scoring additionally checks source semantics, expected period length, supported numerical range, latest-value conflicts, and data age. It retains the selected fact, its `/facts/<index>` pointer, original source evidence, evidence-file path/hash, selected rule, age, reasons, issues and limitations. Stale or conflicting candidate facts are retained as review evidence when a component is unavailable.

The scorer reads the accepted evidence file format; it does not re-fetch sources or redo extraction. Phase 4's review flags and labour direction are not scoring inputs. Repeated but age-eligible observations may support the same component score, without implying a new data release.

## Scoring history

The latest valid earlier canonical scoring file is selected. Current/future weeks and nested archives are ignored. Corrupt or inconsistent files are skipped with audit notes. A recent incomplete score is retained as the historical reference rather than skipped in favour of an older complete score.

Numerical index comparison requires both indices to be complete and to share the policy version, policy checksum, weights and selected component rules. Changes in source mapping, input definitions, older inputs, or same-period revisions prevent a new-period index delta. Repeated identical evidence produces `unchanged_evidence` with zero delta, which is not a claim of market stability.

The policy checksum includes formulas, source rules, age limits, weights, rounding, missing-data policy and limitations. It detects changed policy content even if a version increment was accidentally omitted. Historical results retain their original policy and component values; they are not silently recalculated.

## Output and completion boundary

Each successful scoring stage saves a weekly view at `data/weekly/scores/YYYY-WXX.json` and an immutable archive at `data/weekly/scores/runs/YYYY-WXX/<evidence-run-timestamp>.json`. Incomplete results are saved too, replacing an older complete weekly view if necessary. Archives are preserved. A scoring write failure leaves earlier evidence/comparison outputs intact and returns a nonzero command exit code; always inspect exit status before using an existing score file.

With at least one accepted fact, saving an honest incomplete score is a successful stage outcome. If collection/extraction yields no accepted facts, the existing command failure path remains in effect: previous evidence, comparison and scoring views may remain and the command exits nonzero.

Phase 5's engine can be implemented and tested with partial live coverage. Publishing the original six-component index still requires suitable evidence and rules for all six components. Report generation must expose these limits rather than presenting incomplete coverage as a complete MVP index.
