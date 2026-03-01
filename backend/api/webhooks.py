"""Webhook routes - uses PaymentGateway port (Stripe or stub)."""
import logging

from fastapi import APIRouter, Request

from adapters.payment_factory import get_payment_gateway
from repositories import invoice_repo, payment_repo, withdrawal_repo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["webhooks"])


@router.post("/stripe")
async def stripe_webhook(request: Request):
    """Handle payment provider webhooks (Stripe or stub)."""
    try:
        body = await request.body()
        signature = request.headers.get("Stripe-Signature")
        host_url = str(request.base_url)
        webhook_url = f"{host_url}api/webhook/stripe"
        gateway = get_payment_gateway(webhook_url=webhook_url)

        webhook_response = await gateway.handle_webhook(body, signature)

        if webhook_response.payment_status == "paid" and webhook_response.session_id:
            session_id = webhook_response.session_id
            payment = await payment_repo.get_by_session_id(session_id)

            if payment and payment.get("payment_status") != "paid":
                from datetime import datetime, timezone

                paid_at = datetime.now(timezone.utc).isoformat()
                await payment_repo.update_status(session_id, "paid", "complete", paid_at)
                if payment.get("withdrawal_id"):
                    await withdrawal_repo.mark_paid(payment["withdrawal_id"], paid_at)
                    await invoice_repo.mark_paid_for_withdrawal(payment["withdrawal_id"])

        return {"received": True}
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return {"received": True, "error": str(e)}

