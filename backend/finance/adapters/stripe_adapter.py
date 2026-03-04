"""Stripe payment adapter - implements PaymentGateway using emergentintegrations Stripe checkout."""

from finance.ports.payment_port import CheckoutResult, CheckoutStatusResult, WebhookResult


class StripePaymentAdapter:
    """Payment gateway implementation using Stripe."""

    def __init__(self, api_key: str, webhook_url: str):
        self._api_key = api_key
        self._webhook_url = webhook_url
        self._client = None

    def _get_client(self):
        if self._client is None:
            from emergentintegrations.payments.stripe.checkout import StripeCheckout
            self._client = StripeCheckout(api_key=self._api_key, webhook_url=self._webhook_url)
        return self._client

    async def create_checkout_session(
        self,
        amount: float,
        currency: str,
        success_url: str,
        cancel_url: str,
        metadata: dict,
    ) -> CheckoutResult:
        from emergentintegrations.payments.stripe.checkout import CheckoutSessionRequest
        client = self._get_client()
        request = CheckoutSessionRequest(
            amount=amount,
            currency=currency,
            success_url=success_url,
            cancel_url=cancel_url,
            metadata=metadata,
        )
        response = await client.create_checkout_session(request)
        return CheckoutResult(session_id=response.session_id, url=response.url)

    async def get_checkout_status(self, session_id: str) -> CheckoutStatusResult:
        client = self._get_client()
        response = await client.get_checkout_status(session_id)
        return CheckoutStatusResult(
            status=response.status,
            payment_status=response.payment_status,
            amount_total=getattr(response, "amount_total", 0) or 0,
            currency=getattr(response, "currency", "usd") or "usd",
        )

    async def handle_webhook(self, body: bytes, signature: str | None) -> WebhookResult:
        client = self._get_client()
        response = await client.handle_webhook(body, signature)
        return WebhookResult(session_id=response.session_id, payment_status=response.payment_status)
