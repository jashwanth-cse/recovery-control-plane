# Phase Status

## Phase 0 - Repository & Architecture Foundation

Status: PASS

Acceptance criteria:

- `docker compose up` starts PostgreSQL, Redis, API, and web services.
- Backend health endpoint works.
- Frontend loads.
- Database migration executes.
- Tests run.

Validated on 2026-08-30 with alternate host ports because local port 8000 was already allocated:

- `python -m pytest`
- `pnpm --filter @recovery-control-plane/web build`
- `API_PORT=18000 WEB_PORT=13000 NEXT_PUBLIC_API_BASE_URL=http://localhost:18000 docker compose up --build --detach`
- `GET http://localhost:18000/health`
- `GET http://localhost:18000/health/ready`
- `GET http://localhost:13000`
- `select version_num from alembic_version`
- `select component, status from foundation_status`

## Phase 1 - Domain Model & Database

Status: PASS

Implemented:

- Domain enums and Recovery Case lifecycle rules.
- PostgreSQL schema migration for the conceptual MVP entities.
- Recovery Case repository with create, get, list, and transition behavior.
- Narrow Recovery Case API for Phase 1 validation.
- Idempotent development seed command.
- Unit tests for core lifecycle transitions and repository behavior.

Acceptance criteria:

- Can create/update/query a Recovery Case.
- Invalid state transitions are rejected.
- Tests cover core transitions.

Validated on 2026-09-01:

- `python -m pytest`
- `python -m alembic heads`
- `python -m alembic upgrade head --sql`
- `API_PORT=18000 WEB_PORT=13000 NEXT_PUBLIC_API_BASE_URL=http://localhost:18000 docker compose up --build --detach`
- `GET http://localhost:18000/health`
- `GET http://localhost:18000/health/ready`
- `python -m app.db.seed` inside the API container
- `GET http://localhost:18000/api/cases`
- `POST http://localhost:18000/api/cases`
- `GET http://localhost:18000/api/cases/{case_id}`
- `PATCH http://localhost:18000/api/cases/{case_id}/status`
- Invalid transition `ELIGIBILITY_CHECK -> ACTION_PENDING` returned `422`

## Phase 2 - Razorpay Integration Layer

Status: PASS

Implemented:

- Provider-neutral `PaymentGateway` protocol.
- Secret-safe Razorpay Test Mode configuration and Basic Auth client.
- Typed contracts for order, payment, Payment Link, and notification data.
- Verified order and payment reads.
- Verified Payment Link creation, SMS/email notification or resend, and cancellation.
- Resource ID and outbound request validation.
- Normalized configuration, transport, authentication, rate-limit, service, API,
  and provider-response errors.
- Mock-transport contract tests that make no external calls.

Acceptance criteria:

- Can fetch an order through the adapter.
- Can fetch a payment through the adapter.
- Can create a recovery Payment Link through the adapter.
- Can notify or resend a link by the officially supported `sms` and `email` media.
- Can cancel a recovery Payment Link.
- Business-facing code depends on a gateway protocol rather than raw HTTP.

Validated on 2026-09-01:

- Official Razorpay API reference reviewed for every implemented endpoint.
- `python -m pytest` (`27 passed`, one pre-existing Starlette deprecation warning).
- `python -m compileall -q apps/api/app apps/api/tests`.
- `pnpm --filter @recovery-control-plane/web build`.
- `docker compose config --quiet`.
- `docker compose build api`.
- Disposable API container started without Razorpay credentials and reported
  version `0.3.0-phase2`.
- `git diff --check`.

Known limitation:

- Real Razorpay Test Mode calls were not executed because merchant credentials
  and existing test resources are intentionally not stored in the repository.
  Contract tests validate the exact HTTP boundary using injected mock transport.

## Phase 3 - Webhook Ingestion

Status: PASS

Implemented:

- `POST /webhooks/razorpay` ingestion endpoint.
- HMAC-SHA256 verification over the untouched request body.
- Current and previous webhook secrets for rotation-safe retries.
- Durable `webhook_events` persistence with a unique provider/event ID boundary.
- Explicit processing states and retry attempt tracking.
- Routing for payment failed, authorized, and captured events.
- Routing for Payment Link paid, partially paid, cancelled, and expired events.
- Correlation to existing payment-, order-, and Payment Link-backed Recovery Cases.
- Current-state reconciliation through typed Razorpay API reads.
- Minimized reconciliation snapshots without customer contact data.
- Structured duplicate, ignored, reconciled, and failed event logs.

Acceptance criteria:

- Repeated delivery of a processed event does not repeat reconciliation or invoke
  a business action.
- Failed reconciliation can retry under the same event ID.
- Critical payment, order, and Payment Link states reconcile through the adapter.
- Out-of-order delivery cannot regress local state from captured/paid to failed.
- Invalid signatures are rejected before parsing or persistence.

Validated on 2026-09-02:

- Official Razorpay webhook validation, idempotency, ordering, payment-event, and
  Payment Link event references reviewed.
- `python -m pytest` (`43 passed`, one pre-existing Starlette deprecation warning).
- Focused signature, endpoint, duplicate, retry, all-event routing, correlation,
  and out-of-order tests.
- `python -m compileall -q apps/api/app apps/api/tests`.
- `python -m alembic heads` returned `0003_webhook_events (head)`.
- `python -m alembic upgrade head --sql` succeeded.
- Migration `0003_webhook_events` applied to PostgreSQL.
- PostgreSQL confirmed the table and `uq_webhook_events_provider_event_id`.
- `docker compose config --quiet`.
- `docker compose build api`.
- Disposable API container reported version `0.4.0-phase3`.
- `pnpm --filter @recovery-control-plane/web build`.
- `git diff --check`.

Known limitations:

- No real Razorpay Test Mode webhook was delivered because merchant credentials
  and a public callback URL are not available in the repository environment.
- Reconciliation is synchronous in Phase 3. Durable background jobs and stale
  processing-lease recovery remain hardening work for later phases.
- Phase 3 correlates existing cases only; case creation begins in Phase 4.

## Phase 4 - Recovery Case Engine

Status: PASS

Implemented:

- Idempotent failed-payment Recovery Case creation from reconciled provider state.
- Deterministic scans for old `created` or `attempted` orders with a positive
  amount due.
- Payment Link correlation and remaining-balance case creation.
- Merchant-to-Razorpay account mapping with cross-account ownership rejection.
- Source-specific amount-at-risk calculation.
- Configurable recovery windows and persisted expiration.
- Stop/recovery conditions for merchant state, consent, paid resources, and
  cancelled links.
- Append-only creation and lifecycle audit events.
- Dashboard-ready active-case filtering through `GET /api/cases?active_only=true`.

Acceptance criteria:

- A current failed payment creates one persistent Recovery Case.
- An eligible unpaid order or unpaid Payment Link creates one persistent case.
- Duplicate events and scans do not create duplicate cases.
- Active cases can be queried by all merchants or one merchant.
- Expired and stopped cases are persisted and excluded from active results.

Validated on 2026-09-02:

- `python -m pytest -q` (`52 passed`, one pre-existing Starlette deprecation
  warning).
- Focused Recovery Case engine and webhook integration suite (`24 passed`).
- `python -m compileall -q apps/api/app apps/api/tests`.
- `python -m alembic heads` returned `0004_recovery_case_engine (head)`.
- `python -m alembic upgrade head --sql` succeeded.
- Migration `0004_recovery_case_engine` applied to PostgreSQL.
- PostgreSQL confirmed the account mapping, Payment Link paid amount, unique
  account constraint, and nonnegative paid-amount constraint.
- `docker compose config --quiet`.
- `docker compose build api`.
- Disposable API container reported version `0.5.0-phase4`.
- `pnpm --filter @recovery-control-plane/web build`.
- `git diff --check`.

Known limitations:

- The unpaid-order scan is an explicit idempotent API operation; durable scheduling
  belongs to later operational hardening.
- Real Razorpay Test Mode events were not delivered because credentials and a
  public webhook callback are not stored in the repository.
- Revenue-at-risk aggregation, expected recoverable value, and ranking begin in
  Phase 5 and were intentionally not implemented here.

## Phase 5 - Revenue-at-Risk Aggregator

Status: PASS

Implemented:

- Currency-separated Revenue at Risk, Expected Recoverable, and active-case
  aggregation.
- Latest persisted decision probability selection with estimate-coverage counts.
- Deterministic expected-value and recovery-window urgency ranking.
- Dashboard summary API with merchant filtering and bounded top-result limits.
- Initial operational dashboard backed entirely by the summary API.
- Loading, disconnected, empty, multi-currency, desktop, and mobile UI states.

Acceptance criteria:

- Dashboard displays computed Revenue at Risk, Expected Recoverable, Active Cases,
  and Top Opportunities.
- No frontend metric is hard-coded.
- Currency totals are never combined without conversion.
- Cases without a probability remain visibly unestimated.

Validated on 2026-09-02:

- `python -m pytest -q` (`54 passed`, one pre-existing Starlette deprecation
  warning).
- Focused dashboard, Recovery Case, and health suite (`12 passed`).
- `python -m compileall -q apps/api/app apps/api/tests`.
- `pnpm --filter @recovery-control-plane/web build`.
- `docker compose up --build --detach` on alternate ports `18000` and `13000`.
- PostgreSQL-backed API reported version `0.6.0-phase5` and returned two active
  seeded opportunities with computed INR totals.
- Headless Edge render checks at 1440x1000 and 390x844.
- `git diff --check`.

Known limitations:

- Expected Recoverable is zero until a later phase persists valid decision
  probabilities; estimate coverage is returned and displayed to avoid false
  precision.
- Phase 5 ranks opportunities but does not select or execute actions.
- Rule baseline and control/treatment comparison begin in Phase 6.

## Phase 6 - Rule-Based Recovery Baseline

Status: PASS

Implemented:

- Versioned deterministic rules for unpaid orders, existing Payment Links,
  transient payment failures, and unknown/non-transient failures.
- Exact hash-ranked control/treatment allocation for eligible active cases.
- No-intervention control cases with no generated decision or action.
- Treatment Recovery Decisions and pending Recovery Actions with policy explicitly
  marked `NOT_RUN`.
- Idempotent action outcome records with captured-payment evidence for recovery.
- Intent-to-treat baseline reports with group counts, recovery rates, rate lift,
  outcome coverage, and action distribution.
- Unique action-outcome database boundary.

Acceptance criteria:

- A batch can compare no intervention with rule-based recovery.
- Control cases receive no intervention record.
- Treatment cases receive one deterministic recommendation and pending action.
- Observed action outcomes are persistent and idempotent.
- Reports calculate both group recovery rates from stored state.
- No Razorpay action is executed by the baseline.

Validated on 2026-09-02:

- `python -m pytest -q` (`58 passed`, one pre-existing Starlette deprecation
  warning).
- Focused rule baseline and dashboard suite (`6 passed`).
- `python -m compileall -q apps/api/app apps/api/tests`.
- `python -m alembic heads` returned `0005_rule_baseline (head)`.
- `python -m alembic upgrade head --sql` succeeded.
- `docker compose config --quiet`.
- Migration `0005_rule_baseline` applied to PostgreSQL.
- PostgreSQL confirmed `uq_action_outcomes_action_id`.
- Containerized API reported version `0.7.0-phase6`.
- A PostgreSQL-backed 50/50 batch assigned one control and one treatment case.
- Database inspection confirmed zero control actions and one pending treatment
  action with policy evaluation `NOT_RUN`.
- The live comparison report returned both group rates and computed rate lift.
- `git diff --check`.

## Phase 7 - Synthetic Data Simulator

Status: PASS

Implemented:

- Seeded synthetic customer profiles with tenure, history, engagement, and
  available payment methods.
- Synthetic payments with bounded long-tail amounts and varied methods.
- Weighted failure profiles, attempt counts, and case ages.
- Correlated potential outcomes for no intervention, recovery link, update prompt,
  and delay.
- Separate model-visible and evaluation-only CSV files joined only by case ID.
- Versioned checksum manifest and deterministic UUIDv5 identifiers.
- One-command CLI supporting up to one million requested cases.

Acceptance criteria:

- One command generates thousands of synthetic cases.
- Equal version, seed, and case count produce byte-identical datasets.
- Different seeds produce different data.
- Hidden counterfactual fields never appear in the model-visible schema.
- Customer, payment, failure, history, age, and outcome values vary.

Validated on 2026-09-02:

- Focused simulator property suite (`4 passed`).
- `python -m simulator --cases 5000 --seed 42 --output-dir
  artifacts/simulator-phase7` generated 5,000 cases and 1,667 customers.
- Generated feature and hidden files were approximately 865 KB and 405 KB.
- Manifest SHA-256 values matched both generated files.
- Feature and ground-truth headers shared only `case_id`.
- Full `python -m pytest -q` suite passed (`62 passed`, one pre-existing
  Starlette deprecation warning).
- `python -m compileall -q apps/api/app apps/api/tests simulator tests`.
- `python -m alembic heads` returned `0005_rule_baseline (head)`.
- `docker compose config --quiet`.
- API container image built with the simulator package.
- A disposable API container generated the same 5,000-case SHA-256 hashes as the
  host run.
- Packaged API reported version `0.8.0-phase7`.
- `git diff --check`.
