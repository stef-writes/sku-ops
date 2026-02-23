from fastapi import FastAPI, APIRouter, HTTPException, Depends, UploadFile, File
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
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

class UserCreate(BaseModel):
    email: str
    password: str
    name: str
    role: str = "employee"  # admin, manager, employee

class UserLogin(BaseModel):
    email: str
    password: str

class User(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    email: str
    name: str
    role: str = "employee"
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class DepartmentCreate(BaseModel):
    name: str
    code: str  # 3-letter code like LUM, PLU, ELE
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
    original_sku: Optional[str] = None  # Original SKU from source store
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
    sku: str  # Our internal SKU: DEPT-XXXXX
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

class SaleItem(BaseModel):
    product_id: str
    sku: str
    name: str
    quantity: int
    price: float
    subtotal: float

class SaleCreate(BaseModel):
    items: List[SaleItem]
    payment_method: str = "cash"  # cash, card
    customer_name: Optional[str] = None
    notes: Optional[str] = None

class Sale(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    items: List[SaleItem]
    subtotal: float
    tax: float
    total: float
    payment_method: str = "cash"
    customer_name: Optional[str] = None
    notes: Optional[str] = None
    cashier_id: str
    cashier_name: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class ExtractedProduct(BaseModel):
    name: str
    quantity: int = 1
    price: float
    original_sku: Optional[str] = None

class ReceiptExtraction(BaseModel):
    store_name: str
    products: List[ExtractedProduct]
    total: float
    date: Optional[str] = None

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
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

# ==================== SKU GENERATOR ====================

async def generate_sku(department_code: str) -> str:
    """Generate unique SKU in format: DEPT-XXXXX"""
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
    
    user = User(
        email=data.email,
        name=data.name,
        role=data.role
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
    
    token = create_token(user["id"], user["email"], user["role"])
    user_response = {k: v for k, v in user.items() if k not in ["_id", "password"]}
    return {"token": token, "user": user_response}

@api_router.get("/auth/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    return current_user

# ==================== DEPARTMENT ROUTES ====================

@api_router.get("/departments", response_model=List[Department])
async def get_departments(current_user: dict = Depends(get_current_user)):
    departments = await db.departments.find({}, {"_id": 0}).to_list(100)
    return departments

@api_router.post("/departments", response_model=Department)
async def create_department(data: DepartmentCreate, current_user: dict = Depends(get_current_user)):
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
async def update_department(dept_id: str, data: DepartmentCreate, current_user: dict = Depends(get_current_user)):
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
async def delete_department(dept_id: str, current_user: dict = Depends(get_current_user)):
    product_count = await db.products.count_documents({"department_id": dept_id})
    if product_count > 0:
        raise HTTPException(status_code=400, detail="Cannot delete department with products")
    
    result = await db.departments.delete_one({"id": dept_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Department not found")
    return {"message": "Department deleted"}

# ==================== VENDOR ROUTES ====================

@api_router.get("/vendors", response_model=List[Vendor])
async def get_vendors(current_user: dict = Depends(get_current_user)):
    vendors = await db.vendors.find({}, {"_id": 0}).to_list(100)
    return vendors

@api_router.post("/vendors", response_model=Vendor)
async def create_vendor(data: VendorCreate, current_user: dict = Depends(get_current_user)):
    vendor = Vendor(**data.model_dump())
    await db.vendors.insert_one(vendor.model_dump())
    return vendor

@api_router.put("/vendors/{vendor_id}", response_model=Vendor)
async def update_vendor(vendor_id: str, data: VendorCreate, current_user: dict = Depends(get_current_user)):
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
async def delete_vendor(vendor_id: str, current_user: dict = Depends(get_current_user)):
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
async def create_product(data: ProductCreate, current_user: dict = Depends(get_current_user)):
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
    
    # Update department product count
    await db.departments.update_one(
        {"id": data.department_id},
        {"$inc": {"product_count": 1}}
    )
    
    return product

@api_router.put("/products/{product_id}", response_model=Product)
async def update_product(product_id: str, data: ProductUpdate, current_user: dict = Depends(get_current_user)):
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
async def delete_product(product_id: str, current_user: dict = Depends(get_current_user)):
    product = await db.products.find_one({"id": product_id})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    await db.products.delete_one({"id": product_id})
    
    # Update department product count
    await db.departments.update_one(
        {"id": product["department_id"]},
        {"$inc": {"product_count": -1}}
    )
    
    return {"message": "Product deleted"}

# ==================== POS / SALES ROUTES ====================

@api_router.post("/sales", response_model=Sale)
async def create_sale(data: SaleCreate, current_user: dict = Depends(get_current_user)):
    subtotal = sum(item.subtotal for item in data.items)
    tax = round(subtotal * 0.08, 2)  # 8% tax
    total = round(subtotal + tax, 2)
    
    sale = Sale(
        items=data.items,
        subtotal=subtotal,
        tax=tax,
        total=total,
        payment_method=data.payment_method,
        customer_name=data.customer_name,
        notes=data.notes,
        cashier_id=current_user["id"],
        cashier_name=current_user.get("name", "")
    )
    
    await db.sales.insert_one(sale.model_dump())
    
    # Update product quantities
    for item in data.items:
        await db.products.update_one(
            {"id": item.product_id},
            {"$inc": {"quantity": -item.quantity}}
        )
    
    return sale

@api_router.get("/sales", response_model=List[Sale])
async def get_sales(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    query = {}
    if start_date:
        query["created_at"] = {"$gte": start_date}
    if end_date:
        if "created_at" in query:
            query["created_at"]["$lte"] = end_date
        else:
            query["created_at"] = {"$lte": end_date}
    
    sales = await db.sales.find(query, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return sales

@api_router.get("/sales/{sale_id}", response_model=Sale)
async def get_sale(sale_id: str, current_user: dict = Depends(get_current_user)):
    sale = await db.sales.find_one({"id": sale_id}, {"_id": 0})
    if not sale:
        raise HTTPException(status_code=404, detail="Sale not found")
    return sale

# ==================== RECEIPT OCR ROUTES ====================

@api_router.post("/receipts/extract")
async def extract_receipt(file: UploadFile = File(...), current_user: dict = Depends(get_current_user)):
    """Extract product information from uploaded receipt image using Gemini 3 Flash"""
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
            }
            If you cannot determine a field, use reasonable defaults (quantity=1, date=null).
            Extract all visible products with their prices. SKU may not always be visible."""
        ).with_model("gemini", "gemini-3-flash-preview")
        
        image_content = ImageContent(image_base64=image_base64)
        user_message = UserMessage(
            text="Extract all product information from this receipt. Return only valid JSON.",
            image_contents=[image_content]
        )
        
        response = await chat.send_message(user_message)
        
        # Parse the JSON response
        import json
        import re
        
        # Try to extract JSON from the response
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

@api_router.post("/receipts/import")
async def import_receipt_products(
    products: List[ExtractedProduct],
    department_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Import extracted products into inventory with new SKUs"""
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
            cost=round(item.price * 0.7, 2),  # Estimate cost as 70% of price
            quantity=item.quantity,
            min_stock=5,
            department_id=department_id,
            department_name=department["name"],
            original_sku=item.original_sku
        )
        await db.products.insert_one(product.model_dump())
        imported.append(product)
    
    # Update department product count
    await db.departments.update_one(
        {"id": department_id},
        {"$inc": {"product_count": len(imported)}}
    )
    
    return {"imported": len(imported), "products": imported}

# ==================== REPORTS ROUTES ====================

@api_router.get("/reports/sales")
async def get_sales_report(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    query = {}
    if start_date:
        query["created_at"] = {"$gte": start_date}
    if end_date:
        if "created_at" in query:
            query["created_at"]["$lte"] = end_date
        else:
            query["created_at"] = {"$lte": end_date}
    
    sales = await db.sales.find(query, {"_id": 0}).to_list(10000)
    
    total_revenue = sum(s.get("total", 0) for s in sales)
    total_tax = sum(s.get("tax", 0) for s in sales)
    total_transactions = len(sales)
    
    # Sales by payment method
    by_payment = {}
    for sale in sales:
        method = sale.get("payment_method", "cash")
        by_payment[method] = by_payment.get(method, 0) + sale.get("total", 0)
    
    # Top selling products
    product_sales = {}
    for sale in sales:
        for item in sale.get("items", []):
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
        "by_payment_method": by_payment,
        "top_products": top_products
    }

@api_router.get("/reports/inventory")
async def get_inventory_report(current_user: dict = Depends(get_current_user)):
    products = await db.products.find({}, {"_id": 0}).to_list(10000)
    
    total_products = len(products)
    total_value = sum(p.get("price", 0) * p.get("quantity", 0) for p in products)
    total_cost = sum(p.get("cost", 0) * p.get("quantity", 0) for p in products)
    low_stock = [p for p in products if p.get("quantity", 0) <= p.get("min_stock", 5)]
    out_of_stock = [p for p in products if p.get("quantity", 0) == 0]
    
    # By department
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

# ==================== DASHBOARD ROUTES ====================

@api_router.get("/dashboard/stats")
async def get_dashboard_stats(current_user: dict = Depends(get_current_user)):
    # Get today's date range
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_str = today.isoformat()
    
    # Today's sales
    today_sales = await db.sales.find({"created_at": {"$gte": today_str}}, {"_id": 0}).to_list(1000)
    today_revenue = sum(s.get("total", 0) for s in today_sales)
    today_transactions = len(today_sales)
    
    # Total products and low stock
    total_products = await db.products.count_documents({})
    low_stock_products = await db.products.count_documents({"$expr": {"$lte": ["$quantity", "$min_stock"]}})
    
    # Total vendors
    total_vendors = await db.vendors.count_documents({})
    
    # Recent sales
    recent_sales = await db.sales.find({}, {"_id": 0}).sort("created_at", -1).to_list(5)
    
    # Low stock alerts
    low_stock_items = await db.products.find(
        {"$expr": {"$lte": ["$quantity", "$min_stock"]}},
        {"_id": 0}
    ).to_list(10)
    
    return {
        "today_revenue": round(today_revenue, 2),
        "today_transactions": today_transactions,
        "total_products": total_products,
        "low_stock_count": low_stock_products,
        "total_vendors": total_vendors,
        "recent_sales": recent_sales,
        "low_stock_alerts": low_stock_items
    }

# ==================== SEED DATA ====================

@api_router.post("/seed/departments")
async def seed_departments():
    """Seed standard hardware store departments"""
    standard_departments = [
        {"name": "Lumber", "code": "LUM", "description": "Wood, plywood, boards, and lumber products"},
        {"name": "Plumbing", "code": "PLU", "description": "Pipes, fittings, fixtures, and plumbing supplies"},
        {"name": "Electrical", "code": "ELE", "description": "Wiring, outlets, switches, and electrical supplies"},
        {"name": "Paint", "code": "PNT", "description": "Paint, stains, brushes, and painting supplies"},
        {"name": "Tools", "code": "TOL", "description": "Hand tools, power tools, and accessories"},
        {"name": "Hardware", "code": "HDW", "description": "Fasteners, hinges, locks, and general hardware"},
        {"name": "Garden", "code": "GDN", "description": "Plants, soil, fertilizers, and garden supplies"},
        {"name": "Appliances", "code": "APP", "description": "Home appliances and accessories"}
    ]
    
    created = 0
    for dept_data in standard_departments:
        existing = await db.departments.find_one({"code": dept_data["code"]})
        if not existing:
            dept = Department(**dept_data)
            await db.departments.insert_one(dept.model_dump())
            created += 1
    
    return {"message": f"Seeded {created} departments"}

# ==================== MAIN SETUP ====================

@api_router.get("/")
async def root():
    return {"message": "Hardware Store API"}

# Include the router in the main app
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
