"""Stub payment adapter for dev and tests. No-op payment flow with fake session IDs."""
import uuid

from ports.payment import CheckoutResult, CheckoutStatusResult, WebhookResult


class StubPaymentAdapter:
    """In-memory stub for payment gateway. Use when STRIPE not configured or PAYMENT_ADAPTER=stub."""

    def __init__(self):
        self._sessions: dict[str, dict] = {}  # session_id -> {amount, metadata, etc}

    async def create_checkout_session(
        self,
        amount: float,
        currency: str,
        success_url: str,
        cancel_url: str,
        metadata: dict,
    ) -> CheckoutResult:
        session_id = f"stub_{uuid.uuid4().hex[:24]}"
        self._sessions[session_id] = {
            "amount": amount,
            "currency": currency,
            "metadata": metadata,
            "payment_status": "pending",
        }
        # Return a data URL or placeholder - frontend can mock redirect
        url = success_url.replace("{CHECKOUT_SESSION_ID}", session_id)
        return CheckoutResult(session_id=session_id, url=url)

    async def get_checkout_status(self, session_id: str) -> CheckoutStatusResult:
        session = self._sessions.get(session_id)
        if not session:
            return CheckoutStatusResult(status="expired", payment_status="expired", amount_total=0, currency="usd")
        # Stub: treat known sessions as complete/paid (simulates user completed checkout in dev)
        return CheckoutStatusResult(
            status="complete",
            payment_status="paid",
            amount_total=session["amount"],
            currency=session.get("currency", "usd"),
        )

    async def handle_webhook(self, body: bytes, signature: str | None) -> WebhookResult:
        # Stub ignores webhook body; real adapter would verify signature and parse
        return WebhookResult(session_id="", payment_status="pending")
