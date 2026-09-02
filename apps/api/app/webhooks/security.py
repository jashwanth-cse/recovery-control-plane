import hashlib
import hmac
from collections.abc import Iterable


def verify_razorpay_signature(
    raw_body: bytes,
    received_signature: str,
    secrets: Iterable[str],
) -> bool:
    if not received_signature:
        return False
    for secret in secrets:
        if not secret:
            continue
        expected = hmac.new(
            secret.encode("utf-8"), raw_body, hashlib.sha256
        ).hexdigest()
        if hmac.compare_digest(expected, received_signature):
            return True
    return False
