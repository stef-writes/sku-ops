from pydantic import BaseModel


class CreatePaymentRequest(BaseModel):
    withdrawal_id: str
    origin_url: str
