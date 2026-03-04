"""Webhook routes - uses PaymentGateway port (Stripe or stub)."""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Request

from finance.adapters.payment_factory import get_payment_gateway
from finance.infrastructure.invoice_repo import invoice_repo
from finance.infrastructure.payment_repo import payment_repo
from operations.application.queries import mark_withdrawal_paid

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["webhooks"])


@router.post("/stripe")
async def stripe_webhook(request: Request):
    """Handle payment provider webhooks (Stripe or stub)."""
    try:
        body = await request.body()
        signature = request.headers.get("Stripe-Signature")
        base = str(request.base_url).rstrip("/")
        webhook_url = f"{base}/api/webhook/stripe"
        gateway = get_payment_gateway(webhook_url=webhook_url)

        webhook_response = await gateway.handle_webhook(body, signature)

        if webhook_response.payment_status == "paid" and webhook_response.session_id:
            session_id = webhook_response.session_id
            payment = await payment_repo.get_by_session_id(session_id)

            if payment and payment.get("payment_status") != "paid":
                paid_at = datetime.now(timezone.utc).isoformat()
                await payment_repo.update_status(session_id, "paid", "complete", paid_at)
                if payment.get("withdrawal_id"):
                    await mark_withdrawal_paid(payment["withdrawal_id"], paid_at)
                    await invoice_repo.mark_paid_for_withdrawal(payment["withdrawal_id"])

        return {"received": True}
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        raise

