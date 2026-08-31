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

Status: Not started

Phase 1 must not begin until Phase 0 acceptance criteria are satisfied.
