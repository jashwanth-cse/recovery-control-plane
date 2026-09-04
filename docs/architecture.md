# Architecture

## Product Goal

Revenue Recovery Control Plane helps Razorpay merchants identify revenue at risk, choose the best permitted recovery intervention, execute supported actions through Razorpay Test Mode, and measure incremental recovery rather than only gross recovered revenue.

## Locked MVP Scope

In scope for the MVP:

- Failed one-time payments
- Abandoned or unpaid order recovery
- Payment-link recovery
- Razorpay Test Mode webhooks and payment/order/payment-link reads or actions where officially supported
- Recoverability scoring, next-best-action, expected value, policy gates, auditability, and evaluation

Out of scope unless explicitly promoted later:

- Live money movement
- Direct retry of failed payment objects
- Voice, Hinglish, mandates, full subscriptions, full B2B collections, and broad CRM functionality
- Kubernetes or microservices solely for appearance

## Repository Shape

```text
apps/api        FastAPI application
apps/web        Next.js application
migrations      Alembic migrations
packages        Future shared domain, policy, Razorpay, and common packages
services        Future recovery, experiment, simulation, and ML modules
tests           Cross-cutting test suites
docs            Architecture and implementation notes
```

The initial system is a modular monolith. Later phases should keep Razorpay-specific details behind an adapter and keep payment execution separate from decision logic.

## Phase 0 Runtime

```text
Browser
  ↓
Next.js web app
  ↓
FastAPI API
  ├─ PostgreSQL
  └─ Redis
```

The API exposes:

- `GET /health` for liveness
- `GET /health/live` for liveness aliases used by infrastructure
- `GET /health/ready` for dependency readiness checks
- `GET /api/cases` for Recovery Case listing
- `GET /api/cases/{case_id}` for Recovery Case lookup
- `POST /api/cases` for direct Phase 1 Recovery Case creation
- `POST /api/cases/scan-unpaid-orders` for deterministic unpaid-order detection
- `GET /api/cases?active_only=true` for dashboard-ready active cases
- `GET /api/dashboard/summary` for computed monetary metrics and opportunities
- `POST /api/baselines/batches` for control/treatment rule benchmark assignment
- `GET /api/baselines/{experiment_id}/report` for baseline comparison
- `PATCH /api/cases/{case_id}/status` for validated lifecycle transitions
- `POST /webhooks/razorpay` for verified Razorpay event ingestion

## Phase 1 Domain Model

The Phase 1 schema implements the conceptual tables from the plan:

- `merchants`
- `customers`
- `orders`
- `payments`
- `payment_links`
- `recovery_cases`
- `recovery_features`
- `recovery_decisions`
- `recovery_actions`
- `action_outcomes`
- `experiments`
- `experiment_assignments`
- `audit_events`

Recovery Case lifecycle rules live in `app.domain.recovery_case`. Application code should use these centralized transitions instead of scattering status strings.

## Phase 2 Razorpay Boundary

```text
Application service
      ↓
PaymentGateway protocol
      ↓
RazorpayPaymentGateway
      ↓
RazorpayClient
      ↓
Verified Razorpay v1 endpoint
```

The provider-neutral gateway exposes only order/payment reads and Payment Link
create, notification/resend, and cancellation. Typed request and response models
prevent raw provider payloads from leaking into business logic. HTTP transport is
injectable for contract tests, and provider failures are normalized before they
cross the integration boundary.

The adapter factory rejects missing credentials and live-mode keys. No adapter
operation is automatically invoked at startup, and Phase 2 adds no unrestricted
execution API.

## Phase 3 Webhook Ingestion

```text
Raw webhook request
      ↓
HMAC-SHA256 signature verification
      ↓
Validated event envelope
      ↓
Unique provider/event ID persistence
      ↓
Supported event router
      ↓
Razorpay API reconciliation
      ↓
Existing resource sync + case correlation
```

`webhook_events` stores the verified event envelope, processing status, attempt
count, optional Recovery Case correlation, and a minimized reconciliation
snapshot. The unique `(provider, event_id)` constraint is the concurrency-safe
deduplication boundary.

Processed, ignored, or currently processing duplicates return success without
running reconciliation again. Failed reconciliation returns a non-2xx response
and the same event ID may safely retry provider reads. Out-of-order events update
local resources from current Razorpay API state rather than trusting the older
webhook snapshot.

## Phase 4 Recovery Case Engine

```text
Reconciled Razorpay state / unpaid-order scan
      ↓
Merchant ownership + eligibility checks
      ↓
Idempotent source-backed Recovery Case
      ↓
Amount at risk + bounded recovery window
      ↓
Stop/recovery/expiration transitions + audit event
```

Failed payments use the lesser of the failed payment amount and positive order
amount due. Partially paid or expired Payment Links use their remaining balance,
and eligible old orders use `amount_due`. The unique merchant/source constraint
is the durable case idempotency boundary.

Recovery windows default to 14 days. Cases stop for inactive merchants, opted-out
customers, or cancelled links; paid resources recover linked cases; overdue cases
expire. Terminal cases never reopen when older events arrive. Account IDs and
known local resource ownership must agree before a webhook can create resources or
cases for a merchant.

## Phase 5 Revenue-At-Risk Aggregation

The dashboard aggregator reads active Recovery Cases and each case's latest
persisted Recovery Decision. It groups monetary totals by currency, calculates an
expected recoverable amount only when a valid probability is present, and ranks
opportunities using expected amount and remaining-window urgency. Unscored cases
use amount and urgency for queue placement but remain visibly unestimated.

Aggregation is computed on request from database state; the frontend contains no
metric constants. Phase 5 does not create decisions or claim recovered revenue.

## Phase 6 Rule Baseline

The deterministic baseline assigns eligible cases to an exact no-intervention
control share and a rule-treatment share. Control creates no action. Treatment
stores a versioned decision and pending action while leaving policy evaluation as
`NOT_RUN`, preserving the policy-before-execution boundary.

Observed recovered outcomes require an existing captured payment owned by the
case merchant. Reports compare cumulative recovery rates across all assigned cases
and expose action distribution without claiming causal incrementality.

## Phase 7 Synthetic Simulator

The standalone `simulator` package generates versioned CSV datasets without
database or provider dependencies. A local `random.Random` instance, UUIDv5 IDs,
canonical CSV formatting, and a checksum manifest make equal configurations
byte-reproducible.

`features.csv` contains observed customer, payment, failure, age, and history
fields. `ground_truth.csv` contains potential outcomes and latent probabilities;
`case_id` is their only shared field. This physical boundary is the first defense
against model leakage in Phase 8.

## Phase 8 Action-Conditional Model

The `ml` package verifies the Phase 7 manifest and schemas, removes all identifiers
from model inputs, and splits rows by customer. Four independent gradient-boosted
classifiers estimate action-conditional probabilities and use cross-validated
sigmoid calibration.

The serialized artifact contains preprocessing and estimators only. Metadata binds
the artifact to dataset hashes, configuration, split sizes, metrics, and model
version. Hidden potential outcomes remain outside the artifact and inference path.

## Financial Safety Model

No LLM or model may execute arbitrary financial actions. The required sequence is:

```text
AI/ML recommendation
        ↓
Deterministic policy / guardrail validation
        ↓
Validated action
        ↓
Razorpay adapter
        ↓
Execution
```

Blocked, duplicate, unsafe, unsupported, expired, or unauthorized actions must stop or escalate in later phases.

## Razorpay Constraint

The implementation must not invent a generic `POST /payments/{id}/retry` capability. Failed one-time payments should be recovered through a supported Payment Link recovery flow when the Razorpay adapter is implemented.

## Evaluation Model

Later phases must distinguish:

- Gross recovered revenue
- Incremental recovered revenue
- Net incremental recovered revenue after intervention costs

Synthetic evaluation must keep hidden counterfactual ground truth separate from model-visible features.
