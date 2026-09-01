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
- `PATCH /api/cases/{case_id}/status` for validated lifecycle transitions

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
