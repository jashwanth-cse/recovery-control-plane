# Recovery Case Engine

Phase 4 turns reconciled Razorpay state and deterministic unpaid-order scans into
persistent Recovery Cases. It does not make AI decisions or execute payment
actions.

## Case Sources

- `PAYMENT`: a current `failed` payment from a verified `payment.failed` event.
- `ORDER`: a `created` or `attempted` order with positive `amount_due` older than
  `ABANDONED_ORDER_AGE_MINUTES`.
- `PAYMENT_LINK`: a partially paid or expired link with a positive remaining
  balance.

Cases are unique by merchant, source type, and source ID. Repeated webhooks and
repeated unpaid-order scans return the existing case rather than creating another.

## Amount At Risk

- Failed payment: payment amount, capped by positive order amount due when an
  order is available.
- Unpaid order: current `amount_due`.
- Payment Link: `amount - amount_paid`.

Amounts are stored in the currency's smallest unit, consistent with Razorpay API
responses and the existing domain schema.

## Ownership

`Merchant.razorpay_account_id` maps a webhook account to one merchant. The mapped
account and any known local payment, order, or Payment Link owner must agree. A
conflict fails processing and cannot create a cross-merchant case.

## Recovery Window And Terminal Conditions

`RECOVERY_WINDOW_DAYS` defaults to 14. Failed-payment windows begin at the event
timestamp; scan- and Payment Link-created windows begin when the signal is
observed. Active cases become `EXPIRED` at the window end.

Cases become terminal when:

- the related payment/order/Payment Link is reconciled as paid (`RECOVERED`)
- the merchant is inactive (`STOPPED`)
- the customer has opted out (`STOPPED`)
- the linked Payment Link is cancelled (`STOPPED`)
- the link or recovery window expires (`EXPIRED`)

Terminal cases do not reopen on late or out-of-order events. Creation and status
changes append `audit_events` records with trigger, reason, and reference IDs.

## API

Dashboard consumers can query active cases:

```http
GET /api/cases?active_only=true
GET /api/cases?active_only=true&merchant_id=<uuid>
```

The query persists overdue-case expiration before returning nonterminal cases.
Eligible unpaid orders can be scanned explicitly:

```http
POST /api/cases/scan-unpaid-orders
POST /api/cases/scan-unpaid-orders?merchant_id=<uuid>
```

The scan is deterministic and idempotent. Scheduling it as a background job is a
later operational-hardening concern.
