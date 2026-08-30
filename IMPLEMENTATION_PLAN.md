# Razorpay AI Buildathon 2026 — AI Revenue Recovery
## Complete R&D, Product Blueprint & Phase-by-Phase Implementation Plan

> **Purpose:** This document is the single implementation-oriented source of truth for the project.  
> It is written so that an AI coding agent such as **Codex** can understand the product, architecture, constraints, engineering contracts, evaluation methodology, and implementation sequence before writing code.

---

## 0. HOW CODEX MUST USE THIS DOCUMENT

This repository must be implemented **phase by phase**.

Codex must NOT attempt to implement the complete project in one pass.

### Mandatory operating procedure

Before starting any phase:

1. Read this entire document.
2. Read the current repository state.
3. Read all existing code, tests, configuration, and documentation relevant to the phase.
4. Identify the exact requirements and acceptance criteria for the current phase.
5. Propose a concise implementation plan for that phase.
6. Implement only that phase.
7. Run relevant tests and validation.
8. Update documentation/changelog/status files.
9. Report:
   - what changed
   - files changed
   - tests executed
   - known limitations
   - next phase readiness
10. Do not silently expand scope.

### Critical rule

**Never invent an API, Razorpay capability, webhook, endpoint, response field, or financial action.**

When an integration capability is uncertain:
- inspect official documentation,
- inspect the project integration contract,
- if still uncertain, isolate it behind an adapter and simulate it rather than inventing behavior.

### Financial-safety rule

The LLM/AI layer must never have unrestricted authority over money movement.

The architecture must always remain:

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

### MVP discipline

Do not add:
- voice
- Hinglish
- mandates
- full subscription lifecycle
- full B2B collections
- multi-agent orchestration
- live money
- Kubernetes/microservice over-engineering

unless explicitly promoted into scope later.

---

# 1. PROJECT SUMMARY

## Working Product Name

**Revenue Recovery Control Plane**

The final public-facing name may change later.

## One-line product definition

> An intelligent revenue-recovery control plane for Razorpay merchants that unifies revenue-at-risk, determines the economically best recovery intervention, executes it within deterministic safety boundaries, and measures incremental revenue actually created by the intervention.

## Core user

Primary user:

- Revenue Operations
- Finance Operations
- Growth / Monetization

at a digital business using Razorpay.

Secondary user:

- Merchant engineer responsible for integration and audit/reliability.

## Core merchant problem

Merchants lose money through:
- failed payments
- abandoned checkouts
- recovery opportunities spread across separate payment objects

They often cannot answer:

1. How much revenue is at risk?
2. Which cases are worth pursuing?
3. What intervention should be used?
4. When should it happen?
5. When should we stop?
6. How much additional revenue did the intervention actually cause?

The product answers these questions in one controlled system.

---

# 2. RESEARCH-DERIVED POSITIONING

The R&D established that the following are already substantially commoditized or implemented elsewhere:

- fixed retry schedules
- smart retry timing
- simple dunning
- payment-link generation
- basic failed-payment dashboards
- generic recoverability scoring
- bounded retry agents
- B2B next-best-action collections

A particularly important competitor/discovery is **Juspay Hyperswitch Revenue Recovery**, which has:
- a Predictor for retry success probability
- a Decider for retry-budget optimization
- a bounded retry agent

Therefore:

> **Generic “AI retries failed payments” is NOT our innovation.**

Razorpay itself also provides recovery-oriented primitives and Agent Studio capabilities, so simply reproducing retry, cart recovery, subscription recovery, or voice recovery is not sufficient.

## Our differentiation hypothesis

The strongest remaining combination identified by the research is:

1. **Cross-product revenue-at-risk**
2. **Expected-value / next-best-action across intervention types**
3. **Incremental/causal measurement of recovery interventions**
4. **Bounded, gated, auditable execution on Razorpay**

The key differentiator is:

> **We do not only report recovered revenue. We attempt to estimate the incremental revenue caused by the recovery intervention.**

---

# 3. OFFICIAL CHALLENGE BAR WE ARE DESIGNING AGAINST

The AI Revenue Recovery track requires a system that:

- detects revenue at risk
- determines the appropriate intervention
- executes a bounded recovery workflow
- shows measured money recovered across a batch
- handles compliant escalation
- enforces stopping rules
- provides an audit trail

The universal financial-action expectation is:

> Money actions must be explainable, bounded, and gated.

The project therefore must demonstrate:

```text
Detect
  ↓
Decide
  ↓
Gate
  ↓
Execute
  ↓
Observe
  ↓
Stop / Continue
  ↓
Measure
```

---

# 4. LOCKED MVP SCOPE

## IN SCOPE

### Revenue sources

1. Failed one-time payments
2. Abandoned checkout / unpaid order recovery
3. Payment-link recovery

### Real Razorpay integration

Use Razorpay Test Mode for:

- webhooks
- payment/order reads
- Payment Link creation
- Payment Link notification/resend where supported
- Payment Link cancellation
- test-card payment outcomes
- reconciliation reads

### Intelligent layer

- recoverability scoring
- action-specific recovery probability
- expected value
- next-best-action
- timing recommendation
- deterministic policy enforcement
- explainability

### Evaluation

- synthetic batch generator
- ground-truth simulator
- no-intervention control
- AI treatment
- recovery outcome tracking
- incremental recovery calculation
- baseline comparison
- model metrics
- business metrics
- safety metrics

### Product UI

- revenue-at-risk dashboard
- recovery queue
- case detail
- decision explanation
- experiment results
- audit trail
- policy/guardrail status

---

# 5. EXPLICITLY OUT OF SCOPE

Do not implement in MVP:

- full subscription lifecycle management
- recurring mandate recovery
- UPI mandate retry optimization
- complete B2B receivables/collections
- promise-to-pay workflows
- voice recovery
- Hinglish voice
- multi-agent orchestration
- live/real-money transactions
- autonomous card updates
- arbitrary card charging
- arbitrary retry APIs that Razorpay does not expose
- complex reinforcement learning
- microservices solely for architectural appearance
- Kubernetes unless later justified
- broad CRM functionality

These are potential future extensions only.

---

# 6. CRITICAL RAZORPAY INTEGRATION CONSTRAINT

## There is no generic “retry failed payment object” API

The Payments API is not a generic money-collection retry mechanism for an already failed payment.

Therefore:

### Do NOT implement:

```text
failed payment
→ POST /payments/{id}/retry
```

unless an official current API explicitly establishes such an endpoint.

### MVP recovery interpretation

For a failed one-time payment:

```text
failed payment
        ↓
recovery decision
        ↓
create recovery Payment Link
        ↓
send/re-notify
        ↓
customer completes payment
        ↓
payment_link.paid
        ↓
reconcile order/payment
```

Internally use names such as:

- `RECOVERY_LINK`
- `PAYMENT_LINK_RECOVERY`

rather than pretending we are directly retrying the failed payment object.

---

# 7. REAL VS SIMULATED CAPABILITIES

## Real Razorpay operations

The system should integrate with the actual Razorpay Test environment for:

- webhook ingestion
- payment/order state reads
- Payment Link creation
- Payment Link notification/resend where supported
- Payment Link cancellation
- test-card success/failure
- final reconciliation

## Simulated operations

Use our simulator for:

- large synthetic batches
- customer behavior
- control-group outcomes
- rich failure taxonomy beyond deterministic test-mode scenarios
- hypothetical intervention outcomes
- UPI-specific recovery scenarios if not reproducible in test mode
- large-scale experiment execution
- ground truth
- causal counterfactuals

## Why hybrid simulation is required

Razorpay Test Mode provides useful deterministic payment testing, but it does not reproduce the full real-world universe of decline reasons and high-volume scenarios needed for ML/evaluation.

Therefore the project must use:

```text
Real Razorpay execution rails
+
Synthetic realistic evaluation environment
```

---

# 8. PRODUCT CONCEPT

## 8.1 Merchant flow

```text
Razorpay account
      ↓
Webhook / API ingestion
      ↓
Revenue events
      ↓
Recovery cases
      ↓
Revenue-at-risk aggregation
      ↓
AI recovery decision
      ↓
Safety/policy gate
      ↓
Razorpay-supported action
      ↓
Outcome
      ↓
Measurement
```

## 8.2 Core merchant promise

The merchant should be able to see:

```text
Revenue at Risk
₹18.42L

Expected Recoverable
₹9.67L

Recovered
₹4.28L

Incremental Recovery
₹1.63L
```

The exact figures shown in demos must be generated by the system and never hard-coded as fake business results.

---

# 9. DOMAIN MODEL

The core abstraction is a **Recovery Case**.

Everything revolves around the Recovery Case.

## 9.1 Recovery Case

A Recovery Case represents one monetary opportunity that is currently at risk and may be recovered.

Examples:

- payment failed
- checkout started but not paid
- payment link expired/unpaid

## 9.2 Case lifecycle

```text
AT_RISK
   ↓
ELIGIBILITY_CHECK
   ↓
ASSESSING
   ↓
DECISION_READY
   ↓
POLICY_CHECK
   ↓
ACTION_PENDING
   ↓
EXECUTING
   ├──────────────→ RECOVERED
   │
   ↓
ACTION_FAILED
   ↓
REASSESS
   ├──────────────→ NEXT_ACTION
   └──────────────→ STOPPED
```

Terminal states:

- `RECOVERED`
- `STOPPED`
- `EXPIRED`
- `ESCALATED`

Every case must terminate.

---

# 10. DATA MODEL

Use PostgreSQL.

The exact SQL schema may evolve during implementation, but the conceptual entities are locked.

## 10.1 `merchants`

```text
id
name
status
razorpay_key_id
secret_reference
created_at
updated_at
```

Never log or commit secrets.

## 10.2 `customers`

```text
id
merchant_id
external_customer_id
email
phone
consent_status
created_at
updated_at
```

## 10.3 `orders`

```text
id
merchant_id
razorpay_order_id
customer_id
amount
currency
amount_paid
amount_due
status
attempts
created_at
updated_at
```

## 10.4 `payments`

```text
id
merchant_id
razorpay_payment_id
razorpay_order_id
amount
currency
status
method
error_code
error_description
error_reason
error_source
error_step
bank
vpa
invoice_id
created_at
updated_at
```

## 10.5 `payment_links`

```text
id
merchant_id
razorpay_payment_link_id
order_id
recovery_case_id
amount
currency
status
short_url
expire_by
created_at
updated_at
```

## 10.6 `recovery_cases`

```text
id
merchant_id
customer_id

source_type
source_id

amount_at_risk
currency

status

recovery_window_start
recovery_window_end

attempt_count
contact_count

experiment_id
experiment_group

created_at
updated_at
```

## 10.7 `recovery_features`

Persist the feature snapshot used by the model.

```text
recovery_case_id

failure_reason
failure_source
failure_code
payment_method

amount
attempt_count
case_age

customer_tenure
prior_success_count
prior_failure_count

previous_recovery_success_count
engagement_score

available_payment_methods

feature_timestamp
```

## 10.8 `recovery_decisions`

```text
id
recovery_case_id

model_version

candidate_actions
action_scores
expected_values

selected_action
selected_action_score

reason_code
explanation

created_at
```

## 10.9 `recovery_actions`

```text
id
recovery_case_id

action_type
status

razorpay_resource_id

scheduled_at
executed_at

policy_result
failure_reason

created_at
updated_at
```

## 10.10 `action_outcomes`

```text
id
action_id

outcome
amount_recovered
razorpay_payment_id

recovered_at
```

## 10.11 `experiments`

```text
id
merchant_id

name

control_percentage
status

created_at
```

## 10.12 `experiment_assignments`

```text
id
experiment_id
recovery_case_id

group_name
assigned_at
```

## 10.13 `audit_events`

```text
id
recovery_case_id

event_type
actor_type

input_snapshot
decision_snapshot
policy_snapshot
action_snapshot

timestamp
```

Audit events should be append-only in application behavior.

---

# 11. CORE METRICS

## 11.1 Gross revenue metrics

### Revenue at Risk

```text
sum(amount_at_risk for active eligible cases)
```

### Expected Recoverable Revenue

For each case/action:

```text
P(recovery | action, context) × amount
```

Aggregate across cases.

### Gross recovered revenue

Sum of captured amounts associated with recovery cases.

---

# 12. EXPECTED VALUE

For an action:

```text
EV(action)
=
P(recovery | action, context)
× amount_at_risk
− intervention_cost
− friction_penalty
```

Potential extensions:

```text
− risk_penalty
− time_decay_penalty
```

Do not overcomplicate the first working version.

## Important

The ML model should ideally estimate action-conditional probabilities:

```text
P(recovery | RECOVERY_LINK, context)
P(recovery | UPDATE, context)
P(recovery | DELAY, context)
```

rather than producing only one generic recovery score.

---

# 13. NEXT-BEST-ACTION

MVP candidate actions:

```text
RECOVERY_LINK
PAYMENT_METHOD_UPDATE_PROMPT
DELAY
STOP
ESCALATE
```

Potential `RETRY` should only exist if its actual execution path is established by the integration contract/current Razorpay documentation.

Candidate actions are evaluated and then filtered through policy.

Example:

```text
Candidate          Probability    EV
-----------------------------------------
Recovery Link         0.72       ₹3,597
Update Method         0.61       ₹3,049
Delay                 0.44       ₹2,199
Escalate              0.31       ₹1,500
Stop                  0.00       ₹0
```

The system chooses the highest policy-approved expected value.

---

# 14. AI / ML / LLM RESPONSIBILITY BOUNDARY

## ML is responsible for

- structured prediction
- action-conditional recovery probability
- expected-recovery estimation
- ranking candidate interventions
- timing recommendations where supported by data

Recommended initial family:

- LightGBM
- XGBoost
- or an equally suitable gradient-boosted model

Start with a rule-based baseline.

## LLM is responsible for

- explaining a decision
- summarizing failure context
- producing customer-facing draft text if required
- producing human-readable audit narrative

## LLM must NOT be responsible for

- arbitrary payment API execution
- bypassing policy
- changing monetary amounts without validated rules
- overriding a hard stop
- determining authorization limits
- creating duplicate recovery actions

---

# 15. DETERMINISTIC POLICY ENGINE

This is the safety boundary.

Example policy configuration:

```yaml
recovery:
  max_attempts: 3
  max_customer_contacts: 3
  max_window_days: 14

  high_value_threshold: 50000

  high_value_requires_human: true

  hard_stop_reasons:
    - payment_risk_check_failed
    - mandate_revoked
    - customer_opted_out

  prevent_duplicate_actions: true
  prevent_action_after_paid: true
```

These are examples, not immutable regulatory requirements.

The final rules must be validated against the supported payment rail and the actual MVP flow.

## Policy evaluation

```text
Decision
   ↓
Policy Engine
   ↓
ALLOW / BLOCK / ESCALATE
```

Example:

```json
{
  "allowed": false,
  "decision": "BLOCK",
  "reason": "RECOVERY_WINDOW_EXPIRED"
}
```

---

# 16. GUARDRAIL PRINCIPLES

At minimum enforce:

1. Case already paid → no further money action.
2. Duplicate recovery-link creation must be prevented.
3. Maximum action/attempt counts.
4. Recovery-window expiry.
5. Customer opt-out.
6. High-value escalation.
7. Explicit hard-stop conditions.
8. No action beyond supported Razorpay API capability.
9. Every action is logged.
10. Every blocked action is logged.
11. Every money action has an explainable reason.
12. Every external action is idempotent or safely deduplicated.

---

# 17. RAZORPAY ADAPTER DESIGN

Razorpay-specific details must live behind an adapter.

Recommended conceptual interface:

```python
class PaymentGateway:
    def get_payment(...)
    def get_order(...)
    def create_payment_link(...)
    def notify_payment_link(...)
    def cancel_payment_link(...)
```

Application logic should call the abstract capability, not raw HTTP endpoints.

Example:

```text
recovery/
    service.py
integrations/
    razorpay/
        client.py
        orders.py
        payments.py
        payment_links.py
        webhooks.py
```

This ensures the recovery engine is not tightly coupled to Razorpay implementation details.

---

# 18. WEBHOOK ARCHITECTURE

Relevant events include, where enabled/currently supported:

```text
payment.failed
payment.authorized
payment.captured

payment_link.paid
payment_link.partially_paid
payment_link.cancelled
payment_link.expired
```

The actual webhook list used by the implementation must match current Razorpay documentation.

## Webhook handling

```text
Incoming webhook
       ↓
Verify signature
       ↓
Extract event ID
       ↓
Duplicate?
    /       \
  yes        no
  stop       ↓
        persist event
             ↓
        enqueue/process
             ↓
        update case
             ↓
        reconcile API
```

Important properties already established by research:

- at-least-once delivery
- duplicates are possible
- ordering is not guaranteed
- signatures must be verified
- API reads should be used to reconcile critical state

---

# 19. IDEMPOTENCY

The recovery-link creation path must be idempotent at the application level.

Recommended flow:

```text
Recovery Case
    ↓
Already has active recovery link?
    ├── YES → reuse/return
    └── NO
          ↓
Check order amount_due
          ↓
Already paid?
    ├── YES → STOP
    └── NO
          ↓
Create unique reference_id
          ↓
Call Razorpay
          ↓
Persist link ID
```

`reference_id` must be treated as unique according to the integration contract.

Persist:

```text
recovery_case_id
razorpay_payment_link_id
reference_id
```

and use these to correlate actions and outcomes.

---

# 20. REVENUE-AT-RISK ENGINE

The product should unify at-risk opportunities into one internal view.

For MVP:

```text
failed payment
abandoned/unpaid order
unpaid/expired recovery link
```

Each case has:

```text
amount_at_risk
recoverability
time_remaining
expected_value
priority
```

## Priority concept

A reasonable initial ranking:

```text
priority_score
=
expected_value
× urgency_factor
```

The exact equation can evolve.

Do not claim that this is an industry-standard formula.

It is our engineering decision.

---

# 21. SYNTHETIC DATA & SIMULATION ENGINE

This is critical to the project's reproducibility.

The simulator must generate:

### Observed features

```text
case_id
amount
failure_reason
failure_source
payment_method
attempt_count
case_age
customer_tenure
prior_successes
prior_failures
engagement_score
available_methods
```

### Hidden ground truth

For each case/action combination, the simulator should internally know:

```text
would_recover_without_intervention
would_recover_with_recovery_link
would_recover_with_update_prompt
would_recover_after_delay
```

The AI/model must NOT receive hidden ground-truth fields.

---

# 22. COUNTERFACTUAL / INCREMENTAL MEASUREMENT

This is the project's strongest conceptual differentiator.

Suppose:

```text
Treatment:
AI recovery intervention

Control:
No intervention
```

If:

```text
Treatment recovery rate = 34%
Control recovery rate  = 21%
```

then:

```text
incremental recovery rate = 13 percentage points
```

For comparable eligible revenue:

```text
incremental recovered revenue
=
incremental recovery rate
× eligible treatment revenue
```

Then:

```text
net incremental recovered revenue
=
incremental recovered revenue
− intervention cost
```

Do not claim all treatment-group recovered revenue was caused by the AI.

That is exactly the problem our experiment is designed to address.

---

# 23. EXPERIMENT DESIGN

## Basic MVP

Randomly assign eligible cases:

```text
CONTROL
vs
TREATMENT
```

Randomization must happen before the intervention decision.

### Control

Do not execute the AI recovery action during the experiment window.

### Treatment

Run the AI decision + policy + recovery workflow.

## Later extension

Multi-arm experiments:

```text
Control
Recovery Link
Delay
Update Prompt
```

This should not be part of the first implementation unless the basic experiment is stable.

---

# 24. BASELINES

Every evaluation run should compare:

### Baseline 0

No intervention.

### Baseline 1

Simple deterministic rules.

Example:

```text
if failure == transient:
    recovery_link
else:
    stop
```

### Candidate

ML/AI decision engine.

This allows us to answer:

> Is our intelligence actually better than doing nothing and better than a simple rules engine?

---

# 25. EVALUATION METRICS

## Model

- ROC-AUC where appropriate
- PR-AUC where appropriate
- calibration
- top-k precision / recovery value
- action-selection accuracy where ground truth exists

## Uplift / causal

- incremental recovery rate
- incremental recovered revenue
- Qini/AUUC where implemented
- lift by score decile
- confidence intervals

## Business

- gross recovered revenue
- incremental recovered revenue
- net recovered revenue
- recovery rate
- window expiry rate
- cost-to-collect
- ROI

## Safety

- duplicate action rate
- blocked-action rate
- policy violation rate
- opt-out violation rate
- action-after-paid rate
- incorrect escalation rate

---

# 26. HOW THE SYSTEM SHOULD MEASURE “RECOVERY”

A payment should count as recovered only when the system can link the successful payment to the recovery case and verify the final payment/order state.

Recommended evidence:

```text
payment_link.paid
+
payment/order reconciliation
+
captured payment
```

Do not count:
- link creation
- link notification
- customer clicking the link
- merely moving a case from failed to pending

as revenue recovery.

Only actual captured monetary outcome counts.

---

# 27. AUDIT TRAIL

Every significant transition should generate an audit event.

Example:

```text
REC_10284

09:12:04
EVENT_RECEIVED
payment.failed

09:12:05
DIAGNOSIS
insufficient_funds

09:12:05
MODEL_DECISION
P(recovery)=0.72

09:12:05
ACTION_COMPARISON
RECOVERY_LINK EV=₹3,597
UPDATE EV=₹3,049
DELAY EV=₹2,199

09:12:06
POLICY
ALLOWED

09:12:07
ACTION_EXECUTED
payment_link_created

09:41:32
OUTCOME
payment_link.paid

09:41:32
RECOVERY
₹4,999

09:41:33
RECONCILIATION
order.status=paid
payment.captured=true
```

The UI must make this inspectable.

---

# 28. “WHY THIS ACTION?” FEATURE

Every AI decision should be explainable.

Example UI:

```text
Why Payment Link?

Failure:
insufficient_funds

Customer history:
8 successful payments

Prior failures:
1

Amount:
₹4,999

Recovery window remaining:
11 days

Expected values:
Payment Link  ₹3,597
Update        ₹3,049
Delay         ₹2,199

Selected:
Payment Link

Policy:
Allowed

Reason:
Highest expected recovery value
under current merchant policy.
```

The numbers must come from the actual decision engine.

---

# 29. GRACEFUL FAILURE DEMO

The demo should deliberately contain a blocked action.

Example:

```text
AI recommends:
RECOVERY_LINK

        ↓

Policy Engine

        ↓

Customer communication consent = false

        ↓

ACTION BLOCKED

        ↓

ESCALATE

        ↓

Audit recorded
```

UI:

> Recovery action blocked by policy. Human review required.

This simultaneously demonstrates:
- AI recommendation
- deterministic governance
- safe autonomy
- escalation
- auditability

---

# 30. UI / UX

The MVP UI should have five principal areas.

## Dashboard

Show:

- Revenue at Risk
- Expected Recoverable
- Gross Recovered
- Incremental Recovered
- Active Cases
- Stopped Cases

## Recovery Queue

Columns:

```text
Priority
Case
Amount
Failure
P(recovery)
Expected Value
Action
Status
```

## Case Detail

Show:
- payment/order context
- customer context
- features
- score
- candidate actions
- selected action
- guardrail outcome
- execution
- final outcome

## Experiment

Show:

```text
Control
Treatment
Recovery Rate
Incremental Rate
Incremental Revenue
Net Recovery
```

## Audit

Chronological event timeline.

---

# 31. RECOMMENDED TECH STACK

The goal is effective implementation, not technology theatre.

## Backend

- Python
- FastAPI
- Pydantic
- SQLAlchemy
- Alembic

## Database

- PostgreSQL

## Background processing

- Redis
- Celery or an equally simple background-job mechanism

## ML

- Python
- pandas
- scikit-learn
- LightGBM or XGBoost

## LLM

Use a model provider through a narrow abstraction.

Keep prompts, schemas, and provider code separate from recovery business logic.

## Frontend

- Next.js
- TypeScript
- React
- a professional component library

## Testing

- pytest
- backend integration tests
- frontend tests as appropriate
- contract tests for Razorpay adapter
- simulator/evaluation tests

## Infrastructure

- Docker
- Docker Compose

Start with a modular monolith.

---

# 32. RECOMMENDED REPOSITORY STRUCTURE

```text
revenue-recovery-control-plane/
│
├── apps/
│   ├── api/
│   └── web/
│
├── packages/
│   ├── domain/
│   ├── policy-engine/
│   ├── razorpay-client/
│   └── common/
│
├── services/
│   ├── recovery/
│   ├── experiments/
│   ├── simulation/
│   └── ml/
│
├── migrations/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── contract/
│   └── evaluation/
│
├── simulator/
│
├── docs/
│   ├── architecture.md
│   ├── api-contracts.md
│   ├── decision-engine.md
│   ├── guardrails.md
│   └── evaluation.md
│
├── scripts/
│
├── docker-compose.yml
├── .env.example
├── README.md
└── IMPLEMENTATION_PLAN.md
```

The repository may be adjusted after the initial scaffold, but the architecture must preserve logical separation.

---

# 33. INTERNAL API CONTRACT — CONCEPTUAL

The exact REST schema may be refined during implementation, but the backend should expose concepts similar to:

```text
POST /webhooks/razorpay
GET  /api/cases
GET  /api/cases/{case_id}
POST /api/cases/{case_id}/assess
POST /api/cases/{case_id}/decide
POST /api/cases/{case_id}/execute
POST /api/cases/{case_id}/stop

GET  /api/dashboard/summary
GET  /api/dashboard/recovery-queue

GET  /api/experiments/{id}
GET  /api/experiments/{id}/results

GET  /api/cases/{case_id}/audit
GET  /api/cases/{case_id}/explanation
```

Do not expose unrestricted “execute arbitrary action” endpoints.

Execution APIs should accept only validated domain actions.

---

# 34. DOMAIN ENUMS

Centralize these rather than scattering strings throughout the codebase.

Example:

```text
RecoveryCaseStatus:
AT_RISK
ASSESSING
DECISION_READY
ACTION_PENDING
EXECUTING
RECOVERED
ACTION_FAILED
STOPPED
EXPIRED
ESCALATED
```

```text
ActionType:
RECOVERY_LINK
PAYMENT_METHOD_UPDATE
DELAY
STOP
ESCALATE
```

Potential future action:

```text
RETRY
```

only if a legitimate execution path is introduced.

```text
ExperimentGroup:
CONTROL
TREATMENT
```

---

# 35. PHASE-BY-PHASE IMPLEMENTATION PLAN

The implementation is intentionally incremental.

---

## PHASE 0 — Repository & Architecture Foundation

### Goal

Create a clean, runnable repository.

### Tasks

- initialize repository
- create README
- create environment template
- create Docker Compose
- scaffold backend
- scaffold frontend
- configure PostgreSQL
- configure Redis
- configure migrations
- configure logging
- configure test framework
- create basic health endpoints
- create architectural documentation

### Exit criteria

```text
docker compose up
```

starts all required MVP services.

Backend health endpoint works.

Frontend loads.

Database migration executes.

Tests run.

---

## PHASE 1 — Domain Model & Database

### Goal

Implement the core entities and Recovery Case state machine.

### Tasks

- define domain models
- implement database schema
- write migrations
- seed development data
- implement recovery case lifecycle
- add domain validation
- add repository layer
- add unit tests

### Exit criteria

Can create/update/query a Recovery Case.

Invalid state transitions are rejected.

Tests cover core transitions.

---

## PHASE 2 — Razorpay Integration Layer

### Goal

Build and test a clean Razorpay adapter.

### Tasks

- configuration handling
- Razorpay client
- authentication
- orders read API
- payments read API
- payment-links API
- notification/resend capability as supported
- cancellation
- typed responses
- error normalization
- integration tests/mocks

### Exit criteria

The application can:
- fetch order
- fetch payment
- create a recovery Payment Link
- notify/resend where supported
- cancel a recovery link

No business logic should depend directly on raw HTTP calls.

---

## PHASE 3 — Webhook Ingestion

### Goal

Create reliable event ingestion.

### Tasks

- webhook endpoint
- signature verification
- event persistence
- event ID deduplication
- event routing
- case correlation
- API reconciliation
- idempotency tests
- duplicate-delivery tests
- out-of-order event tests

### Exit criteria

Repeated webhook delivery does not duplicate business actions.

Critical states reconcile successfully against Razorpay.

---

## PHASE 4 — Recovery Case Engine

### Goal

Turn Razorpay events into recoverable cases.

### Tasks

- create case from failed payment
- create case from eligible abandoned/unpaid order signals
- link Payment Link events to cases
- calculate amount at risk
- define recovery window
- implement case expiration
- implement case stop conditions

### Exit criteria

A failed/unpaid monetary event results in a persistent Recovery Case.

The dashboard can query active cases.

---

## PHASE 5 — Revenue-at-Risk Aggregator

### Goal

Create the unified monetary opportunity view.

### Tasks

- aggregate active at-risk cases
- compute expected recoverable value
- rank cases
- build dashboard APIs
- build initial UI

### Exit criteria

Dashboard displays real computed:

```text
Revenue at Risk
Expected Recoverable
Active Cases
Top opportunities
```

No hard-coded metrics.

---

## PHASE 6 — Rule-Based Recovery Baseline

### Goal

Create the benchmark system.

### Tasks

- define simple deterministic recovery rules
- implement rule-based action selection
- record action outcomes
- implement control group
- create baseline reports

### Exit criteria

We can run a batch and compare:

```text
No intervention
vs
Rule-based recovery
```

---

## PHASE 7 — Synthetic Data Simulator

### Goal

Create a reproducible environment for large-scale evaluation.

### Tasks

- synthetic customer generator
- payment generator
- failure generator
- case-age generator
- customer-history generator
- intervention-outcome generator
- hidden counterfactual ground truth
- deterministic random seeds

### Exit criteria

One command can generate a reproducible dataset of thousands of cases.

The hidden ground truth is separated from model-visible features.

---

## PHASE 8 — ML Recoverability / Action Model

### Goal

Implement data-driven decision intelligence.

### Tasks

- feature pipeline
- training dataset generation
- train/validation/test split
- model training
- model serialization/versioning
- calibration evaluation
- action-conditional probability estimation
- model inference service/module

### Exit criteria

The AI candidate can outperform the rule baseline on the defined evaluation dataset or clearly demonstrate why it does not yet.

No leakage from hidden ground truth into features.

---

## PHASE 9 — Expected Value & Next-Best-Action

### Goal

Turn predictions into economically meaningful decisions.

### Tasks

- action candidate generation
- action probability scoring
- intervention cost model
- EV calculation
- time/urgency handling
- ranking
- stop/skip decision
- decision persistence

### Exit criteria

A case can produce:

```text
candidate actions
probability per action
EV per action
selected action
reason
```

and this is deterministic given a fixed model/configuration.

---

## PHASE 10 — Deterministic Guardrail Engine

### Goal

Make AI autonomy bounded and safe.

### Tasks

- policy config
- max attempts
- max contacts
- time windows
- consent checks
- already-paid checks
- duplicate action checks
- high-value escalation
- hard-stop conditions
- policy decision audit

### Exit criteria

Every executable AI recommendation passes through policy.

A blocked action cannot execute.

A policy-blocked action creates an audit event.

---

## PHASE 11 — Real Recovery Execution

### Goal

Connect the decision engine to real Razorpay Test Mode.

### Tasks

- recovery-link action
- link creation
- notification/resend
- cancellation
- outcome observation
- payment/order reconciliation
- action retry safety

### Exit criteria

A complete real test-mode happy path works:

```text
failure
→ case
→ decision
→ policy
→ recovery link
→ customer test payment
→ payment_link.paid
→ reconciliation
→ recovered
```

---

## PHASE 12 — Incremental Measurement Engine

### Goal

Prove causal/incremental value.

### Tasks

- experiment configuration
- random assignment
- control
- treatment
- outcome collection
- recovery-rate comparison
- incremental revenue calculation
- intervention-cost calculation
- confidence intervals
- optional uplift metrics

### Exit criteria

A reproducible batch produces:

```text
control recovery
treatment recovery
incremental recovery
net incremental recovery
```

with a clear methodology.

---

## PHASE 13 — LLM Explanation Layer

### Goal

Add LLM value without giving it unsafe authority.

### Tasks

- structured decision explanation
- failure explanation
- customer message drafting
- audit narrative
- schema validation
- provider abstraction
- prompt versioning
- fallback behavior

### Exit criteria

LLM failure does not prevent core money-safety logic.

All AI-generated outputs are schema validated.

---

## PHASE 14 — Audit & Case Investigation UI

### Goal

Make the entire reasoning/action history inspectable.

### Tasks

- case timeline
- decision explanation
- model version
- action candidates
- policy result
- Razorpay resource IDs
- outcome
- recovered amount
- experiment group

### Exit criteria

A judge can inspect a single case from trigger to recovered revenue.

---

## PHASE 15 — Dashboard & Demo UX

### Goal

Create the polished product experience.

### Screens

1. Dashboard
2. Recovery Queue
3. Case Detail
4. Experiment Results
5. Audit Trail
6. Policy/Guardrail view

### Exit criteria

A user can understand the product within 30 seconds.

The major business metrics are visible immediately.

---

## PHASE 16 — Evaluation Harness

### Goal

Make results reproducible.

### Tasks

- one-command dataset generation
- one-command model evaluation
- rule baseline evaluation
- AI evaluation
- control/treatment evaluation
- report generation
- saved experiment metadata
- model/version tracking

### Exit criteria

A clean environment can reproduce the reported metrics.

---

## PHASE 17 — Failure Scenarios & Hardening

### Goal

Prove reliability.

Test:

- duplicate webhook
- out-of-order webhook
- already-paid order
- expired recovery case
- duplicate recovery request
- Razorpay API failure
- Payment Link creation failure
- customer opt-out
- policy block
- model unavailable
- LLM unavailable
- database retry
- worker retry

### Exit criteria

No uncontrolled money action occurs.

Every expected failure produces a safe terminal or recoverable state.

---

## PHASE 18 — Security & Production-Readiness Pass

### Goal

Remove obvious hackathon-grade security weaknesses.

Tasks:

- secret management
- request validation
- webhook verification
- authorization
- input sanitization
- PII minimization
- secure logs
- rate limiting
- audit integrity
- error handling
- dependency review

### Exit criteria

No secrets committed.

Sensitive data is not unnecessarily logged.

Webhook verification and authorization are tested.

---

## PHASE 19 — Final Demo Scenario

### Goal

Create one deterministic 5-minute-style demonstration.

### Scenario

```text
Merchant
  ↓
₹X revenue at risk
  ↓
10,000 synthetic cases
  ↓
AI prioritizes
  ↓
Case selected
  ↓
AI evaluates actions
  ↓
Policy allows
  ↓
Real Razorpay Test Link
  ↓
Payment succeeds
  ↓
Revenue recovered
  ↓
Experiment compares control/treatment
  ↓
Incremental ₹ shown
  ↓
Second case
  ↓
Policy blocks action
  ↓
Escalation + audit
```

### Exit criteria

Demo can be repeated reliably from a clean environment.

---

# 36. IMPLEMENTATION PRIORITY

If time becomes constrained, prioritize in this order:

```text
P0
Razorpay integration
Recovery cases
Guardrails
Recovery execution
Outcome measurement

P1
Revenue-at-risk
Rule baseline
Synthetic simulator
ML/NBA

P2
Incremental experimentation
Audit UI
LLM explanations

P3
Visual polish
Advanced analytics
Optional extensions
```

A complete P0 + P1 is better than a half-built P0–P3.

---

# 37. TESTING STRATEGY

## Unit tests

Cover:
- state transitions
- EV calculations
- policy engine
- action selection
- experiment assignment
- attribution calculations

## Integration tests

Cover:
- database
- Razorpay adapter
- webhook processing
- recovery action execution

## Contract tests

Verify:
- Razorpay request structure
- response parsing
- webhook payload parsing

## End-to-end tests

Test:

```text
failed event
→ recovery case
→ AI decision
→ guardrail
→ action
→ outcome
→ recovery measurement
```

## Failure tests

Every dangerous path must have a test that proves the action is blocked.

---

# 38. OBSERVABILITY

The backend should provide structured logs for:

```text
request_id
case_id
experiment_id
action_id
razorpay_resource_id
model_version
policy_version
```

Never log:
- Razorpay secrets
- raw authentication credentials
- unnecessary sensitive payment/customer data

Metrics should include:

```text
cases_created
cases_recovered
cases_stopped
actions_executed
actions_blocked
razorpay_errors
duplicate_events
recovered_revenue
incremental_revenue
```

---

# 39. CONFIGURATION

Anything likely to change during evaluation should be configurable.

Examples:

```yaml
recovery_window_days
max_attempts
high_value_threshold
control_percentage
intervention_costs
policy_rules
model_version
experiment_version
```

Avoid magic numbers in business logic.

---

# 40. VERSIONING

Track versions for:

```text
model
policy
experiment
dataset
decision logic
prompt
```

Every recovery decision should be reproducible from its recorded versions.

---

# 41. SECURITY PRINCIPLES

## Secrets

Use environment variables or secure secret storage.

Never:

```text
commit API keys
print API secrets
put secrets into screenshots
```

## PII

Collect only fields needed for the MVP.

## Webhooks

Always verify signatures before processing business events.

## External actions

Never execute external money actions from raw LLM output.

---

# 42. PRODUCT DESIGN PRINCIPLES

## Principle 1

**Show the money.**

Everything should ultimately connect to monetary value.

## Principle 2

**Explain the decision.**

The merchant should know why the system acted.

## Principle 3

**Bound the agent.**

The AI recommends. Policy permits. Executor acts.

## Principle 4

**Measure causality where possible.**

Collected money is not automatically incremental money.

## Principle 5

**Fail safely.**

A blocked action is a successful safety outcome.

## Principle 6

**Real integration beats fake integration.**

Use real Razorpay Test APIs wherever possible.

## Principle 7

**Simulation should be reproducible.**

Randomness must be seed-controlled.

---

# 43. WHAT NOT TO CLAIM IN THE PITCH

Do NOT say:

- “We invented smart retries.”
- “Nobody does recovery prediction.”
- “Our AI is the first recovery agent.”
- “Every recovered rupee was caused by our AI.”
- “Razorpay cannot do recovery.”
- “Razorpay provides no AI.”
- “No company uses causal experimentation.”
- “We directly retry failed Razorpay payments.”

Instead say:

> We are adding a decision and measurement layer on top of Razorpay's existing execution primitives.

And:

> We distinguish total recovered revenue from incremental recovered revenue.

And:

> Our system optimizes across recovery interventions rather than simply running a fixed retry schedule.

---

# 44. COMPETITOR POSITIONING

Relevant competitors discovered during R&D include:

- Razorpay Agent Studio
- Juspay Hyperswitch Revenue Recovery
- Stripe Revenue Recovery / Smart Retries
- Chargebee
- Recurly
- Paddle
- Zuora
- HighRadius
- Billtrust
- Tesorio

## Positioning

### Versus simple dunning

They say:

```text
Send reminder
Retry later
```

We say:

```text
Is this revenue worth pursuing?
What action has highest expected value?
What is permitted?
Did it create incremental revenue?
```

### Versus Hyperswitch

Hyperswitch demonstrates intelligent retry prediction/budget optimization.

Our differentiation hypothesis:

```text
cross-product risk
+
multi-intervention EV/NBA
+
incremental recovery measurement
```

### Versus Razorpay Agent Studio

Agent Studio provides specialist recovery agents.

Our proposed layer:

```text
cross-product prioritization
+
measurement
+
decision intelligence
```

while still relying on the same principle of bounded/gated financial actions.

---

# 45. FINAL DEFINITION OF DONE

The MVP is done only when ALL of the following are true:

- [ ] Real Razorpay Test Mode integration works.
- [ ] Webhooks are verified and deduplicated.
- [ ] Recovery Cases are persisted.
- [ ] Revenue at Risk is calculated from real case data.
- [ ] Cases are ranked by expected recovery opportunity.
- [ ] AI/ML generates action-aware recovery predictions.
- [ ] Next-best-action is selected.
- [ ] Deterministic guardrails gate execution.
- [ ] Recovery Link execution works in Razorpay Test Mode.
- [ ] Outcome is observed and reconciled.
- [ ] Recovery amount is calculated from actual captured outcome.
- [ ] Control and treatment groups can be run.
- [ ] Incremental recovery is measured.
- [ ] Rule-based baseline exists.
- [ ] Evaluation harness is reproducible.
- [ ] Audit trail is viewable.
- [ ] A blocked action is demonstrated.
- [ ] No duplicate charge/link behavior occurs.
- [ ] LLM failure cannot bypass financial safety.
- [ ] README explains setup and architecture.
- [ ] Docker Compose starts the system.
- [ ] Tests pass.
- [ ] Demo scenario is deterministic.

---

# 46. CODEX EXECUTION PROMPT

Use this as the first prompt when starting implementation.

```text
You are the primary coding agent for this repository.

The repository contains:
IMPLEMENTATION_PLAN.md

This file is the source of truth for the project's architecture, scope, constraints, research findings, engineering contracts, evaluation methodology, and implementation phases.

Your job is NOT to implement the entire project at once.

FIRST:
1. Read IMPLEMENTATION_PLAN.md completely.
2. Inspect the repository.
3. Summarize:
   - product goal
   - locked MVP scope
   - architecture
   - key domain entities
   - Razorpay integration constraints
   - safety model
   - evaluation model
   - current implementation phase
4. Identify any ambiguity or conflict between the plan and the existing repository.
5. Do not invent missing Razorpay APIs or capabilities.

THEN:
Implement ONLY the current phase specified in the plan.

For every phase:
1. Analyze first.
2. Propose the implementation steps.
3. Implement the smallest complete version.
4. Add/modify tests.
5. Run tests.
6. Validate integration boundaries.
7. Update documentation/status.
8. Report exactly what changed and whether the phase acceptance criteria are satisfied.

IMPORTANT ARCHITECTURE RULE:
AI/ML may recommend an action.
The deterministic policy engine must approve it.
Only validated actions may reach the Razorpay adapter.
The AI must never directly execute arbitrary financial operations.

IMPORTANT SCOPE RULE:
Do not add out-of-scope features unless explicitly requested:
- voice
- Hinglish
- mandates
- full subscriptions
- full B2B collections
- multi-agent orchestration
- live payments
- Kubernetes
- unnecessary microservices

IMPORTANT RAZORPAY RULE:
There is no assumed generic failed-payment retry endpoint.
For one-time failed payments, use the supported recovery Payment Link flow defined in the plan.
Verify all current API behavior against official documentation before implementation.

IMPORTANT EVALUATION RULE:
Do not fabricate recovery metrics.
All business metrics must come from actual simulator/Razorpay test outcomes.
Incremental recovered revenue must distinguish treatment outcomes from control outcomes.

IMPORTANT SAFETY RULE:
If an action is unsafe, unsupported, unauthorized, duplicated, expired, or blocked by policy:
STOP or ESCALATE.
Never “try anyway.”

Start by analyzing Phase 0 only.
Do not implement Phase 1 until Phase 0 acceptance criteria are satisfied.
```

---

# 47. PHASE HANDOFF PROTOCOL FOR CODEX

At the end of every phase, Codex should produce:

```text
PHASE:
Status: PASS / BLOCKED

Implemented:
- ...

Files changed:
- ...

Tests:
- ...

Validation:
- ...

Known limitations:
- ...

Architecture decisions:
- ...

Next phase:
- ...

Ready for next phase:
YES / NO
```

If `NO`, do not proceed.

---

# 48. R&D SOURCE BASIS

The project decisions were derived from the project's research set covering:

1. Revenue-recovery problem analysis
2. Razorpay API/payment ecosystem
3. Payment failure classification and recoverability
4. Competitive/market analysis
5. Primary-source gap validation
6. Product decision framework
7. Razorpay integration contract

Important conclusions from those studies:

- Revenue recovery is a decision-and-action problem, not merely a detection problem.
- Razorpay provides execution rails and structured failure signals.
- Failed one-time payments cannot be treated as directly retryable payment objects.
- Payment Links are a practical one-time recovery primitive.
- Webhooks require signature verification, deduplication, and reconciliation.
- Generic intelligent retry is not novel.
- Hyperswitch is a direct benchmark for predictive retry/bounded retry behavior.
- B2B next-best-action is already implemented by established platforms.
- Cross-product revenue-at-risk remains a meaningful product opportunity.
- Incremental measurement of recovery interventions is a particularly defensible differentiation hypothesis.
- AI/ML should recommend; deterministic policy should govern; payment APIs should execute.
- Synthetic data plus real Razorpay Test Mode provides a practical evaluation architecture.

---

# 49. IMPORTANT RESEARCH CAVEAT

The research deliberately distinguishes:

- official source-backed facts
- engineering inference
- product recommendation

That distinction must remain intact.

Do not turn an inference into a regulatory or vendor fact inside the code, README, or pitch.

Where exact current Razorpay behavior matters, current official documentation is the final authority.

---

# 50. FINAL PRODUCT THESIS

The project is ultimately trying to prove this:

> A merchant should not have to blindly chase every failed payment or abandoned checkout. A recovery system should understand which revenue is at risk, estimate which interventions are economically worthwhile, choose the best permitted action, execute it safely through payment infrastructure, and prove how much additional revenue that intervention created.

The product should therefore be understood as:

```text
                  REVENUE RECOVERY
                         │
               ┌─────────┴─────────┐
               ▼                   ▼
          SEE THE RISK         MEASURE IMPACT
               │                   │
               ▼                   ▲
        DECIDE WHAT TO DO           │
               │                   │
               ▼                   │
        GATE THE ACTION             │
               │                   │
               ▼                   │
         EXECUTE SAFELY             │
               │                   │
               └──────► OUTCOME ────┘
```

The strongest product statement remains:

> **We are not another dunning or retry engine. We are a revenue-recovery decision and measurement layer that sits on top of Razorpay's payment rails.**

---

# 51. BUILD ORDER SUMMARY

For quick reference:

```text
PHASE 0   Foundation
PHASE 1   Domain + DB
PHASE 2   Razorpay Adapter
PHASE 3   Webhooks
PHASE 4   Recovery Cases
PHASE 5   Revenue-at-Risk
PHASE 6   Rule Baseline
PHASE 7   Simulator
PHASE 8   ML
PHASE 9   EV + NBA
PHASE 10  Guardrails
PHASE 11  Real Recovery Execution
PHASE 12  Incremental Measurement
PHASE 13  LLM Explanation
PHASE 14  Audit UI
PHASE 15  Product UI
PHASE 16  Evaluation Harness
PHASE 17  Failure Hardening
PHASE 18  Security
PHASE 19  Final Demo
```

**Do not skip ahead merely because a later phase looks exciting.**

The correct workflow is:

```text
Understand
→ Implement
→ Test
→ Validate
→ Freeze
→ Next Phase
```

---

## END OF IMPLEMENTATION PLAN
