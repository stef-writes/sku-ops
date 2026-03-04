"""Payment gateway port - abstraction for payment providers (Stripe, stub, etc.)."""
from typing import Any, Optional, Protocol


class CheckoutResult:
    """Result of creating a checkout session."""
    session_id: str
    url: str

    def __init__(self, session_id: str, url: str):
        self.session_id = session_id
        self.url = url


class CheckoutStatusResult:
    """Result of checking payment status."""
    status: str  # e.g. "complete", "expired", "open"
    payment_status: str  # e.g. "paid", "unpaid", "pending"
    amount_total: float
    currency: str

    def __init__(self, status: str, payment_status: str, amount_total: float = 0, currency: str = "usd"):
        self.status = status
        self.payment_status = payment_status
        self.amount_total = amount_total
        self.currency = currency


class WebhookResult:
    """Result of handling a payment webhook."""
    session_id: str
    payment_status: str

    def __init__(self, session_id: str, payment_status: str):
        self.session_id = session_id
        self.payment_status = payment_status


class PaymentGateway(Protocol):
    """Port for payment processing. Implementations: Stripe, Stub."""

    async def create_checkout_session(
        self,
        amount: float,
        currency: str,
        success_url: str,
        cancel_url: str,
        metadata: dict[str, Any],
    ) -> CheckoutResult:
        """Create a payment checkout session. Returns session_id and redirect URL."""
        ...

    async def get_checkout_status(self, session_id: str) -> CheckoutStatusResult:
        """Get the status of a checkout session."""
        ...

    async def handle_webhook(self, body: bytes, signature: Optional[str]) -> WebhookResult:
        """Handle incoming webhook from payment provider."""
        ...
