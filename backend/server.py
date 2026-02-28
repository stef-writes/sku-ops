import asyncio
from fastapi import FastAPI, APIRouter, HTTPException, Depends, UploadFile, File, Request
from fastapi.responses import StreamingResponse
from starlette.middleware.cors import CORSMiddleware
import os
import logging
import json
import re
import csv
import io
import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Tuple

from pydantic import BaseModel

# Stripe integration (optional - not on public PyPI; used in Emergent builds)
try:
    from emergentintegrations.payments.stripe.checkout import (
        StripeCheckout,
        CheckoutSessionResponse,
        CheckoutStatusResponse,
        CheckoutSessionRequest,
    )
    HAS_EMERGENT_STRIPE = True
except ImportError:
    StripeCheckout = CheckoutSessionResponse = CheckoutStatusResponse = CheckoutSessionRequest = None
    HAS_EMERGENT_STRIPE = False

from db import init_db, close_db
from repositories import (
    user_repo,
    department_repo,
    vendor_repo,
    product_repo,
    withdrawal_repo,
    payment_repo,
    sku_repo,
)
from auth import (
    hash_password,
    verify_password,
    create_token,
    get_current_user,
    require_role,
)
from models import (
    ROLES,
    User,
    UserCreate,
    UserUpdate,
    UserLogin,
    Department,
    DepartmentCreate,
    Vendor,
    VendorCreate,
    Product,
    ProductCreate,
    ProductUpdate,
    ExtractedProduct,
    MaterialWithdrawal,
    MaterialWithdrawalCreate,
)
from models.product import ALLOWED_BASE_UNITS
from services.uom_classifier import classify_uom, classify_uom_batch
from services.inventory import (
    process_withdrawal_stock_changes,
    process_import_stock_changes,
    get_stock_history,
    InsufficientStockError,
)

# Create the main app
app = FastAPI()
api_router = APIRouter(prefix="/api")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# ==================== SKU GENERATOR ====================

async def generate_sku(department_code: str) -> str:
    number = await sku_repo.increment_and_get(department_code)
    return f"{department_code}-{str(number).zfill(5)}"

# ==================== AUTH ROUTES ====================

@api_router.post("/auth/register")
async def register(data: UserCreate):
    existing = await user_repo.get_by_email(data.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    if data.role not in ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {ROLES}")

    user = User(
        email=data.email,
        name=data.name,
        role=data.role,
        company=data.company,
        billing_entity=data.billing_entity,
        phone=data.phone,
    )
    user_dict = user.model_dump()
    user_dict["password"] = hash_password(data.password)

    await user_repo.insert(user_dict)

    token = create_token(user.id, user.email, user.role)
    return {"token": token, "user": user.model_dump()}


@api_router.post("/auth/login")
async def login(data: UserLogin):
    user = await user_repo.get_by_email(data.email)
    if not user or not verify_password(data.password, user.get("password", "")):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.get("is_active", True):
        raise HTTPException(status_code=401, detail="Account is disabled")

    token = create_token(user["id"], user["email"], user["role"])
    user_response = {k: v for k, v in user.items() if k not in ["password"]}
    return {"token": token, "user": user_response}

@api_router.get("/auth/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    return current_user

# ==================== CONTRACTOR MANAGEMENT (Admin Only) ====================

@api_router.get("/contractors")
async def get_contractors(current_user: dict = Depends(require_role("admin", "warehouse_manager"))):
    return await user_repo.list_contractors()


@api_router.post("/contractors")
async def create_contractor(data: UserCreate, current_user: dict = Depends(require_role("admin"))):
    existing = await user_repo.get_by_email(data.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    contractor = User(
        email=data.email,
        name=data.name,
        role="contractor",
        company=data.company or "Independent",
        billing_entity=data.billing_entity or data.company or "Independent",
        phone=data.phone,
    )
    contractor_dict = contractor.model_dump()
    contractor_dict["password"] = hash_password(data.password)

    await user_repo.insert(contractor_dict)

    return {k: v for k, v in contractor_dict.items() if k != "password"}


@api_router.put("/contractors/{contractor_id}")
async def update_contractor(contractor_id: str, data: UserUpdate, current_user: dict = Depends(require_role("admin"))):
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    contractor = await user_repo.get_by_id(contractor_id)
    if not contractor or contractor.get("role") != "contractor":
        raise HTTPException(status_code=404, detail="Contractor not found")

    result = await user_repo.update(contractor_id, update_data)
    return {k: v for k, v in result.items() if k != "password"}


@api_router.delete("/contractors/{contractor_id}")
async def delete_contractor(contractor_id: str, current_user: dict = Depends(require_role("admin"))):
    deleted = await user_repo.delete_contractor(contractor_id)
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Contractor not found")
    return {"message": "Contractor deleted"}

# ==================== DEPARTMENT ROUTES ====================

@api_router.get("/departments", response_model=List[Department])
async def get_departments(current_user: dict = Depends(get_current_user)):
    return await department_repo.list_all()


@api_router.post("/departments", response_model=Department)
async def create_department(data: DepartmentCreate, current_user: dict = Depends(require_role("admin", "warehouse_manager"))):
    existing = await department_repo.get_by_code(data.code)
    if existing:
        raise HTTPException(status_code=400, detail="Department code already exists")

    dept = Department(
        name=data.name,
        code=data.code.upper(),
        description=data.description or "",
    )
    await department_repo.insert(dept.model_dump())
    return dept


@api_router.put("/departments/{dept_id}", response_model=Department)
async def update_department(dept_id: str, data: DepartmentCreate, current_user: dict = Depends(require_role("admin", "warehouse_manager"))):
    result = await department_repo.update(dept_id, data.name, data.description or "")
    if not result:
        raise HTTPException(status_code=404, detail="Department not found")
    return result


@api_router.delete("/departments/{dept_id}")
async def delete_department(dept_id: str, current_user: dict = Depends(require_role("admin"))):
    product_count = await department_repo.count_products_by_department(dept_id)
    if product_count > 0:
        raise HTTPException(status_code=400, detail="Cannot delete department with products")

    deleted = await department_repo.delete(dept_id)
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Department not found")
    return {"message": "Department deleted"}

# ==================== VENDOR ROUTES ====================

@api_router.get("/vendors", response_model=List[Vendor])
async def get_vendors(current_user: dict = Depends(require_role("admin", "warehouse_manager"))):
    return await vendor_repo.list_all()


@api_router.post("/vendors", response_model=Vendor)
async def create_vendor(data: VendorCreate, current_user: dict = Depends(require_role("admin", "warehouse_manager"))):
    vendor = Vendor(**data.model_dump())
    await vendor_repo.insert(vendor.model_dump())
    return vendor


@api_router.put("/vendors/{vendor_id}", response_model=Vendor)
async def update_vendor(vendor_id: str, data: VendorCreate, current_user: dict = Depends(require_role("admin", "warehouse_manager"))):
    result = await vendor_repo.update(vendor_id, data.model_dump())
    if not result:
        raise HTTPException(status_code=404, detail="Vendor not found")
    return result


@api_router.delete("/vendors/{vendor_id}")
async def delete_vendor(vendor_id: str, current_user: dict = Depends(require_role("admin"))):
    deleted = await vendor_repo.delete(vendor_id)
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Vendor not found")
    return {"message": "Vendor deleted"}

# ==================== PRODUCT ROUTES ====================

@api_router.get("/products", response_model=List[Product])
async def get_products(
    department_id: Optional[str] = None,
    search: Optional[str] = None,
    low_stock: bool = False,
    current_user: dict = Depends(get_current_user),
):
    return await product_repo.list_products(
        department_id=department_id,
        search=search,
        low_stock=low_stock,
    )


@api_router.get("/products/{product_id}", response_model=Product)
async def get_product(product_id: str, current_user: dict = Depends(get_current_user)):
    product = await product_repo.get_by_id(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@api_router.get("/products/{product_id}/stock-history")
async def get_product_stock_history(
    product_id: str,
    limit: int = 50,
    current_user: dict = Depends(require_role("admin", "warehouse_manager")),
):
    """Get stock transaction history for a product (stock ledger)."""
    product = await product_repo.get_by_id(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    history = await get_stock_history(product_id=product_id, limit=limit)
    return {"product_id": product_id, "sku": product.get("sku"), "history": history}


class SuggestUomRequest(BaseModel):
    name: str
    description: Optional[str] = None


@api_router.post("/products/suggest-uom")
async def suggest_uom(data: SuggestUomRequest, current_user: dict = Depends(require_role("admin", "warehouse_manager"))):
    """Use AI to suggest base_unit, sell_uom, pack_qty from product name."""
    result = await classify_uom(data.name, data.description)
    return result


@api_router.post("/products", response_model=Product)
async def create_product(data: ProductCreate, current_user: dict = Depends(require_role("admin", "warehouse_manager"))):
    department = await department_repo.get_by_id(data.department_id)
    if not department:
        raise HTTPException(status_code=400, detail="Department not found")

    vendor_name = ""
    if data.vendor_id:
        vendor = await vendor_repo.get_by_id(data.vendor_id)
        if vendor:
            vendor_name = vendor.get("name", "")

    sku = await generate_sku(department["code"])

    product = Product(
        sku=sku,
        name=data.name,
        description=data.description or "",
        price=data.price,
        cost=data.cost,
        quantity=data.quantity,
        min_stock=data.min_stock,
        department_id=data.department_id,
        department_name=department["name"],
        vendor_id=data.vendor_id,
        vendor_name=vendor_name,
        original_sku=data.original_sku,
        barcode=data.barcode,
        base_unit=getattr(data, "base_unit", "each"),
        sell_uom=getattr(data, "sell_uom", "each"),
        pack_qty=getattr(data, "pack_qty", 1),
    )

    await product_repo.insert(product.model_dump())
    await department_repo.increment_product_count(data.department_id, 1)

    return product


@api_router.put("/products/{product_id}", response_model=Product)
async def update_product(product_id: str, data: ProductUpdate, current_user: dict = Depends(require_role("admin", "warehouse_manager"))):
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

    if "department_id" in update_data:
        department = await department_repo.get_by_id(update_data["department_id"])
        if department:
            update_data["department_name"] = department["name"]

    if "vendor_id" in update_data:
        if update_data["vendor_id"]:
            vendor = await vendor_repo.get_by_id(update_data["vendor_id"])
            update_data["vendor_name"] = vendor.get("name", "") if vendor else ""
        else:
            update_data["vendor_name"] = ""

    result = await product_repo.update(product_id, update_data)
    if not result:
        raise HTTPException(status_code=404, detail="Product not found")
    return result


@api_router.delete("/products/{product_id}")
async def delete_product(product_id: str, current_user: dict = Depends(require_role("admin", "warehouse_manager"))):
    product = await product_repo.get_by_id(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    await product_repo.delete(product_id)
    await department_repo.increment_product_count(product["department_id"], -1)

    return {"message": "Product deleted"}

# ==================== MATERIAL WITHDRAWAL (POS) ====================

@api_router.post("/withdrawals", response_model=MaterialWithdrawal)
async def create_withdrawal(data: MaterialWithdrawalCreate, current_user: dict = Depends(get_current_user)):
    """Create a material withdrawal - Contractors withdraw materials charged to their account"""
    if current_user.get("role") == "contractor":
        contractor = current_user
    else:
        contractor = current_user

    subtotal = sum(item.subtotal for item in data.items)
    cost_total = sum(item.cost * item.quantity for item in data.items)
    tax = round(subtotal * 0.08, 2)
    total = round(subtotal + tax, 2)

    withdrawal = MaterialWithdrawal(
        items=data.items,
        job_id=data.job_id,
        service_address=data.service_address,
        notes=data.notes,
        subtotal=subtotal,
        tax=tax,
        total=total,
        cost_total=cost_total,
        contractor_id=contractor["id"],
        contractor_name=contractor.get("name", ""),
        contractor_company=contractor.get("company", ""),
        billing_entity=contractor.get("billing_entity", ""),
        payment_status="unpaid",
        processed_by_id=current_user["id"],
        processed_by_name=current_user.get("name", ""),
    )

    # Atomic stock decrement + stock ledger (rolls back on insufficient stock)
    try:
        await process_withdrawal_stock_changes(
            items=data.items,
            withdrawal_id=withdrawal.id,
            user_id=current_user["id"],
            user_name=current_user.get("name", ""),
        )
    except InsufficientStockError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)

    await withdrawal_repo.insert(withdrawal.model_dump())
    return withdrawal


@api_router.post("/withdrawals/for-contractor")
async def create_withdrawal_for_contractor(
    contractor_id: str,
    data: MaterialWithdrawalCreate,
    current_user: dict = Depends(require_role("admin", "warehouse_manager")),
):
    """Warehouse manager creates withdrawal on behalf of a contractor"""
    contractor = await user_repo.get_by_id(contractor_id)
    if not contractor or contractor.get("role") != "contractor":
        raise HTTPException(status_code=404, detail="Contractor not found")

    subtotal = sum(item.subtotal for item in data.items)
    cost_total = sum(item.cost * item.quantity for item in data.items)
    tax = round(subtotal * 0.08, 2)
    total = round(subtotal + tax, 2)

    withdrawal = MaterialWithdrawal(
        items=data.items,
        job_id=data.job_id,
        service_address=data.service_address,
        notes=data.notes,
        subtotal=subtotal,
        tax=tax,
        total=total,
        cost_total=cost_total,
        contractor_id=contractor["id"],
        contractor_name=contractor.get("name", ""),
        contractor_company=contractor.get("company", ""),
        billing_entity=contractor.get("billing_entity", ""),
        payment_status="unpaid",
        processed_by_id=current_user["id"],
        processed_by_name=current_user.get("name", ""),
    )

    try:
        await process_withdrawal_stock_changes(
            items=data.items,
            withdrawal_id=withdrawal.id,
            user_id=current_user["id"],
            user_name=current_user.get("name", ""),
        )
    except InsufficientStockError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)

    await withdrawal_repo.insert(withdrawal.model_dump())
    return withdrawal


@api_router.get("/withdrawals")
async def get_withdrawals(
    contractor_id: Optional[str] = None,
    payment_status: Optional[str] = None,
    billing_entity: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    cid = current_user["id"] if current_user.get("role") == "contractor" else contractor_id
    return await withdrawal_repo.list_withdrawals(
        contractor_id=cid,
        payment_status=payment_status,
        billing_entity=billing_entity,
        start_date=start_date,
        end_date=end_date,
        limit=1000,
    )


@api_router.get("/withdrawals/{withdrawal_id}")
async def get_withdrawal(withdrawal_id: str, current_user: dict = Depends(get_current_user)):
    withdrawal = await withdrawal_repo.get_by_id(withdrawal_id)
    if not withdrawal:
        raise HTTPException(status_code=404, detail="Withdrawal not found")
    
    # Contractors can only view their own
    if current_user.get("role") == "contractor" and withdrawal.get("contractor_id") != current_user["id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    return withdrawal

# ==================== FINANCIAL DASHBOARD (Admin) ====================

@api_router.get("/financials/summary")
async def get_financial_summary(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: dict = Depends(require_role("admin"))
):
    """Get financial summary for admin dashboard"""
    withdrawals = await withdrawal_repo.list_withdrawals(
        start_date=start_date, end_date=end_date, limit=10000
    )
    
    # Calculate totals
    total_unpaid = sum(w["total"] for w in withdrawals if w.get("payment_status") == "unpaid")
    total_paid = sum(w["total"] for w in withdrawals if w.get("payment_status") == "paid")
    total_invoiced = sum(w["total"] for w in withdrawals if w.get("payment_status") == "invoiced")
    total_revenue = sum(w["total"] for w in withdrawals)
    total_cost = sum(w.get("cost_total", 0) for w in withdrawals)
    
    # By billing entity
    by_entity = {}
    for w in withdrawals:
        entity = w.get("billing_entity", "Unknown")
        if entity not in by_entity:
            by_entity[entity] = {"total": 0, "unpaid": 0, "paid": 0, "count": 0}
        by_entity[entity]["total"] += w["total"]
        by_entity[entity]["count"] += 1
        if w.get("payment_status") == "unpaid":
            by_entity[entity]["unpaid"] += w["total"]
        elif w.get("payment_status") == "paid":
            by_entity[entity]["paid"] += w["total"]
    
    # By contractor
    by_contractor = {}
    for w in withdrawals:
        cid = w.get("contractor_id", "Unknown")
        cname = w.get("contractor_name", "Unknown")
        if cid not in by_contractor:
            by_contractor[cid] = {"name": cname, "company": w.get("contractor_company", ""), "total": 0, "unpaid": 0, "count": 0}
        by_contractor[cid]["total"] += w["total"]
        by_contractor[cid]["count"] += 1
        if w.get("payment_status") == "unpaid":
            by_contractor[cid]["unpaid"] += w["total"]
    
    return {
        "total_revenue": round(total_revenue, 2),
        "total_cost": round(total_cost, 2),
        "gross_margin": round(total_revenue - total_cost, 2),
        "total_unpaid": round(total_unpaid, 2),
        "total_paid": round(total_paid, 2),
        "total_invoiced": round(total_invoiced, 2),
        "transaction_count": len(withdrawals),
        "by_billing_entity": by_entity,
        "by_contractor": list(by_contractor.values())
    }

@api_router.put("/withdrawals/{withdrawal_id}/mark-paid")
async def mark_withdrawal_paid(withdrawal_id: str, current_user: dict = Depends(require_role("admin"))):
    paid_at = datetime.now(timezone.utc).isoformat()
    result = await withdrawal_repo.mark_paid(withdrawal_id, paid_at)
    if not result:
        raise HTTPException(status_code=404, detail="Withdrawal not found")
    return result


@api_router.put("/withdrawals/bulk-mark-paid")
async def bulk_mark_paid(withdrawal_ids: List[str], current_user: dict = Depends(require_role("admin"))):
    paid_at = datetime.now(timezone.utc).isoformat()
    updated = await withdrawal_repo.bulk_mark_paid(withdrawal_ids, paid_at)
    return {"updated": updated}

@api_router.get("/financials/export")
async def export_financials(
    format: str = "csv",
    payment_status: Optional[str] = None,
    billing_entity: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: dict = Depends(require_role("admin"))
):
    """Export financial data as CSV"""
    withdrawals = await withdrawal_repo.list_withdrawals(
        payment_status=payment_status,
        billing_entity=billing_entity,
        start_date=start_date,
        end_date=end_date,
        limit=10000,
    )
    
    # Create CSV
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Header
    writer.writerow([
        "Transaction ID", "Date", "Contractor", "Company", "Billing Entity",
        "Job ID", "Service Address", "Subtotal", "Tax", "Total",
        "Cost", "Margin", "Payment Status", "Items"
    ])
    
    for w in withdrawals:
        items_str = "; ".join([f"{i['name']} x{i['quantity']}" for i in w.get("items", [])])
        writer.writerow([
            w.get("id", ""),
            w.get("created_at", "")[:10],
            w.get("contractor_name", ""),
            w.get("contractor_company", ""),
            w.get("billing_entity", ""),
            w.get("job_id", ""),
            w.get("service_address", ""),
            w.get("subtotal", 0),
            w.get("tax", 0),
            w.get("total", 0),
            w.get("cost_total", 0),
            round(w.get("total", 0) - w.get("cost_total", 0), 2),
            w.get("payment_status", ""),
            items_str
        ])
    
    output.seek(0)
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=financials_{datetime.now().strftime('%Y%m%d')}.csv"}
    )

# ==================== REPORTS ====================

@api_router.get("/reports/sales")
async def get_sales_report(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: dict = Depends(require_role("admin", "warehouse_manager"))
):
    withdrawals = await withdrawal_repo.list_withdrawals(
        start_date=start_date, end_date=end_date, limit=10000
    )

    total_revenue = sum(w.get("total", 0) for w in withdrawals)
    total_tax = sum(w.get("tax", 0) for w in withdrawals)
    total_transactions = len(withdrawals)
    
    # By payment status
    by_status = {}
    for w in withdrawals:
        status = w.get("payment_status", "unknown")
        by_status[status] = by_status.get(status, 0) + w.get("total", 0)
    
    # Top products
    product_sales = {}
    for w in withdrawals:
        for item in w.get("items", []):
            pid = item.get("product_id")
            if pid:
                if pid not in product_sales:
                    product_sales[pid] = {"name": item.get("name"), "quantity": 0, "revenue": 0}
                product_sales[pid]["quantity"] += item.get("quantity", 0)
                product_sales[pid]["revenue"] += item.get("subtotal", 0)
    
    top_products = sorted(product_sales.values(), key=lambda x: x["revenue"], reverse=True)[:10]
    
    return {
        "total_revenue": round(total_revenue, 2),
        "total_tax": round(total_tax, 2),
        "total_transactions": total_transactions,
        "average_transaction": round(total_revenue / total_transactions, 2) if total_transactions > 0 else 0,
        "by_payment_status": by_status,
        "top_products": top_products
    }

@api_router.get("/reports/inventory")
async def get_inventory_report(current_user: dict = Depends(require_role("admin", "warehouse_manager"))):
    products = await product_repo.list_products()
    
    total_products = len(products)
    total_value = sum(p.get("price", 0) * p.get("quantity", 0) for p in products)
    total_cost = sum(p.get("cost", 0) * p.get("quantity", 0) for p in products)
    low_stock = [p for p in products if p.get("quantity", 0) <= p.get("min_stock", 5)]
    out_of_stock = [p for p in products if p.get("quantity", 0) == 0]
    
    by_department = {}
    for p in products:
        dept = p.get("department_name", "Unknown")
        if dept not in by_department:
            by_department[dept] = {"count": 0, "value": 0}
        by_department[dept]["count"] += 1
        by_department[dept]["value"] += p.get("price", 0) * p.get("quantity", 0)
    
    return {
        "total_products": total_products,
        "total_retail_value": round(total_value, 2),
        "total_cost_value": round(total_cost, 2),
        "potential_profit": round(total_value - total_cost, 2),
        "low_stock_count": len(low_stock),
        "out_of_stock_count": len(out_of_stock),
        "low_stock_items": low_stock[:20],
        "by_department": by_department
    }

# ==================== DASHBOARD ====================

@api_router.get("/dashboard/stats")
async def get_dashboard_stats(current_user: dict = Depends(get_current_user)):
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_str = today.isoformat()
    
    # For contractors, show their own stats
    if current_user.get("role") == "contractor":
        my_withdrawals = await withdrawal_repo.list_withdrawals(
            contractor_id=current_user["id"], limit=1000
        )
        
        total_spent = sum(w.get("total", 0) for w in my_withdrawals)
        unpaid = sum(w.get("total", 0) for w in my_withdrawals if w.get("payment_status") == "unpaid")
        
        return {
            "total_withdrawals": len(my_withdrawals),
            "total_spent": round(total_spent, 2),
            "unpaid_balance": round(unpaid, 2),
            "recent_withdrawals": my_withdrawals[:5]
        }
    
    # For warehouse manager / admin
    today_withdrawals = await withdrawal_repo.list_withdrawals(
        start_date=today_str, limit=1000
    )
    today_revenue = sum(w.get("total", 0) for w in today_withdrawals)
    today_transactions = len(today_withdrawals)

    # Week revenue (last 7 days)
    week_start = (datetime.now(timezone.utc) - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
    week_start_str = week_start.isoformat()
    week_withdrawals = await withdrawal_repo.list_withdrawals(
        start_date=week_start_str, limit=10000
    )
    week_revenue = sum(w.get("total", 0) for w in week_withdrawals)

    total_products = await product_repo.count_all()
    low_stock_products = await product_repo.count_low_stock()
    total_vendors = await vendor_repo.count()
    total_contractors = await user_repo.count_contractors()

    # Unpaid totals
    unpaid_withdrawals = await withdrawal_repo.list_withdrawals(
        payment_status="unpaid", limit=10000
    )
    unpaid_total = sum(w.get("total", 0) for w in unpaid_withdrawals)

    recent_withdrawals = await withdrawal_repo.list_withdrawals(limit=5)
    low_stock_items = await product_repo.list_low_stock(10)

    # Revenue by day for last 7 days (for chart)
    revenue_by_day = {}
    for i in range(7):
        d = (datetime.now(timezone.utc) - timedelta(days=6 - i)).replace(hour=0, minute=0, second=0, microsecond=0)
        key = d.strftime("%Y-%m-%d")
        revenue_by_day[key] = 0
    for w in week_withdrawals:
        created = w.get("created_at", "")[:10]
        if created in revenue_by_day:
            revenue_by_day[created] += w.get("total", 0)
    revenue_by_day_list = [{"date": k, "revenue": round(v, 2)} for k, v in sorted(revenue_by_day.items())]

    return {
        "today_revenue": round(today_revenue, 2),
        "today_transactions": today_transactions,
        "week_revenue": round(week_revenue, 2),
        "revenue_by_day": revenue_by_day_list,
        "total_products": total_products,
        "low_stock_count": low_stock_products,
        "total_vendors": total_vendors,
        "total_contractors": total_contractors,
        "unpaid_total": round(unpaid_total, 2),
        "recent_withdrawals": recent_withdrawals,
        "low_stock_alerts": low_stock_items
    }

# ==================== RECEIPT OCR ====================

@api_router.post("/receipts/extract")
async def extract_receipt(file: UploadFile = File(...), current_user: dict = Depends(require_role("admin", "warehouse_manager"))):
    try:
        contents = await file.read()
        if not os.environ.get("LLM_API_KEY"):
            raise HTTPException(status_code=500, detail="LLM API key not configured")

        from services.llm import generate_with_image

        system_msg = """You are a receipt parser for a hardware store. Extract product information from receipt images.
Infer unit of measure from product names (e.g. "5 Gal Paint" -> base_unit gallon, pack_qty 5; "2x4x8" -> foot; "Nail Box" -> box).
Allowed units: each, case, box, pack, bag, roll, kit, gallon, quart, pint, liter, pound, ounce, foot, meter, yard, sqft.
Return ONLY valid JSON:
{
    "store_name": "Store Name",
    "products": [
        {"name": "Product Name", "quantity": 1, "price": 9.99, "original_sku": "SKU123", "base_unit": "gallon", "sell_uom": "gallon", "pack_qty": 5}
    ],
    "total": 99.99,
    "date": "2024-01-15"
}
Always include base_unit, sell_uom, pack_qty for each product. Use "each" and 1 when unsure."""

        response = await asyncio.to_thread(
            generate_with_image,
            "Extract all product information from this receipt. Return only valid JSON.",
            contents,
            mime_type=file.content_type or "image/jpeg",
            system_instruction=system_msg,
        )
        if not response:
            raise HTTPException(status_code=500, detail="LLM failed to process receipt")

        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            extracted_data = json.loads(json_match.group())
        else:
            extracted_data = json.loads(response)

        return extracted_data
        
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error: {e}")
        raise HTTPException(status_code=422, detail="Could not parse receipt data")
    except Exception as e:
        logger.error(f"Receipt extraction error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/vendors/{vendor_id}/import-pdf")
async def import_vendor_pdf(vendor_id: str, file: UploadFile = File(...), current_user: dict = Depends(require_role("admin", "warehouse_manager"))):
    import tempfile
    temp_file_path = None

    try:
        vendor = await vendor_repo.get_by_id(vendor_id)
        if not vendor:
            raise HTTPException(status_code=404, detail="Vendor not found")

        contents = await file.read()

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
            temp_file.write(contents)
            temp_file_path = temp_file.name

        if not os.environ.get("LLM_API_KEY"):
            raise HTTPException(status_code=500, detail="LLM API key not configured")

        from services.llm import generate_with_pdf

        departments = await department_repo.list_all()
        dept_list = ", ".join([f"{d['name']} ({d['code']})" for d in departments])
        system_msg = f"""You are an invoice/receipt parser for a hardware store.
Available departments: {dept_list}
Allowed UOM units: each, case, box, pack, bag, roll, kit, gallon, quart, pint, liter, pound, ounce, foot, meter, yard, sqft.
Infer base_unit, sell_uom, pack_qty from product names (e.g. "5 Gal Paint" -> base_unit gallon, pack_qty 5).
Return ONLY valid JSON:
{{"store_name": "...", "products": [{{"name": "...", "quantity": 1, "price": 9.99, "cost": 7.99, "original_sku": "...", "suggested_department": "PLU", "base_unit": "gallon", "sell_uom": "gallon", "pack_qty": 5}}], "total": 99.99, "date": "2024-01-15"}}
Use EFFECTIVE price (after discounts). Match products to departments. Always include base_unit, sell_uom, pack_qty (use "each", "each", 1 when unsure)."""

        response = await asyncio.to_thread(
            generate_with_pdf,
            "Extract all product information. Return only valid JSON.",
            temp_file_path,
            system_instruction=system_msg,
        )
        if not response:
            raise HTTPException(status_code=500, detail="LLM failed to process PDF")

        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            extracted_data = json.loads(json_match.group())
        else:
            extracted_data = json.loads(response)

        extracted_data["vendor_id"] = vendor_id
        extracted_data["vendor_name"] = vendor.get("name", "")

        return extracted_data
        
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error: {e}")
        raise HTTPException(status_code=422, detail="Could not parse PDF data")
    except Exception as e:
        logger.error(f"PDF extraction error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            os.unlink(temp_file_path)

def _resolve_uom(item: dict) -> Tuple[str, str, int]:
    """Resolve base_unit, sell_uom, pack_qty from item, validating against allowed units."""
    bu = (item.get("base_unit") or "each").lower().strip()
    su = (item.get("sell_uom") or item.get("base_unit") or "each").lower().strip()
    pq = item.get("pack_qty")
    try:
        pq = max(1, int(pq)) if pq is not None else 1
    except (ValueError, TypeError):
        pq = 1
    bu = bu if bu in ALLOWED_BASE_UNITS else "each"
    su = su if su in ALLOWED_BASE_UNITS else "each"
    return bu, su, pq


@api_router.post("/vendors/{vendor_id}/import-products")
async def import_vendor_products(vendor_id: str, products: List[dict], current_user: dict = Depends(require_role("admin", "warehouse_manager"))):
    vendor = await vendor_repo.get_by_id(vendor_id)
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")

    # Classify UOM for products missing valid base_unit/sell_uom
    needs_uom = [p for p in products if (p.get("base_unit") or "").lower() not in ALLOWED_BASE_UNITS or (p.get("sell_uom") or "").lower() not in ALLOWED_BASE_UNITS]
    if needs_uom:
        await classify_uom_batch(needs_uom)

    imported = []
    errors = []

    for item in products:
        try:
            dept_code = item.get("suggested_department", "HDW")
            department = await department_repo.get_by_code(dept_code)
            
            if not department:
                department = await department_repo.get_by_code("HDW")
                if not department:
                    errors.append({"product": item.get("name"), "error": "No valid department"})
                    continue
            
            sku = await generate_sku(department["code"])
            bu, su, pq = _resolve_uom(item)

            product = Product(
                sku=sku,
                name=item.get("name", "Unknown"),
                description=item.get("description", ""),
                price=float(item.get("price", 0)),
                cost=float(item.get("cost", 0)) or float(item.get("price", 0)) * 0.7,
                quantity=int(item.get("quantity", 1)),
                min_stock=5,
                department_id=department["id"],
                department_name=department["name"],
                vendor_id=vendor_id,
                vendor_name=vendor.get("name", ""),
                original_sku=item.get("original_sku"),
                base_unit=bu,
                sell_uom=su,
                pack_qty=pq,
            )
            
            await product_repo.insert(product.model_dump())
            await process_import_stock_changes(
                product_id=product.id,
                sku=product.sku,
                product_name=product.name,
                quantity=product.quantity,
                user_id=current_user["id"],
                user_name=current_user.get("name", ""),
            )
            imported.append(product)
            await department_repo.increment_product_count(department["id"], 1)
            await vendor_repo.increment_product_count(vendor_id, 1)

        except Exception as e:
            errors.append({"product": item.get("name"), "error": str(e)})

    return {
        "imported": len(imported),
        "errors": len(errors),
        "products": imported,
        "error_details": errors,
    }

@api_router.post("/receipts/import")
async def import_receipt_products(
    products: List[ExtractedProduct],
    department_id: str,
    current_user: dict = Depends(require_role("admin", "warehouse_manager")),
):
    department = await department_repo.get_by_id(department_id)
    if not department:
        raise HTTPException(status_code=400, detail="Department not found")

    # Convert to dicts for UOM classification; classify any missing/invalid UOM
    items = [{"name": p.name, "base_unit": p.base_unit, "sell_uom": p.sell_uom, "pack_qty": p.pack_qty, **p.model_dump()} for p in products]
    needs_uom = [i for i in items if (i.get("base_unit") or "").lower() not in ALLOWED_BASE_UNITS or (i.get("sell_uom") or "").lower() not in ALLOWED_BASE_UNITS]
    if needs_uom:
        await classify_uom_batch(needs_uom)

    imported = []
    for item in items:
        sku = await generate_sku(department["code"])
        bu, su, pq = _resolve_uom(item)
        product = Product(
            sku=sku,
            name=item["name"],
            price=float(item["price"]),
            cost=round(float(item["price"]) * 0.7, 2),
            quantity=int(item.get("quantity", 1)),
            min_stock=5,
            department_id=department_id,
            department_name=department["name"],
            original_sku=item.get("original_sku"),
            base_unit=bu,
            sell_uom=su,
            pack_qty=pq,
        )
        await product_repo.insert(product.model_dump())
        await process_import_stock_changes(
            product_id=product.id,
            sku=product.sku,
            product_name=product.name,
            quantity=product.quantity,
            user_id=current_user["id"],
            user_name=current_user.get("name", ""),
        )
        imported.append(product)

    await department_repo.increment_product_count(department_id, len(imported))
    return {"imported": len(imported), "products": imported}

# ==================== STRIPE PAYMENTS ====================

class CreatePaymentRequest(BaseModel):
    withdrawal_id: str
    origin_url: str

@api_router.post("/payments/create-checkout")
async def create_payment_checkout(data: CreatePaymentRequest, request: Request, current_user: dict = Depends(get_current_user)):
    """Create a Stripe checkout session for a withdrawal"""
    
    # Fetch the withdrawal
    withdrawal = await withdrawal_repo.get_by_id(data.withdrawal_id)
    if not withdrawal:
        raise HTTPException(status_code=404, detail="Withdrawal not found")
    
    # Only allow payment for unpaid withdrawals
    if withdrawal.get("payment_status") == "paid":
        raise HTTPException(status_code=400, detail="This withdrawal is already paid")
    
    if not HAS_EMERGENT_STRIPE:
        raise HTTPException(status_code=503, detail="Stripe integration not installed (emergentintegrations)")
    stripe_api_key = os.environ.get("STRIPE_API_KEY")
    if not stripe_api_key:
        raise HTTPException(status_code=500, detail="Stripe not configured")
    
    # Build URLs using the origin provided by frontend
    origin = data.origin_url.rstrip("/")
    success_url = f"{origin}/pos?payment=success&session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{origin}/pos?payment=cancelled"
    
    # Initialize Stripe
    host_url = str(request.base_url)
    webhook_url = f"{host_url}api/webhook/stripe"
    stripe_checkout = StripeCheckout(api_key=stripe_api_key, webhook_url=webhook_url)
    
    # Create checkout session - amount is from the server (withdrawal total), not from frontend
    amount = float(withdrawal.get("total", 0))
    
    metadata = {
        "withdrawal_id": data.withdrawal_id,
        "contractor_id": withdrawal.get("contractor_id", ""),
        "job_id": withdrawal.get("job_id", ""),
        "user_id": current_user["id"]
    }
    
    checkout_request = CheckoutSessionRequest(
        amount=amount,
        currency="usd",
        success_url=success_url,
        cancel_url=cancel_url,
        metadata=metadata
    )
    
    try:
        session: CheckoutSessionResponse = await stripe_checkout.create_checkout_session(checkout_request)
        
        # Create payment transaction record
        payment_record = {
            "id": str(uuid.uuid4()),
            "session_id": session.session_id,
            "withdrawal_id": data.withdrawal_id,
            "user_id": current_user["id"],
            "contractor_id": withdrawal.get("contractor_id", ""),
            "amount": amount,
            "currency": "usd",
            "metadata": metadata,
            "payment_status": "pending",
            "status": "initiated",
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await payment_repo.insert(payment_record)
        
        return {
            "checkout_url": session.url,
            "session_id": session.session_id
        }
    except Exception as e:
        logger.error(f"Stripe checkout error: {e}")
        raise HTTPException(status_code=500, detail=f"Payment processing error: {str(e)}")

@api_router.get("/payments/status/{session_id}")
async def get_payment_status(session_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    """Check the status of a payment session and update records"""
    if not HAS_EMERGENT_STRIPE:
        raise HTTPException(status_code=503, detail="Stripe integration not installed (emergentintegrations)")
    stripe_api_key = os.environ.get("STRIPE_API_KEY")
    if not stripe_api_key:
        raise HTTPException(status_code=500, detail="Stripe not configured")
    
    host_url = str(request.base_url)
    webhook_url = f"{host_url}api/webhook/stripe"
    stripe_checkout = StripeCheckout(api_key=stripe_api_key, webhook_url=webhook_url)
    
    try:
        status: CheckoutStatusResponse = await stripe_checkout.get_checkout_status(session_id)
        
        # Find the payment transaction
        payment = await payment_repo.get_by_session_id(session_id)

        if payment and status.payment_status == "paid" and payment.get("payment_status") != "paid":
            paid_at = datetime.now(timezone.utc).isoformat()
            await payment_repo.update_status(session_id, "paid", "complete", paid_at)
            if payment.get("withdrawal_id"):
                await withdrawal_repo.mark_paid(payment["withdrawal_id"], paid_at)
        elif status.status == "expired":
            await payment_repo.update_status(session_id, "expired", "expired")
        
        return {
            "status": status.status,
            "payment_status": status.payment_status,
            "amount_total": status.amount_total,
            "currency": status.currency,
            "withdrawal_id": payment.get("withdrawal_id") if payment else None
        }
    except Exception as e:
        logger.error(f"Payment status check error: {e}")
        raise HTTPException(status_code=500, detail=f"Error checking payment status: {str(e)}")

@api_router.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    """Handle Stripe webhooks"""
    if not HAS_EMERGENT_STRIPE:
        raise HTTPException(status_code=503, detail="Stripe integration not installed (emergentintegrations)")
    stripe_api_key = os.environ.get("STRIPE_API_KEY")
    if not stripe_api_key:
        raise HTTPException(status_code=500, detail="Stripe not configured")
    
    try:
        body = await request.body()
        signature = request.headers.get("Stripe-Signature")
        
        host_url = str(request.base_url)
        webhook_url = f"{host_url}api/webhook/stripe"
        stripe_checkout = StripeCheckout(api_key=stripe_api_key, webhook_url=webhook_url)
        
        webhook_response = await stripe_checkout.handle_webhook(body, signature)
        
        if webhook_response.payment_status == "paid":
            session_id = webhook_response.session_id
            
            # Update payment transaction
            payment = await payment_repo.get_by_session_id(session_id)

            if payment and payment.get("payment_status") != "paid":
                paid_at = datetime.now(timezone.utc).isoformat()
                await payment_repo.update_status(session_id, "paid", "complete", paid_at)
                if payment.get("withdrawal_id"):
                    await withdrawal_repo.mark_paid(payment["withdrawal_id"], paid_at)
        
        return {"received": True}
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return {"received": True, "error": str(e)}

# ==================== SEED DATA ====================

@api_router.post("/seed/departments")
async def seed_departments():
    standard_departments = [
        {"name": "Lumber", "code": "LUM", "description": "Wood, plywood, boards"},
        {"name": "Plumbing", "code": "PLU", "description": "Pipes, fittings, fixtures"},
        {"name": "Electrical", "code": "ELE", "description": "Wiring, outlets, switches"},
        {"name": "Paint", "code": "PNT", "description": "Paint, stains, brushes"},
        {"name": "Tools", "code": "TOL", "description": "Hand tools, power tools"},
        {"name": "Hardware", "code": "HDW", "description": "Fasteners, hinges, locks"},
        {"name": "Garden", "code": "GDN", "description": "Plants, soil, fertilizers"},
        {"name": "Appliances", "code": "APP", "description": "Home appliances"}
    ]
    
    created = 0
    for dept_data in standard_departments:
        existing = await department_repo.get_by_code(dept_data["code"])
        if not existing:
            dept = Department(**dept_data)
            await department_repo.insert(dept.model_dump())
            created += 1
    
    return {"message": f"Seeded {created} departments"}

# ==================== MAIN ====================

@api_router.get("/")
async def root():
    return {"message": "Supply Yard API - Material Management System"}

app.include_router(api_router)


@app.on_event("startup")
async def startup():
    """Initialize SQLite database on startup."""
    try:
        await init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.warning(f"Database init: {e}")


app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("shutdown")
async def shutdown_db_client():
    await close_db()
