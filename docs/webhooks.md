# Razorpay Webhook Ingestion

Phase 3 exposes `POST /webhooks/razorpay` for Razorpay Test Mode events.

## Security Contract

The endpoint requires:

```text
X-Razorpay-Signature
x-razorpay-event-id
```

The signature is verified with HMAC-SHA256 using the exact raw request bytes and
`RAZORPAY_WEBHOOK_SECRET`. JSON parsing and persistence happen only after a valid
signature. `RAZORPAY_WEBHOOK_PREVIOUS_SECRET` can temporarily validate retries
created before a webhook-secret rotation.

The default maximum body size is 1 MB and is configurable with
`RAZORPAY_WEBHOOK_MAX_BODY_BYTES` up to 5 MB. Missing configuration fails closed.

Official references checked on 2026-09-01:

- [Validate and test webhooks](https://razorpay.com/docs/webhooks/validate-test/)
- [Webhook best practices](https://razorpay.com/docs/webhooks/best-practices/)
- [Payment webhook events](https://razorpay.com/docs/webhooks/payments/)
- [Payment Link webhook events](https://razorpay.com/docs/webhooks/payment-links/)

## Supported Events

```text
payment.failed
payment.authorized
payment.captured
payment_link.paid
payment_link.partially_paid
payment_link.cancelled
payment_link.expired
```

Other correctly signed event types are persisted as `IGNORED`. They do not call
the payment gateway.

## Processing States

```text
RECEIVED → PROCESSING → PROCESSED
                      → FAILED
RECEIVED → IGNORED
```

`(provider, event_id)` is unique. A duplicate of a processed, ignored, or active
event returns `200` without another reconciliation. A duplicate of a failed event
retries reconciliation and increments `processing_attempts`.

Reconciliation reads current Razorpay state for the referenced payment, order,
or Payment Link. This prevents a late webhook from overwriting newer local state.
Only a minimized state snapshot is stored as reconciliation evidence.

## Recovery Case Handoff

After reconciliation, Phase 4 consumes only current provider state and the
verified event envelope. It can create a source-backed Recovery Case, correlate a
Payment Link, or apply a terminal recovery, stop, or expiration transition. A
mapped webhook account and any known local resource owner must agree.

Webhook processing still does not create, notify, or cancel a Payment Link, run an
AI decision, execute a financial action, or aggregate revenue. Those remain later
phase responsibilities.
