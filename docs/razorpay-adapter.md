# Razorpay Adapter Contract

Phase 2 implements a narrow Razorpay Payment Gateway adapter for Test Mode. It
does not expose raw HTTP to recovery business logic and does not implement a
generic failed-payment retry operation.

## Supported Capabilities

The following operations were checked against Razorpay's official API reference
on 2026-09-01:

| Gateway capability | Razorpay operation |
| --- | --- |
| `get_order` | `GET /v1/orders/:id` |
| `get_payment` | `GET /v1/payments/:id` |
| `create_payment_link` | `POST /v1/payment_links` |
| `notify_payment_link` | `POST /v1/payment_links/:id/notify_by/:medium` |
| `cancel_payment_link` | `POST /v1/payment_links/:id/cancel` |

Official references:

- [API authentication](https://razorpay.com/docs/api/authentication/)
- [Fetch an order](https://razorpay.com/docs/api/orders/fetch-with-id/)
- [Fetch a payment](https://razorpay.com/docs/api/payments/fetch-with-id/)
- [Create a Standard Payment Link](https://razorpay.com/docs/api/payments/payment-links/create-standard/)
- [Send or resend Payment Link notifications](https://razorpay.com/docs/api/payments/payment-links/resend/)
- [Cancel a Standard Payment Link](https://razorpay.com/docs/api/payments/payment-links/cancel-standard/)

## Configuration

The adapter reads these environment variables through application settings:

```text
RAZORPAY_KEY_ID
RAZORPAY_KEY_SECRET
RAZORPAY_API_BASE_URL=https://api.razorpay.com/v1
RAZORPAY_TIMEOUT_SECONDS=10
RAZORPAY_TEST_MODE_ONLY=true
```

Credentials are optional while the rest of the application starts. Creating a
gateway without credentials fails closed. With `RAZORPAY_TEST_MODE_ONLY=true`,
the factory rejects any key that does not use Razorpay's `rzp_test_` prefix.
The key secret is represented as a Pydantic `SecretStr` and is never included in
normalized adapter exceptions.

## Application Boundary

Application services should depend on `PaymentGateway` from
`app.integrations.payment_gateway`. A configured adapter is created with
`create_razorpay_gateway`; business code must not instantiate an HTTP client or
construct Razorpay URLs directly.

Request and response objects are validated Pydantic models. Unknown response
fields are ignored for forward compatibility, while required monetary and state
fields are validated before they enter application logic.

Provider failures are normalized into configuration, request-validation,
transport, authentication, rate-limit, service, API, and response-validation
exceptions. The normalized errors do not retain raw response bodies.

## Test Strategy

Contract tests use `httpx.MockTransport` to inspect Basic Auth, HTTP methods,
paths, request bodies, typed response parsing, malformed responses, and error
normalization. They do not require credentials and never contact Razorpay.

An optional real Test Mode smoke test requires merchant-owned test credentials
and existing test resource IDs. It is intentionally not run automatically
because creating, notifying, and cancelling links changes the merchant's Razorpay
Test Mode account state.
