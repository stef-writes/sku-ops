from fastapi import FastAPI, APIRouter, HTTPException, Depends, UploadFile, File, Query, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
import uuid
from datetime import datetime, timezone, timedelta
import jwt
import bcrypt
import base64
import json
import re
import csv
import io

# Stripe integration
from emergentintegrations.payments.stripe.checkout import StripeCheckout, CheckoutSessionResponse, CheckoutStatusResponse, CheckoutSessionRequest

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# JWT Settings
JWT_SECRET = os.environ.get('JWT_SECRET', 'hardware-store-secret-key')
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

# Create the main app
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

security = HTTPBearer()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ==================== MODELS ====================

# Roles: admin, warehouse_manager, contractor
ROLES = ["admin", "warehouse_manager", "contractor"]

class UserCreate(BaseModel):
    email: str
    password: str
    name: str
    role: str = "warehouse_manager"
    # Contractor specific fields
    company: Optional[str] = None  # e.g., "On Point", "Stone & Timber"
    billing_entity: Optional[str] = None
    phone: Optional[str] = None

class UserUpdate(BaseModel):
    name: Optional[str] = None
    company: Optional[str] = None
    billing_entity: Optional[str] = None
    phone: Optional[str] = None
    is_active: Optional[bool] = None

class UserLogin(BaseModel):
    email: str
    password: str

class User(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    email: str
    name: str
    role: str = "warehouse_manager"
    company: Optional[str] = None
    billing_entity: Optional[str] = None
    phone: Optional[str] = None
    is_active: bool = True
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class DepartmentCreate(BaseModel):
    name: str
    code: str
    description: Optional[str] = ""

class Department(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    code: str
    description: str = ""
    product_count: int = 0
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class VendorCreate(BaseModel):
    name: str
    contact_name: Optional[str] = ""
    email: Optional[str] = ""
    phone: Optional[str] = ""
    address: Optional[str] = ""

class Vendor(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    contact_name: str = ""
    email: str = ""
    phone: str = ""
    address: str = ""
    product_count: int = 0
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class ProductCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    price: float
    cost: float = 0.0
    quantity: int = 0
    min_stock: int = 5
    department_id: str
    vendor_id: Optional[str] = None
    original_sku: Optional[str] = None
    barcode: Optional[str] = None

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    cost: Optional[float] = None
    quantity: Optional[int] = None
    min_stock: Optional[int] = None
    department_id: Optional[str] = None
    vendor_id: Optional[str] = None
    barcode: Optional[str] = None

class Product(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    sku: str
    name: str
    description: str = ""
    price: float
    cost: float = 0.0
    quantity: int = 0
    min_stock: int = 5
    department_id: str
    department_name: str = ""
    vendor_id: Optional[str] = None
    vendor_name: str = ""
    original_sku: Optional[str] = None
    barcode: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class WithdrawalItem(BaseModel):
    product_id: str
    sku: str
    name: str
    quantity: int
    price: float
    cost: float = 0.0
    subtotal: float

class MaterialWithdrawalCreate(BaseModel):
    items: List[WithdrawalItem]
    job_id: str  # Free text job ID
    service_address: str
    notes: Optional[str] = None

class MaterialWithdrawal(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    items: List[WithdrawalItem]
    job_id: str
    service_address: str
    notes: Optional[str] = None
    # Financial tracking
    subtotal: float
    tax: float
    total: float
    cost_total: float  # Total cost for margin tracking
    # Contractor info
    contractor_id: str
    contractor_name: str = ""
    contractor_company: str = ""
    billing_entity: str = ""
    # Status
    payment_status: str = "unpaid"  # unpaid, paid, invoiced
    invoice_id: Optional[str] = None
    paid_at: Optional[str] = None
    # Audit
    processed_by_id: str  # Warehouse manager who processed
    processed_by_name: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class ExtractedProduct(BaseModel):
    name: str
    quantity: int = 1
    price: float
    original_sku: Optional[str] = None

# ==================== AUTH HELPERS ====================

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def create_token(user_id: str, email: str, role: str) -> str:
    payload = {
        "user_id": user_id,
        "email": email,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRATION_HOURS)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user = await db.users.find_one({"id": payload["user_id"]}, {"_id": 0, "password": 0})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        if not user.get("is_active", True):
            raise HTTPException(status_code=401, detail="User account is disabled")
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

def require_role(*roles):
    async def role_checker(current_user: dict = Depends(get_current_user)):
        if current_user.get("role") not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return current_user
    return role_checker

# ==================== SKU GENERATOR ====================

async def generate_sku(department_code: str) -> str:
    counter = await db.sku_counters.find_one_and_update(
        {"department_code": department_code},
        {"$inc": {"counter": 1}},
        upsert=True,
        return_document=True
    )
    number = counter.get("counter", 1)
    return f"{department_code}-{str(number).zfill(5)}"

# ==================== AUTH ROUTES ====================

@api_router.post("/auth/register")
async def register(data: UserCreate):
    existing = await db.users.find_one({"email": data.email})
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
        phone=data.phone
    )
    user_dict = user.model_dump()
    user_dict["password"] = hash_password(data.password)
    
    await db.users.insert_one(user_dict)
    
    token = create_token(user.id, user.email, user.role)
    return {"token": token, "user": user.model_dump()}

@api_router.post("/auth/login")
async def login(data: UserLogin):
    user = await db.users.find_one({"email": data.email})
    if not user or not verify_password(data.password, user.get("password", "")):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.get("is_active", True):
        raise HTTPException(status_code=401, detail="Account is disabled")
    
    token = create_token(user["id"], user["email"], user["role"])
    user_response = {k: v for k, v in user.items() if k not in ["_id", "password"]}
    return {"token": token, "user": user_response}

@api_router.get("/auth/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    return current_user

# ==================== CONTRACTOR MANAGEMENT (Admin Only) ====================

@api_router.get("/contractors")
async def get_contractors(current_user: dict = Depends(require_role("admin", "warehouse_manager"))):
    contractors = await db.users.find(
        {"role": "contractor"},
        {"_id": 0, "password": 0}
    ).to_list(1000)
    return contractors

@api_router.post("/contractors")
async def create_contractor(data: UserCreate, current_user: dict = Depends(require_role("admin"))):
    existing = await db.users.find_one({"email": data.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    contractor = User(
        email=data.email,
        name=data.name,
        role="contractor",
        company=data.company or "Independent",
        billing_entity=data.billing_entity or data.company or "Independent",
        phone=data.phone
    )
    contractor_dict = contractor.model_dump()
    contractor_dict["password"] = hash_password(data.password)
    
    await db.users.insert_one(contractor_dict)
    
    return {k: v for k, v in contractor_dict.items() if k != "password"}

@api_router.put("/contractors/{contractor_id}")
async def update_contractor(contractor_id: str, data: UserUpdate, current_user: dict = Depends(require_role("admin"))):
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    
    result = await db.users.find_one_and_update(
        {"id": contractor_id, "role": "contractor"},
        {"$set": update_data},
        return_document=True
    )
    if not result:
        raise HTTPException(status_code=404, detail="Contractor not found")
    
    result.pop("_id", None)
    result.pop("password", None)
    return result

@api_router.delete("/contractors/{contractor_id}")
async def delete_contractor(contractor_id: str, current_user: dict = Depends(require_role("admin"))):
    result = await db.users.delete_one({"id": contractor_id, "role": "contractor"})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Contractor not found")
    return {"message": "Contractor deleted"}

# ==================== DEPARTMENT ROUTES ====================

@api_router.get("/departments", response_model=List[Department])
async def get_departments(current_user: dict = Depends(get_current_user)):
    departments = await db.departments.find({}, {"_id": 0}).to_list(100)
    return departments

@api_router.post("/departments", response_model=Department)
async def create_department(data: DepartmentCreate, current_user: dict = Depends(require_role("admin", "warehouse_manager"))):
    existing = await db.departments.find_one({"code": data.code.upper()})
    if existing:
        raise HTTPException(status_code=400, detail="Department code already exists")
    
    dept = Department(
        name=data.name,
        code=data.code.upper(),
        description=data.description or ""
    )
    await db.departments.insert_one(dept.model_dump())
    return dept

@api_router.put("/departments/{dept_id}", response_model=Department)
async def update_department(dept_id: str, data: DepartmentCreate, current_user: dict = Depends(require_role("admin", "warehouse_manager"))):
    result = await db.departments.find_one_and_update(
        {"id": dept_id},
        {"$set": {"name": data.name, "description": data.description or ""}},
        return_document=True
    )
    if not result:
        raise HTTPException(status_code=404, detail="Department not found")
    result.pop("_id", None)
    return result

@api_router.delete("/departments/{dept_id}")
async def delete_department(dept_id: str, current_user: dict = Depends(require_role("admin"))):
    product_count = await db.products.count_documents({"department_id": dept_id})
    if product_count > 0:
        raise HTTPException(status_code=400, detail="Cannot delete department with products")
    
    result = await db.departments.delete_one({"id": dept_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Department not found")
    return {"message": "Department deleted"}

# ==================== VENDOR ROUTES ====================

@api_router.get("/vendors", response_model=List[Vendor])
async def get_vendors(current_user: dict = Depends(require_role("admin", "warehouse_manager"))):
    vendors = await db.vendors.find({}, {"_id": 0}).to_list(100)
    return vendors

@api_router.post("/vendors", response_model=Vendor)
async def create_vendor(data: VendorCreate, current_user: dict = Depends(require_role("admin", "warehouse_manager"))):
    vendor = Vendor(**data.model_dump())
    await db.vendors.insert_one(vendor.model_dump())
    return vendor

@api_router.put("/vendors/{vendor_id}", response_model=Vendor)
async def update_vendor(vendor_id: str, data: VendorCreate, current_user: dict = Depends(require_role("admin", "warehouse_manager"))):
    result = await db.vendors.find_one_and_update(
        {"id": vendor_id},
        {"$set": data.model_dump()},
        return_document=True
    )
    if not result:
        raise HTTPException(status_code=404, detail="Vendor not found")
    result.pop("_id", None)
    return result

@api_router.delete("/vendors/{vendor_id}")
async def delete_vendor(vendor_id: str, current_user: dict = Depends(require_role("admin"))):
    result = await db.vendors.delete_one({"id": vendor_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Vendor not found")
    return {"message": "Vendor deleted"}

# ==================== PRODUCT ROUTES ====================

@api_router.get("/products", response_model=List[Product])
async def get_products(
    department_id: Optional[str] = None,
    search: Optional[str] = None,
    low_stock: bool = False,
    current_user: dict = Depends(get_current_user)
):
    query = {}
    if department_id:
        query["department_id"] = department_id
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"sku": {"$regex": search, "$options": "i"}},
            {"barcode": {"$regex": search, "$options": "i"}}
        ]
    if low_stock:
        query["$expr"] = {"$lte": ["$quantity", "$min_stock"]}
    
    products = await db.products.find(query, {"_id": 0}).to_list(1000)
    return products

@api_router.get("/products/{product_id}", response_model=Product)
async def get_product(product_id: str, current_user: dict = Depends(get_current_user)):
    product = await db.products.find_one({"id": product_id}, {"_id": 0})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product

@api_router.post("/products", response_model=Product)
async def create_product(data: ProductCreate, current_user: dict = Depends(require_role("admin", "warehouse_manager"))):
    department = await db.departments.find_one({"id": data.department_id}, {"_id": 0})
    if not department:
        raise HTTPException(status_code=400, detail="Department not found")
    
    vendor_name = ""
    if data.vendor_id:
        vendor = await db.vendors.find_one({"id": data.vendor_id}, {"_id": 0})
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
        barcode=data.barcode
    )
    
    await db.products.insert_one(product.model_dump())
    await db.departments.update_one({"id": data.department_id}, {"$inc": {"product_count": 1}})
    
    return product

@api_router.put("/products/{product_id}", response_model=Product)
async def update_product(product_id: str, data: ProductUpdate, current_user: dict = Depends(require_role("admin", "warehouse_manager"))):
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    if "department_id" in update_data:
        department = await db.departments.find_one({"id": update_data["department_id"]}, {"_id": 0})
        if department:
            update_data["department_name"] = department["name"]
    
    if "vendor_id" in update_data:
        if update_data["vendor_id"]:
            vendor = await db.vendors.find_one({"id": update_data["vendor_id"]}, {"_id": 0})
            update_data["vendor_name"] = vendor.get("name", "") if vendor else ""
        else:
            update_data["vendor_name"] = ""
    
    result = await db.products.find_one_and_update(
        {"id": product_id},
        {"$set": update_data},
        return_document=True
    )
    if not result:
        raise HTTPException(status_code=404, detail="Product not found")
    result.pop("_id", None)
    return result

@api_router.delete("/products/{product_id}")
async def delete_product(product_id: str, current_user: dict = Depends(require_role("admin", "warehouse_manager"))):
    product = await db.products.find_one({"id": product_id})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    await db.products.delete_one({"id": product_id})
    await db.departments.update_one({"id": product["department_id"]}, {"$inc": {"product_count": -1}})
    
    return {"message": "Product deleted"}

# ==================== MATERIAL WITHDRAWAL (POS) ====================

@api_router.post("/withdrawals", response_model=MaterialWithdrawal)
async def create_withdrawal(data: MaterialWithdrawalCreate, current_user: dict = Depends(get_current_user)):
    """Create a material withdrawal - Contractors withdraw materials charged to their account"""
    
    # For contractors, they are the one withdrawing
    # For warehouse managers, they need to specify contractor
    if current_user.get("role") == "contractor":
        contractor = current_user
    else:
        # Warehouse manager processes for a contractor - contractor_id should be in request
        # For now, warehouse manager can also process without contractor (walk-in edge case)
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
        processed_by_name=current_user.get("name", "")
    )
    
    await db.withdrawals.insert_one(withdrawal.model_dump())
    
    # Update product quantities
    for item in data.items:
        await db.products.update_one(
            {"id": item.product_id},
            {"$inc": {"quantity": -item.quantity}}
        )
    
    return withdrawal

@api_router.post("/withdrawals/for-contractor")
async def create_withdrawal_for_contractor(
    contractor_id: str,
    data: MaterialWithdrawalCreate,
    current_user: dict = Depends(require_role("admin", "warehouse_manager"))
):
    """Warehouse manager creates withdrawal on behalf of a contractor"""
    contractor = await db.users.find_one({"id": contractor_id, "role": "contractor"}, {"_id": 0, "password": 0})
    if not contractor:
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
        processed_by_name=current_user.get("name", "")
    )
    
    await db.withdrawals.insert_one(withdrawal.model_dump())
    
    for item in data.items:
        await db.products.update_one(
            {"id": item.product_id},
            {"$inc": {"quantity": -item.quantity}}
        )
    
    return withdrawal

@api_router.get("/withdrawals")
async def get_withdrawals(
    contractor_id: Optional[str] = None,
    payment_status: Optional[str] = None,
    billing_entity: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    query = {}
    
    # Contractors can only see their own withdrawals
    if current_user.get("role") == "contractor":
        query["contractor_id"] = current_user["id"]
    elif contractor_id:
        query["contractor_id"] = contractor_id
    
    if payment_status:
        query["payment_status"] = payment_status
    if billing_entity:
        query["billing_entity"] = billing_entity
    if start_date:
        query["created_at"] = {"$gte": start_date}
    if end_date:
        if "created_at" in query:
            query["created_at"]["$lte"] = end_date
        else:
            query["created_at"] = {"$lte": end_date}
    
    withdrawals = await db.withdrawals.find(query, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return withdrawals

@api_router.get("/withdrawals/{withdrawal_id}")
async def get_withdrawal(withdrawal_id: str, current_user: dict = Depends(get_current_user)):
    withdrawal = await db.withdrawals.find_one({"id": withdrawal_id}, {"_id": 0})
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
    query = {}
    if start_date:
        query["created_at"] = {"$gte": start_date}
    if end_date:
        if "created_at" in query:
            query["created_at"]["$lte"] = end_date
        else:
            query["created_at"] = {"$lte": end_date}
    
    withdrawals = await db.withdrawals.find(query, {"_id": 0}).to_list(10000)
    
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
    result = await db.withdrawals.find_one_and_update(
        {"id": withdrawal_id},
        {"$set": {"payment_status": "paid", "paid_at": datetime.now(timezone.utc).isoformat()}},
        return_document=True
    )
    if not result:
        raise HTTPException(status_code=404, detail="Withdrawal not found")
    result.pop("_id", None)
    return result

@api_router.put("/withdrawals/bulk-mark-paid")
async def bulk_mark_paid(withdrawal_ids: List[str], current_user: dict = Depends(require_role("admin"))):
    result = await db.withdrawals.update_many(
        {"id": {"$in": withdrawal_ids}},
        {"$set": {"payment_status": "paid", "paid_at": datetime.now(timezone.utc).isoformat()}}
    )
    return {"updated": result.modified_count}

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
    query = {}
    if payment_status:
        query["payment_status"] = payment_status
    if billing_entity:
        query["billing_entity"] = billing_entity
    if start_date:
        query["created_at"] = {"$gte": start_date}
    if end_date:
        if "created_at" in query:
            query["created_at"]["$lte"] = end_date
        else:
            query["created_at"] = {"$lte": end_date}
    
    withdrawals = await db.withdrawals.find(query, {"_id": 0}).sort("created_at", -1).to_list(10000)
    
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
    query = {}
    if start_date:
        query["created_at"] = {"$gte": start_date}
    if end_date:
        if "created_at" in query:
            query["created_at"]["$lte"] = end_date
        else:
            query["created_at"] = {"$lte": end_date}
    
    withdrawals = await db.withdrawals.find(query, {"_id": 0}).to_list(10000)
    
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
    products = await db.products.find({}, {"_id": 0}).to_list(10000)
    
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
        my_withdrawals = await db.withdrawals.find(
            {"contractor_id": current_user["id"]},
            {"_id": 0}
        ).sort("created_at", -1).to_list(1000)
        
        total_spent = sum(w.get("total", 0) for w in my_withdrawals)
        unpaid = sum(w.get("total", 0) for w in my_withdrawals if w.get("payment_status") == "unpaid")
        
        return {
            "total_withdrawals": len(my_withdrawals),
            "total_spent": round(total_spent, 2),
            "unpaid_balance": round(unpaid, 2),
            "recent_withdrawals": my_withdrawals[:5]
        }
    
    # For warehouse manager / admin
    today_withdrawals = await db.withdrawals.find({"created_at": {"$gte": today_str}}, {"_id": 0}).to_list(1000)
    today_revenue = sum(w.get("total", 0) for w in today_withdrawals)
    today_transactions = len(today_withdrawals)
    
    total_products = await db.products.count_documents({})
    low_stock_products = await db.products.count_documents({"$expr": {"$lte": ["$quantity", "$min_stock"]}})
    total_vendors = await db.vendors.count_documents({})
    total_contractors = await db.users.count_documents({"role": "contractor"})
    
    # Unpaid totals
    unpaid_total = 0
    unpaid_withdrawals = await db.withdrawals.find({"payment_status": "unpaid"}, {"_id": 0}).to_list(10000)
    unpaid_total = sum(w.get("total", 0) for w in unpaid_withdrawals)
    
    recent_withdrawals = await db.withdrawals.find({}, {"_id": 0}).sort("created_at", -1).to_list(5)
    low_stock_items = await db.products.find({"$expr": {"$lte": ["$quantity", "$min_stock"]}}, {"_id": 0}).to_list(10)
    
    return {
        "today_revenue": round(today_revenue, 2),
        "today_transactions": today_transactions,
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
        image_base64 = base64.b64encode(contents).decode('utf-8')
        
        from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
        
        api_key = os.environ.get('EMERGENT_LLM_KEY')
        if not api_key:
            raise HTTPException(status_code=500, detail="LLM API key not configured")
        
        chat = LlmChat(
            api_key=api_key,
            session_id=f"receipt-{uuid.uuid4()}",
            system_message="""You are a receipt parser. Extract product information from receipt images.
            Return ONLY valid JSON in this exact format:
            {
                "store_name": "Store Name",
                "products": [
                    {"name": "Product Name", "quantity": 1, "price": 9.99, "original_sku": "SKU123"}
                ],
                "total": 99.99,
                "date": "2024-01-15"
            }"""
        ).with_model("gemini", "gemini-3-flash-preview")
        
        image_content = ImageContent(image_base64=image_base64)
        user_message = UserMessage(
            text="Extract all product information from this receipt. Return only valid JSON.",
            image_contents=[image_content]
        )
        
        response = await chat.send_message(user_message)
        
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
        vendor = await db.vendors.find_one({"id": vendor_id}, {"_id": 0})
        if not vendor:
            raise HTTPException(status_code=404, detail="Vendor not found")
        
        contents = await file.read()
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
            temp_file.write(contents)
            temp_file_path = temp_file.name
        
        from emergentintegrations.llm.chat import LlmChat, UserMessage, FileContentWithMimeType
        
        api_key = os.environ.get('EMERGENT_LLM_KEY')
        if not api_key:
            raise HTTPException(status_code=500, detail="LLM API key not configured")
        
        departments = await db.departments.find({}, {"_id": 0}).to_list(100)
        dept_list = ", ".join([f"{d['name']} ({d['code']})" for d in departments])
        
        chat = LlmChat(
            api_key=api_key,
            session_id=f"vendor-pdf-{uuid.uuid4()}",
            system_message=f"""You are an invoice/receipt parser for a hardware store.
Available departments: {dept_list}
Return ONLY valid JSON:
{{"store_name": "...", "products": [{{"name": "...", "quantity": 1, "price": 9.99, "cost": 7.99, "original_sku": "...", "suggested_department": "PLU"}}], "total": 99.99, "date": "2024-01-15"}}
Use EFFECTIVE price (after discounts). Match products to departments."""
        ).with_model("gemini", "gemini-3-flash-preview")
        
        file_content = FileContentWithMimeType(file_path=temp_file_path, mime_type="application/pdf")
        user_message = UserMessage(
            text="Extract all product information. Return only valid JSON.",
            file_contents=[file_content]
        )
        
        response = await chat.send_message(user_message)
        
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

@api_router.post("/vendors/{vendor_id}/import-products")
async def import_vendor_products(vendor_id: str, products: List[dict], current_user: dict = Depends(require_role("admin", "warehouse_manager"))):
    vendor = await db.vendors.find_one({"id": vendor_id}, {"_id": 0})
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")
    
    imported = []
    errors = []
    
    for item in products:
        try:
            dept_code = item.get("suggested_department", "HDW")
            department = await db.departments.find_one({"code": dept_code}, {"_id": 0})
            
            if not department:
                department = await db.departments.find_one({"code": "HDW"}, {"_id": 0})
                if not department:
                    errors.append({"product": item.get("name"), "error": "No valid department"})
                    continue
            
            sku = await generate_sku(department["code"])
            
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
                original_sku=item.get("original_sku")
            )
            
            await db.products.insert_one(product.model_dump())
            imported.append(product)
            await db.departments.update_one({"id": department["id"]}, {"$inc": {"product_count": 1}})
            await db.vendors.update_one({"id": vendor_id}, {"$inc": {"product_count": 1}})
            
        except Exception as e:
            errors.append({"product": item.get("name"), "error": str(e)})
    
    return {"imported": len(imported), "errors": len(errors), "products": imported, "error_details": errors}

@api_router.post("/receipts/import")
async def import_receipt_products(products: List[ExtractedProduct], department_id: str, current_user: dict = Depends(require_role("admin", "warehouse_manager"))):
    department = await db.departments.find_one({"id": department_id}, {"_id": 0})
    if not department:
        raise HTTPException(status_code=400, detail="Department not found")
    
    imported = []
    for item in products:
        sku = await generate_sku(department["code"])
        product = Product(
            sku=sku,
            name=item.name,
            price=item.price,
            cost=round(item.price * 0.7, 2),
            quantity=item.quantity,
            min_stock=5,
            department_id=department_id,
            department_name=department["name"],
            original_sku=item.original_sku
        )
        await db.products.insert_one(product.model_dump())
        imported.append(product)
    
    await db.departments.update_one({"id": department_id}, {"$inc": {"product_count": len(imported)}})
    
    return {"imported": len(imported), "products": imported}

# ==================== STRIPE PAYMENTS ====================

class CreatePaymentRequest(BaseModel):
    withdrawal_id: str
    origin_url: str

@api_router.post("/payments/create-checkout")
async def create_payment_checkout(data: CreatePaymentRequest, request: Request, current_user: dict = Depends(get_current_user)):
    """Create a Stripe checkout session for a withdrawal"""
    
    # Fetch the withdrawal
    withdrawal = await db.withdrawals.find_one({"id": data.withdrawal_id}, {"_id": 0})
    if not withdrawal:
        raise HTTPException(status_code=404, detail="Withdrawal not found")
    
    # Only allow payment for unpaid withdrawals
    if withdrawal.get("payment_status") == "paid":
        raise HTTPException(status_code=400, detail="This withdrawal is already paid")
    
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
        await db.payment_transactions.insert_one(payment_record)
        
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
    
    stripe_api_key = os.environ.get("STRIPE_API_KEY")
    if not stripe_api_key:
        raise HTTPException(status_code=500, detail="Stripe not configured")
    
    host_url = str(request.base_url)
    webhook_url = f"{host_url}api/webhook/stripe"
    stripe_checkout = StripeCheckout(api_key=stripe_api_key, webhook_url=webhook_url)
    
    try:
        status: CheckoutStatusResponse = await stripe_checkout.get_checkout_status(session_id)
        
        # Find the payment transaction
        payment = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
        
        if payment and status.payment_status == "paid" and payment.get("payment_status") != "paid":
            # Update payment transaction
            await db.payment_transactions.update_one(
                {"session_id": session_id},
                {"$set": {
                    "payment_status": "paid",
                    "status": "complete",
                    "paid_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            
            # Update the withdrawal
            if payment.get("withdrawal_id"):
                await db.withdrawals.update_one(
                    {"id": payment["withdrawal_id"]},
                    {"$set": {
                        "payment_status": "paid",
                        "paid_at": datetime.now(timezone.utc).isoformat(),
                        "stripe_session_id": session_id
                    }}
                )
        elif status.status == "expired":
            await db.payment_transactions.update_one(
                {"session_id": session_id},
                {"$set": {
                    "payment_status": "expired",
                    "status": "expired"
                }}
            )
        
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
            payment = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
            
            if payment and payment.get("payment_status") != "paid":
                await db.payment_transactions.update_one(
                    {"session_id": session_id},
                    {"$set": {
                        "payment_status": "paid",
                        "status": "complete",
                        "paid_at": datetime.now(timezone.utc).isoformat()
                    }}
                )
                
                # Update withdrawal
                if payment.get("withdrawal_id"):
                    await db.withdrawals.update_one(
                        {"id": payment["withdrawal_id"]},
                        {"$set": {
                            "payment_status": "paid",
                            "paid_at": datetime.now(timezone.utc).isoformat(),
                            "stripe_session_id": session_id
                        }}
                    )
        
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
        existing = await db.departments.find_one({"code": dept_data["code"]})
        if not existing:
            dept = Department(**dept_data)
            await db.departments.insert_one(dept.model_dump())
            created += 1
    
    return {"message": f"Seeded {created} departments"}

# ==================== MAIN ====================

@api_router.get("/")
async def root():
    return {"message": "Supply Yard API - Material Management System"}

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
