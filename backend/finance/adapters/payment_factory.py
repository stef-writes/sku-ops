"""Factory for payment gateway. Uses stub adapter only."""
from finance.adapters.stub_payment import StubPaymentAdapter


def get_payment_gateway(webhook_url: str = ""):
    """Return the active payment gateway. Always stub."""
    return StubPaymentAdapter()
