# Revenue Recovery Control Plane

Revenue Recovery Control Plane is an AI-assisted decision and measurement layer for Razorpay merchants. It is intended to unify revenue-at-risk, recommend economically sensible recovery interventions, gate every financial action through deterministic policy, execute only supported Razorpay Test Mode actions, and measure recovered revenue separately from incremental recovered revenue.

This repository is implemented phase by phase from [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md). Phase 0 created the runnable foundation, Phase 1 added the core domain schema and Recovery Case lifecycle, Phase 2 added the bounded Razorpay Test Mode adapter, Phase 3 added verified webhook ingestion, and Phase 4 turns eligible monetary signals into persistent Recovery Cases.

## Implemented Scope

Implemented in Phase 0:

- FastAPI backend scaffold with health endpoints and structured logging
- Next.js frontend scaffold that loads and checks API health
- PostgreSQL and Redis via Docker Compose
- Alembic migration configuration with a foundation migration
- pytest configuration and backend health tests
- Architecture documentation and phase status tracking

Implemented in Phase 1:

- SQLAlchemy domain tables for merchants, customers, orders, payments, payment links, recovery cases, features, decisions, actions, outcomes, experiments, assignments, and audit events
- Centralized domain enums
- Recovery Case lifecycle validation with explicit allowed transitions
- Recovery Case repository for create, query, list, and transition operations
- Narrow Recovery Case API endpoints for Phase 1 validation
- Idempotent development seed command
- Unit tests for lifecycle and repository behavior

Implemented in Phase 2:

- Provider-neutral `PaymentGateway` contract
- Razorpay Basic Auth client with secret-safe configuration
- Typed order, payment, Payment Link, and notification contracts
- Order and payment reads
- Recovery Payment Link creation
- Payment Link email/SMS notification and resend
- Payment Link cancellation
- Normalized configuration, transport, provider, and response errors
- Mock-transport contract tests for every supported operation

Implemented in Phase 3:

- Raw-body HMAC-SHA256 verification for Razorpay webhook signatures
- Current and previous webhook-secret support for safe secret rotation
- Durable event persistence and provider/event ID deduplication
- Routing for supported payment and Payment Link event types
- Correlation to existing Recovery Cases
- Current-state reconciliation through Razorpay payment, order, and Payment Link reads
- Safe retry of failed reconciliation without repeating processed events
- Duplicate-delivery and out-of-order event tests

Implemented in Phase 4:

- Idempotent Recovery Case creation from failed payments
- Configurable unpaid-order detection and case creation
- Payment Link case correlation and remaining-balance calculation
- Merchant account ownership checks for webhook-created resources
- Configurable recovery windows with persisted expiration
- Stop conditions for inactive merchants, opted-out customers, paid resources,
  and cancelled links
- Append-only case creation and status-change audit events
- Active-case query for dashboard consumers

Not implemented yet:

- Revenue-at-risk aggregation and ranking
- AI/ML decisions, policy engine, recovery execution, or monetary metrics

## Run Locally

Copy the environment template if you want to override defaults:

```bash
cp .env.example .env
```

Start all services:

```bash
docker compose up --build
```

Expected local URLs:

- API health: [http://localhost:8000/health](http://localhost:8000/health)
- API readiness: [http://localhost:8000/health/ready](http://localhost:8000/health/ready)
- Web app: [http://localhost:3000](http://localhost:3000)

If either port is already in use, override the published ports:

```bash
API_PORT=18000 WEB_PORT=13000 NEXT_PUBLIC_API_BASE_URL=http://localhost:18000 docker compose up --build
```

PowerShell:

```powershell
$env:API_PORT="18000"
$env:WEB_PORT="13000"
$env:NEXT_PUBLIC_API_BASE_URL="http://localhost:18000"
docker compose up --build
```

The API container runs `alembic upgrade head` before starting, so migrations are applied during `docker compose up`.

## Backend Development

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -r apps/api/requirements.txt
.venv\Scripts\python -m pytest
```

Run the API directly:

```bash
$env:DATABASE_URL="postgresql+psycopg://recovery:recovery@localhost:5432/recovery_control_plane"
$env:REDIS_URL="redis://localhost:6379/0"
.venv\Scripts\python -m uvicorn app.main:app --app-dir apps/api --reload
```

Run migrations directly:

```bash
.venv\Scripts\python -m alembic upgrade head
```

Seed one demo merchant, customer, and recovery case:

```powershell
$env:PYTHONPATH="apps/api"
.venv\Scripts\python -m app.db.seed
```

With the API running, Recovery Cases can be checked at:

- `GET /api/cases`
- `GET /api/cases/{case_id}`
- `POST /api/cases`
- `PATCH /api/cases/{case_id}/status`
- `GET /api/cases?active_only=true`
- `POST /api/cases/scan-unpaid-orders`

See [docs/recovery-cases.md](docs/recovery-cases.md) for Phase 4 eligibility,
amount-at-risk, recovery-window, expiration, and stop-condition behavior.

## Razorpay Test Mode Adapter

Set `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET` in `.env` to construct a real
Test Mode gateway. Live keys are rejected by default. The API and web services
still start when credentials are absent; adapter construction then fails closed.

See [docs/razorpay-adapter.md](docs/razorpay-adapter.md) for the verified endpoint
contract, configuration, safety boundary, and test strategy.

## Razorpay Webhooks

Configure `RAZORPAY_WEBHOOK_SECRET` and send Razorpay Test Mode webhooks to:

```text
POST /webhooks/razorpay
```

The endpoint requires `X-Razorpay-Signature` and `x-razorpay-event-id`. It
verifies the untouched request body before parsing or persisting it. See
[docs/webhooks.md](docs/webhooks.md) for supported events, retries, reconciliation,
and local testing guidance.

## Frontend Development

```bash
pnpm install
pnpm web:dev
```

## Safety Boundary

The project architecture remains:

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

This code does not perform financial actions and does not assume any unsupported Razorpay API such as a generic failed-payment retry endpoint.
