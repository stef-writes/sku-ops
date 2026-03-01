"""Factory for payment gateway. Uses PAYMENT_ADAPTER env (stub|stripe) or falls back to stripe when configured."""
import os

from adapters.stub_payment import StubPaymentAdapter


def get_payment_gateway(webhook_url: str = ""):
    """
    Return the active payment gateway.
    - PAYMENT_ADAPTER=stub -> StubPaymentAdapter (dev/tests)
    - PAYMENT_ADAPTER=stripe or unset + STRIPE_API_KEY set -> StripePaymentAdapter
    - Otherwise -> StubPaymentAdapter (safe fallback)
    """
    adapter = os.environ.get("PAYMENT_ADAPTER", "").lower().strip()
    stripe_key = os.environ.get("STRIPE_API_KEY", "").strip()

    if adapter == "stub":
        return StubPaymentAdapter()
    if stripe_key and (adapter == "stripe" or not adapter):
        try:
            from adapters.stripe_payment import StripePaymentAdapter
            return StripePaymentAdapter(api_key=stripe_key, webhook_url=webhook_url)
        except ImportError:
            pass
    return StubPaymentAdapter()
