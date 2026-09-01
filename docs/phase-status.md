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

Status: Not started

Phase 2 must not begin until Phase 1 acceptance criteria are satisfied.
