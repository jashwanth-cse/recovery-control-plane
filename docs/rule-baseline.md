# Rule-Based Recovery Baseline

Phase 6 provides a deterministic benchmark for comparing no intervention with a
simple rule-selected recovery strategy. It records recommendations and observed
outcomes but never calls Razorpay or executes a financial action.

## Rules

The versioned `rule-baseline-v1` table is evaluated in order:

1. Unpaid order cases select `RECOVERY_LINK`.
2. Existing Payment Link cases select `DELAY`.
3. Failed payments with a bank/gateway source or a known transient reason select
   `RECOVERY_LINK`.
4. Unknown or non-transient payment failures select `STOP`.

These are project benchmark rules, not Razorpay recommendations. The selected
action is stored with a rule-match score, not a recovery probability. Therefore,
rule decisions do not create false Expected Recoverable estimates on the Phase 5
dashboard.

## Run A Batch

```http
POST /api/baselines/batches
Content-Type: application/json

{
  "merchant_id": "<uuid>",
  "name": "Rules vs no intervention",
  "control_percentage": 50
}
```

Only active, unassigned cases in pre-decision states are eligible. Cases are
hash-ranked and assigned to an exact control share. For samples of at least two
and percentages between 0 and 100, both groups receive at least one case.

Control cases receive no decision or action. Treatment cases receive a
`RecoveryDecision`, a pending `RecoveryAction`, and advance to `DECISION_READY`.
The action's policy state is explicitly `NOT_RUN`; Phase 6 does not bypass the
later policy and execution phases.

## Record An Observed Outcome

```http
POST /api/baselines/actions/<action_id>/outcomes
Content-Type: application/json

{
  "outcome": "RECOVERED",
  "razorpay_payment_id": "pay_..."
}
```

Supported outcomes are `RECOVERED` and `NOT_RECOVERED`. A recovered observation
requires a matching, locally reconciled captured payment owned by the same
merchant; its actual payment amount is recorded. Non-recovered observations
cannot reference a payment. One outcome is allowed per action, and identical
retries are idempotent.

## Compare Groups

```http
GET /api/baselines/<experiment_id>/report
```

The report returns assigned and recovered case counts, cumulative recovery rates,
treatment-minus-control rate lift, recorded treatment outcomes, and treatment
action distribution. Recovery rates use all assigned cases as the denominator,
preserving an intent-to-treat comparison.

Synthetic generation, model comparison, real action execution, and causal
incrementality belong to later phases.
