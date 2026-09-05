# Revenue Recovery Control Plane

## Submission and Demonstration Guide

## 1. Project Summary

Revenue Recovery Control Plane is an AI-assisted system for identifying money at
risk after failed or incomplete payments, organizing each opportunity as a
Recovery Case, estimating how recoverable that case is under different actions,
and measuring recovery strategies against a deterministic baseline.

The implemented prototype is complete through Phase 8 of the implementation
plan. It includes the application foundation, domain model, Razorpay Test Mode
adapter, secure webhook ingestion, Recovery Case engine, revenue-at-risk
dashboard, deterministic recovery baseline, synthetic counterfactual simulator,
and calibrated action-conditional ML models.

It does not yet connect model predictions to expected-value decisions, policy
approval, or automatic Razorpay execution. Those responsibilities begin in
Phases 9 through 11. The prototype therefore recommends and evaluates; it does
not move money or contact real customers.

## 2. Problem Being Solved

Payment systems expose several recoverable failure signals:

- a one-time payment fails
- an order remains unpaid
- a Payment Link is partially paid or expires with a remaining balance

A merchant needs more than a list of failures. The merchant needs to know:

1. How much revenue is currently at risk?
2. Which cases should be handled first?
3. Which intervention is most suitable for each case?
4. Did the intervention produce incremental recovery rather than merely coincide
   with a payment that would have happened anyway?

This project creates the data and decision foundation needed to answer those
questions while keeping provider execution behind explicit safety boundaries.

## 3. Implemented Scope

| Phase | Capability | Status |
| --- | --- | --- |
| 0 | FastAPI, Next.js, PostgreSQL, Redis, Docker and Alembic foundation | Complete |
| 1 | Domain schema and validated Recovery Case lifecycle | Complete |
| 2 | Bounded Razorpay Test Mode adapter | Complete |
| 3 | Verified, deduplicated webhook ingestion and reconciliation | Complete |
| 4 | Idempotent Recovery Case creation and terminal conditions | Complete |
| 5 | Revenue-at-risk aggregation and database-backed dashboard | Complete |
| 6 | Deterministic recovery baseline and control/treatment experiments | Complete |
| 7 | Reproducible synthetic counterfactual dataset | Complete |
| 8 | Calibrated action-conditional models and inference | Complete |
| 9-19 | EV ranking, guardrails, execution, measurement, explanation, audit UI and hardening | Not implemented |

## 4. System Architecture

```text
Razorpay Test Mode / synthetic demo signal
                 |
                 v
      FastAPI ingestion boundary
        | signature verification
        | event deduplication
        | provider reconciliation
                 v
          PostgreSQL domain state
        | merchant, customer, payment
        | order, payment link
        | recovery case and audit event
                 v
       Recovery opportunity services
        | revenue-at-risk aggregation
        | deterministic rule baseline
        | action-conditional ML inference
                 v
        Next.js operational dashboard
           polls API every 3 seconds

Redis is available for later queues, locks, and operational coordination.
Provider-specific behavior remains behind the PaymentGateway interface.
```

The project is a modular monolith. This keeps deployment simple while preserving
clear module boundaries between provider integration, domain logic, analytics,
rules, machine learning, and presentation.

## 5. End-to-End Application Flow

### Step 1: Receive a recovery signal

In the Razorpay path, the API receives a supported webhook such as
`payment.failed`, `payment.captured`, or a Payment Link state change. The API
verifies the HMAC-SHA256 signature over the untouched request body before parsing
or storing it.

The event ID is persisted behind a unique provider/event constraint. Duplicate
processed events return successfully without being processed twice. Supported
events are reconciled against current Razorpay state, so an old webhook cannot
overwrite newer provider state.

### Step 2: Create or update a Recovery Case

The Recovery Case engine checks merchant ownership, customer consent, source
state, amount due, and the recovery window. A case is unique by merchant, source
type, and source ID, which makes repeated scans and webhooks idempotent.

The amount at risk is calculated as:

- failed payment: failed amount capped by positive order amount due
- unpaid order: current order amount due
- Payment Link: total amount minus amount already paid

Cases can progress through assessment and action states, or terminate as
`RECOVERED`, `STOPPED`, `EXPIRED`, or `ESCALATED`. Terminal cases do not reopen
because of late events.

### Step 3: Compute the recovery opportunity view

`GET /api/dashboard/summary` reads active cases from PostgreSQL and computes:

- revenue at risk by currency
- expected recoverable amount when a valid probability exists
- active and estimated case counts
- an opportunity queue ranked by monetary value and recovery-window urgency

The frontend contains no hardcoded monetary totals. It polls this endpoint every
three seconds, so new database records become visible during the live demo.

### Step 4: Establish a deterministic baseline

Before claiming that AI improves anything, the system records a simple benchmark.
Eligible cases can be assigned to no-intervention control and rule-treatment
groups. Assignment uses deterministic hash ranking, making the requested group
sizes reproducible.

Treatment recommendations are persisted as decisions and pending actions. They
are not executed. Outcome reporting requires real reconciled captured-payment
evidence before a case can be counted as recovered.

### Step 5: Generate leakage-safe training data

The Phase 7 simulator creates two checksum-protected files:

- `features.csv`: information visible to a model at decision time
- `ground_truth.csv`: hidden potential outcomes for evaluation

The files share only `case_id`. Equal seeds and configurations produce identical
rows, IDs, manifests, and SHA-256 checksums. The results are synthetic and must
not be presented as production Razorpay performance.

### Step 6: Train action-conditional recovery models

Phase 8 trains four independent calibrated binary models:

- probability of recovery with no intervention
- probability of recovery with a recovery link
- probability of recovery with a payment-method update prompt
- probability of recovery after a delay

Numeric features pass through the preprocessing pipeline and categorical features
are one-hot encoded. Gradient-boosted classifiers learn nonlinear relationships,
and three-fold sigmoid calibration improves probability interpretation.

Customers, rather than individual rows, are split approximately 70/15/15 into
train, validation, and test sets. This prevents behavior from one customer from
appearing in both training and evaluation.

### Step 7: Evaluate and run inference

Evaluation records ROC-AUC, PR-AUC, Brier score, log loss, expected calibration
error, and outcome prevalence for every action model. The model artifact is
versioned from its training configuration and dataset hashes.

Inference accepts only the model-visible feature schema and emits:

```text
case_id
p_no_intervention
p_recovery_link
p_update_prompt
p_delay
```

No hidden outcome column enters the inference path.

## 6. Recovery Technique

### Deterministic rule technique

The versioned `rule-baseline-v1` applies these rules in order:

1. An unpaid order selects `RECOVERY_LINK`.
2. An existing Payment Link selects `DELAY` while that link remains recoverable.
3. A failed payment with a bank/gateway source or known transient reason selects
   `RECOVERY_LINK`.
4. An unknown or non-transient failed payment selects `STOP`.

This baseline is deliberately simple and explainable. It provides the benchmark
that an ML candidate must beat.

### ML recovery technique

The ML technique is action-conditional modeling. Instead of predicting one generic
"will recover" score, it estimates what may happen under each possible action.
This matters because the most recoverable customer is not automatically the
customer who benefits most from intervention.

For example:

```text
P(recovery | no intervention) = 0.40
P(recovery | recovery link)   = 0.68
P(recovery | update prompt)   = 0.51
P(recovery | delay)           = 0.44
```

This suggests that a recovery link has the highest modeled recovery probability.
It is not yet permission to execute. Phase 9 must account for intervention cost
and expected value, and Phase 10 must apply deterministic policy gates first.

### Reference synthetic result

For the fixed 5,000-case simulator dataset with seed 42:

- deterministic rule recovery rate: 35.98%
- model-selected recovery rate: 46.22%
- absolute synthetic lift: 10.24 percentage points
- test ROC-AUC by action: 0.6708 to 0.7454
- expected calibration error by action: 0.0224 to 0.0331
- oracle action-selection accuracy: 86.17%

These figures prove behavior on the defined synthetic benchmark only. They are
not production claims.

## 7. Safety and Correctness Controls

- Razorpay live keys are rejected by default; the adapter is Test Mode only.
- No generic failed-payment retry endpoint is invented.
- Webhook signatures are checked before JSON parsing.
- Provider event IDs and Recovery Case source keys enforce idempotency.
- Current provider state is reconciled before local state changes.
- Merchant ownership must agree across webhook and local resources.
- Opted-out customers, inactive merchants, expired windows, paid resources, and
  cancelled links stop or terminate recovery.
- Model output is a recommendation, never execution authority.
- Hidden counterfactual truth is physically separated from model features.
- Model artifacts have versions and SHA-256 checksums.
- Recovered baseline outcomes require captured-payment evidence.

The intended future execution chain is:

```text
ML recommendation
       |
       v
Expected-value selection
       |
       v
Deterministic policy and guardrails
       |
       v
Validated Razorpay Test Mode action
       |
       v
Observed and audited outcome
```

Only the recommendation and evaluation portions are implemented today.

## 8. Main Data Entities

| Entity | Purpose |
| --- | --- |
| Merchant | Razorpay account ownership and operating status |
| Customer | Merchant-scoped customer identity and consent |
| Order | Current order state and amount due |
| Payment | Payment state and normalized failure information |
| PaymentLink | Link state, amount paid, and remaining balance |
| RecoveryCase | One bounded revenue-at-risk opportunity |
| RecoveryFeature | Versioned model inputs associated with a case |
| RecoveryDecision | Model/rule recommendation and explanation snapshot |
| RecoveryAction | Pending or executed intervention record |
| ActionOutcome | Observed recovery result and recovered amount |
| Experiment | Control/treatment benchmark definition |
| ExperimentAssignment | Stable case-to-group assignment |
| AuditEvent | Append-only evidence for important state changes |
| WebhookEvent | Verified, deduplicated provider event record |

## 9. Important API Endpoints

| Method and path | Purpose |
| --- | --- |
| `GET /health` | Service liveness and version |
| `GET /health/ready` | PostgreSQL and Redis readiness |
| `POST /webhooks/razorpay` | Verified Razorpay webhook ingestion |
| `POST /api/cases` | Create a Recovery Case for validation/demo use |
| `GET /api/cases` | List Recovery Cases |
| `GET /api/cases?active_only=true` | List current active opportunities |
| `POST /api/cases/scan-unpaid-orders` | Run deterministic unpaid-order detection |
| `PATCH /api/cases/{case_id}/status` | Apply a validated lifecycle transition |
| `GET /api/dashboard/summary` | Compute dashboard metrics and queue |
| `POST /api/baselines/batches` | Assign and evaluate a rule-baseline batch |
| `GET /api/baselines/{experiment_id}/report` | View baseline groups and outcomes |

Interactive API documentation is available at `http://localhost:8000/docs`.

## 10. Run the Project

From the repository root:

```powershell
docker compose up --detach api web
Invoke-RestMethod http://localhost:8000/health/ready | ConvertTo-Json -Depth 4
```

Open:

- dashboard: http://localhost:3000
- API documentation: http://localhost:8000/docs
- readiness response: http://localhost:8000/health/ready

If a fresh database contains no merchant-backed case, seed the development data:

```powershell
docker compose exec api python -m app.db.seed
```

## 11. Real-Time Prototype Demonstration

The prototype uses three-second polling rather than WebSockets. This is a
near-real-time operational dashboard backed by the real API and PostgreSQL. The
event generator supplies labeled synthetic inputs so no real customer or payment
is affected.

### Recommended screen layout

1. Keep `http://localhost:3000` visible on the left.
2. Keep a PowerShell terminal visible on the right.
3. Increase browser zoom only enough for the totals and queue to remain readable.
4. Start recording before running the feed command.

### Run the live feed

```powershell
powershell -ExecutionPolicy Bypass -File scripts/demo-live-feed.ps1 -Count 9 -IntervalSeconds 2 -RunBaseline
```

What happens:

1. The script reads an existing merchant through `GET /api/cases`.
2. It posts nine uniquely identified synthetic signals through `POST /api/cases`.
3. Signals rotate through `ORDER`, `PAYMENT_LINK`, and `PAYMENT` case types.
4. PostgreSQL stores each new case.
5. The dashboard polls the summary API and visibly updates totals and rows.
6. The script runs the deterministic baseline with all demo cases in treatment.
7. The terminal prints an action distribution containing recovery link, delay,
   and stop recommendations.

The script creates recommendations only. It does not invoke Razorpay or send a
message to a customer.

### Demonstrate model training

```powershell
python -m simulator --cases 5000 --seed 42 --output-dir artifacts/demo-simulator
python -m ml --dataset-dir artifacts/demo-simulator --output-dir artifacts/demo-model --seed 42
```

Point out the model version, split sizes, per-action metrics, and baseline
comparison printed by the training command.

### Demonstrate inference

```powershell
python -m ml.inference --model artifacts/demo-model/model.joblib --input artifacts/demo-simulator/features.csv --output artifacts/demo-model/predictions.csv
Get-Content artifacts/demo-model/predictions.csv -TotalCount 4
```

Point out that output contains one case identifier and four probabilities, but no
hidden outcome fields.

## 12. Suggested Screen-Recording Script

### 0:00 - Introduce the problem

Say:

> Failed payments are not equally recoverable, and not every recovery should use
> the same intervention. This project turns payment failure signals into auditable
> Recovery Cases, computes revenue at risk, benchmarks deterministic recovery
> rules, and estimates recovery probability under four possible actions.

### 0:40 - Show architecture and readiness

Open the API readiness endpoint and say:

> The prototype runs as a modular monolith with FastAPI, Next.js, PostgreSQL, and
> Redis. PostgreSQL is the durable source of truth. The provider integration is
> behind a typed gateway so decision logic does not depend directly on Razorpay
> payloads.

### 1:20 - Show live dashboard updates

Run the live-feed command and say:

> These are synthetic demo signals, but they enter through the real Recovery Case
> API and are persisted in PostgreSQL. The frontend has no static revenue totals;
> it polls the computed dashboard endpoint every three seconds. We can see revenue
> at risk and the recovery queue change as each case arrives.

### 2:30 - Explain deterministic recovery

When the action distribution appears, say:

> The baseline gives unpaid orders a recovery link, delays when an existing
> Payment Link is still usable, gives transient payment failures a recovery link,
> and stops unknown or unsafe failures. These are recommendations and pending
> actions only. No provider action is executed in this phase.

### 3:30 - Explain the ML model

Show `metadata.json` or run training and say:

> The ML layer estimates four calibrated probabilities, one for each possible
> action. The split is grouped by customer, identifiers are removed, and hidden
> counterfactual outcomes are kept outside the feature file. On the fixed synthetic
> benchmark, model-selected actions improve recovery by 10.24 percentage points
> over the deterministic baseline.

### 5:00 - Show inference safety

Show `predictions.csv` and say:

> Inference emits only the case ID and four action probabilities. A probability is
> not permission to execute. Expected-value ranking and deterministic policy gates
> must approve an action before a provider adapter can run it.

### 5:45 - Close honestly

Say:

> The project is complete through the ML recommendation phase. The implemented
> prototype proves secure ingestion, idempotent case creation, live aggregation,
> baseline measurement, reproducible model training, and bounded inference. Online
> next-best-action persistence, guardrails, execution, and causal measurement are
> the next planned phases.

## 13. Verification

Run the full automated suite:

```powershell
python -m pytest -q
```

Current acceptance evidence:

- 66 automated tests pass
- Next.js production build passes
- API and web container builds pass
- PostgreSQL and Redis readiness checks pass
- containerized simulator, training, and inference smoke test passes
- model inference writes the expected number of schema-valid rows
- hidden-column leakage tests reject invalid datasets

The test suite currently emits one Starlette `httpx` deprecation warning. It does
not represent a failing test.

## 14. Common Questions and Answers

### Is the dashboard static?

No. It fetches `GET /api/dashboard/summary`, which computes values from current
PostgreSQL records. It polls every three seconds. The initial development record
is seeded, and the demonstration feed creates additional synthetic records through
the API.

### Is the live demonstration using real Razorpay payments?

No. The demo feed is synthetic and labeled as such. The Razorpay adapter and
webhook security boundary are implemented for Test Mode, but the demonstration
does not contact customers or execute payment actions.

### Why are some dashboard probabilities shown as Pending?

The Phase 5 dashboard displays a probability only when a valid persisted decision
contains one. Phase 8 currently provides file-based model inference. Persisting
online ML decisions belongs to Phase 9, so the UI does not fabricate probabilities
for cases that have not passed that step.

### Why use four models instead of one recovery score?

The business question is not only whether a case will recover. It is which action
has the best expected result compared with doing nothing. Action-conditional
probabilities provide that comparison.

### Why calibrate probabilities?

Later expected-value logic multiplies probability by money and subtracts action
cost. Poorly calibrated confidence would produce misleading financial rankings.

### How is data leakage prevented?

Visible features and hidden potential outcomes are separate files with exact
schemas and checksums. Identifiers are removed from model inputs, customers cannot
cross dataset splits, and tests reject hidden columns in the visible feature file.

### How are duplicate webhooks handled?

The provider and event ID form a unique persistence boundary. Already processed
events return success without repeating reconciliation or case creation.

### Why not retry a failed payment directly?

The project does not assume a generic Razorpay failed-payment retry endpoint.
Supported recovery uses a Payment Link flow through the bounded adapter.

### What remains before production use?

Expected-value decision persistence, deterministic guardrails, real Test Mode
execution orchestration, incremental measurement, explanation and investigation
UI, failure hardening, authentication, authorization, secret management,
observability, and production security review remain planned work.

## 15. Presentation Rules

Use these phrases:

- "synthetic live demo signals"
- "database-backed dashboard"
- "near-real-time three-second polling"
- "action-conditional recovery probability"
- "recommendation, not execution authority"
- "Razorpay Test Mode boundary"
- "synthetic benchmark result"

Avoid these claims:

- "the complete production system is finished"
- "the model recovered real merchant revenue"
- "the AI automatically retries failed payments"
- "the dashboard is streaming through WebSockets"
- "the measured synthetic lift is guaranteed in production"

