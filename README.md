# Revenue Recovery Control Plane

Revenue Recovery Control Plane is an AI-assisted decision and measurement layer for Razorpay merchants. It is intended to unify revenue-at-risk, recommend economically sensible recovery interventions, gate every financial action through deterministic policy, execute only supported Razorpay Test Mode actions, and measure recovered revenue separately from incremental recovered revenue.

This repository is implemented phase by phase from [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md). Phase 0 creates the runnable foundation only; domain entities, Razorpay adapters, webhooks, guardrails, recovery actions, simulation, and ML arrive in later phases.

## Phase 0 Scope

Implemented in this phase:

- FastAPI backend scaffold with health endpoints and structured logging
- Next.js frontend scaffold that loads and checks API health
- PostgreSQL and Redis via Docker Compose
- Alembic migration configuration with a foundation migration
- pytest configuration and backend health tests
- Architecture documentation and phase status tracking

Not implemented yet:

- Recovery Case schema and lifecycle
- Razorpay API calls or webhooks
- AI/ML decisions, policy engine, recovery execution, or monetary metrics

## Run Locally

Copy the environment template if you want to override defaults:

```bash
cp .env.example .env
```

Start all Phase 0 services:

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

The API container runs `alembic upgrade head` before starting, so the foundation migration is applied during `docker compose up`.

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

Phase 0 does not perform financial actions and does not assume any unsupported Razorpay API such as a generic failed-payment retry endpoint.
