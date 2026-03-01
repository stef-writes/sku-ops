"""Payment routes - uses PaymentGateway port (Stripe or stub adapter)."""
import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request

from adapters.payment_factory import get_payment_gateway
from auth import get_current_user
from repositories import invoice_repo, payment_repo, withdrawal_repo

from .schemas import CreatePaymentRequest

import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("/create-checkout")
async def create_payment_checkout(data: CreatePaymentRequest, request: Request, current_user: dict = Depends(get_current_user)):
    """Create a checkout session for a withdrawal (Stripe or stub adapter)."""

    withdrawal = await withdrawal_repo.get_by_id(data.withdrawal_id)
    if not withdrawal:
        raise HTTPException(status_code=404, detail="Withdrawal not found")

    if withdrawal.get("payment_status") == "paid":
        raise HTTPException(status_code=400, detail="This withdrawal is already paid")

    origin = data.origin_url.rstrip("/")
    success_url = f"{origin}/pos?payment=success&session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{origin}/pos?payment=cancelled"

    host_url = str(request.base_url)
    webhook_url = f"{host_url}api/webhook/stripe"
    gateway = get_payment_gateway(webhook_url=webhook_url)

    amount = float(withdrawal.get("total", 0))
    metadata = {
        "withdrawal_id": data.withdrawal_id,
        "contractor_id": withdrawal.get("contractor_id", ""),
        "job_id": withdrawal.get("job_id", ""),
        "user_id": current_user["id"],
    }

    try:
        result = await gateway.create_checkout_session(
            amount=amount,
            currency="usd",
            success_url=success_url,
            cancel_url=cancel_url,
            metadata=metadata,
        )

        payment_record = {
            "id": str(uuid.uuid4()),
            "session_id": result.session_id,
            "withdrawal_id": data.withdrawal_id,
            "user_id": current_user["id"],
            "contractor_id": withdrawal.get("contractor_id", ""),
            "amount": amount,
            "currency": "usd",
            "metadata": metadata,
            "payment_status": "pending",
            "status": "initiated",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await payment_repo.insert(payment_record)

        return {
            "checkout_url": result.url,
            "session_id": result.session_id,
        }
    except Exception as e:
        logger.error(f"Checkout error: {e}")
        raise HTTPException(status_code=500, detail=f"Payment processing error: {str(e)}")


@router.get("/status/{session_id}")
async def get_payment_status(session_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    """Check the status of a payment session and update records."""
    host_url = str(request.base_url)
    webhook_url = f"{host_url}api/webhook/stripe"
    gateway = get_payment_gateway(webhook_url=webhook_url)

    try:
        status = await gateway.get_checkout_status(session_id)

        payment = await payment_repo.get_by_session_id(session_id)

        if payment and status.payment_status == "paid" and payment.get("payment_status") != "paid":
            paid_at = datetime.now(timezone.utc).isoformat()
            await payment_repo.update_status(session_id, "paid", "complete", paid_at)
            if payment.get("withdrawal_id"):
                await withdrawal_repo.mark_paid(payment["withdrawal_id"], paid_at)
                await invoice_repo.mark_paid_for_withdrawal(payment["withdrawal_id"])
        elif status.status == "expired":
            await payment_repo.update_status(session_id, "expired", "expired")

        return {
            "status": status.status,
            "payment_status": status.payment_status,
            "amount_total": status.amount_total,
            "currency": status.currency,
            "withdrawal_id": payment.get("withdrawal_id") if payment else None,
        }
    except Exception as e:
        logger.error(f"Payment status check error: {e}")
        raise HTTPException(status_code=500, detail=f"Error checking payment status: {str(e)}")
