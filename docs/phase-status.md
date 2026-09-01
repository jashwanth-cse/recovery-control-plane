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

Status: Not started

Phase 3 must not begin until Phase 2 acceptance criteria are satisfied.
