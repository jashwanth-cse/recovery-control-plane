import httpx

from app.core.config import Settings, get_settings
from app.integrations.razorpay.client import RazorpayClient
from app.integrations.razorpay.errors import RazorpayConfigurationError
from app.integrations.razorpay.gateway import RazorpayPaymentGateway


def create_razorpay_gateway(
    settings: Settings | None = None,
    *,
    transport: httpx.BaseTransport | None = None,
) -> RazorpayPaymentGateway:
    active_settings = settings or get_settings()
    key_id = active_settings.razorpay_key_id
    secret = active_settings.razorpay_key_secret
    if not key_id or secret is None or not secret.get_secret_value():
        raise RazorpayConfigurationError(
            "Razorpay Test Mode credentials are not configured."
        )
    if active_settings.razorpay_test_mode_only and not key_id.startswith("rzp_test_"):
        raise RazorpayConfigurationError(
            "Only Razorpay Test Mode credentials are allowed."
        )

    client = RazorpayClient(
        key_id=key_id,
        key_secret=secret.get_secret_value(),
        base_url=active_settings.razorpay_api_base_url,
        timeout_seconds=active_settings.razorpay_timeout_seconds,
        transport=transport,
    )
    return RazorpayPaymentGateway(client)
