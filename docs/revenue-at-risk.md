# Revenue At Risk Dashboard

Phase 5 provides a unified monetary opportunity view over active Recovery Cases.
All amounts use integer minor units in the API and are formatted by currency in
the browser.

## Dashboard API

```http
GET /api/dashboard/summary
GET /api/dashboard/summary?merchant_id=<uuid>&top_limit=10
```

The response contains generation time, per-currency summaries, and ranked top
opportunities. `top_limit` accepts 1 through 50.

## Calculations

Revenue at Risk is the sum of `amount_at_risk` for nonterminal, unexpired cases.
Currencies are grouped separately and never converted or combined.

Expected Recoverable is calculated for cases whose latest persisted Recovery
Decision contains an explicit `action_scores.recovery_probability` value from 0
through 1:

```text
round(amount_at_risk * recovery_probability)
```

Cases without a valid probability contribute to Revenue at Risk and Active Cases,
but not Expected Recoverable. `estimated_cases` makes this coverage explicit. No
fallback probability is invented.

## Ranking

The initial engineering ranking is:

```text
priority = value_basis * (1 + elapsed_window_fraction)
```

`value_basis` is expected recoverable when estimated, otherwise amount at risk.
This keeps unscored monetary opportunities visible before the later rule and ML
phases exist. It is an internal queue heuristic, not an industry-standard formula.

Ties are resolved deterministically by amount and case ID. Expired cases are
persisted as `EXPIRED` before the snapshot is computed.

## Phase Boundary

Phase 5 reads decisions but does not generate them. Rule-based decisions, control
groups, action outcomes, and comparative baseline reports begin in Phase 6.
