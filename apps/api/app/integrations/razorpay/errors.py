class RazorpayError(Exception):
    """Base exception for normalized Razorpay adapter failures."""


class RazorpayConfigurationError(RazorpayError):
    pass


class RazorpayRequestValidationError(RazorpayError):
    pass


class RazorpayTransportError(RazorpayError):
    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


class RazorpayAPIError(RazorpayError):
    def __init__(
        self,
        *,
        status_code: int,
        code: str | None,
        description: str,
        retryable: bool,
    ) -> None:
        super().__init__(description)
        self.status_code = status_code
        self.code = code
        self.description = description
        self.retryable = retryable


class RazorpayAuthenticationError(RazorpayAPIError):
    pass


class RazorpayRateLimitError(RazorpayAPIError):
    pass


class RazorpayServiceError(RazorpayAPIError):
    pass


class RazorpayResponseValidationError(RazorpayError):
    pass
