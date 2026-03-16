"""Typed seed data — single source of truth for all demo/dev seed scripts.

Every piece of demo data is defined here as a validated Pydantic model.
A typo, wrong type, or missing required field will blow up at import time
instead of silently corrupting a half-seeded database.

Consumed by: seed_realistic.py, seed.py, seed_full.py
"""

from __future__ import annotations

from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class SeedOrg(BaseModel):
    id: str
    name: str
    slug: str


class SeedUser(BaseModel):
    email: str
    password: str
    name: str
    role: str
    company: str = ""
    billing_entity: str = ""


class SeedDepartment(BaseModel):
    name: str
    code: str
    description: str = ""


class SeedVendor(BaseModel):
    name: str
    contact_name: str
    email: str
    phone: str
    address: str


class SeedProduct(BaseModel):
    name: str
    dept: str
    vendor: int
    price: float
    cost: float
    qty: int
    min: int
    unit: str
    product: str = ""
    vendor_sku: str = ""
    purchase_uom: str | None = None
    purchase_pack_qty: int = 1


class SeedWithdrawalItem(BaseModel):
    product_name: str
    quantity: int


class SeedWithdrawalScenario(BaseModel):
    job_id: str
    service_address: str
    days_ago: int
    items: list[SeedWithdrawalItem]


class SeedContractor(BaseModel):
    name: str
    email: str
    company: str
    billing_entity: str
    phone: str


class SeedJob(BaseModel):
    id: str
    address: str


class SeedTenant(BaseModel):
    id: str
    name: str
    slug: str


class SeedTenantUser(BaseModel):
    email: str
    name: str
    role: str


# ---------------------------------------------------------------------------
# Data — Organization & Users
# ---------------------------------------------------------------------------

ORG = SeedOrg(id="default", name="Demo Supply Yard", slug="default")

ADMIN_USER = SeedUser(
    email="admin@demo.local",
    password="demo123",  # noqa: S106
    name="Admin",
    role="admin",
)

CONTRACTOR_USER = SeedUser(
    email="contractor@demo.local",
    password="demo123",  # noqa: S106
    name="Demo Contractor",
    role="contractor",
    company="ABC Plumbing",
    billing_entity="ABC Plumbing",
)

# ---------------------------------------------------------------------------
# Data — Departments
# ---------------------------------------------------------------------------

DEPARTMENTS: list[SeedDepartment] = [
    SeedDepartment(name="Lumber", code="LUM", description="Wood, plywood, boards"),
    SeedDepartment(name="Plumbing", code="PLU", description="Pipes, fittings, fixtures"),
    SeedDepartment(name="Electrical", code="ELE", description="Wiring, outlets, switches"),
    SeedDepartment(name="Paint", code="PNT", description="Paint, stains, brushes"),
    SeedDepartment(name="Tools", code="TOL", description="Hand tools, power tools"),
    SeedDepartment(name="Hardware", code="HDW", description="Fasteners, hinges, locks"),
    SeedDepartment(name="Garden", code="GDN", description="Plants, soil, fertilizers"),
    SeedDepartment(name="Appliances", code="APP", description="Home appliances"),
]

# ---------------------------------------------------------------------------
# Data — Vendors
# ---------------------------------------------------------------------------

VENDORS: list[SeedVendor] = [
    SeedVendor(
        name="Johnson Lumber Co",
        contact_name="Mike Johnson",
        email="mike@johnsonlumber.com",
        phone="555-0101",
        address="100 Timber Rd",
    ),
    SeedVendor(
        name="Pacific Plumbing Supply",
        contact_name="Sarah Chen",
        email="sarah@pacificplumbing.com",
        phone="555-0202",
        address="250 Pipe Ave",
    ),
    SeedVendor(
        name="National Paint & Coatings",
        contact_name="Tom Rivera",
        email="tom@nationalpaint.com",
        phone="555-0303",
        address="88 Color Blvd",
    ),
    SeedVendor(
        name="Allied Electrical Dist.",
        contact_name="Karen Park",
        email="karen@alliedelectric.com",
        phone="555-0404",
        address="300 Watt St",
    ),
    SeedVendor(
        name="FastenAll Hardware",
        contact_name="Dave Wilson",
        email="dave@fastenall.com",
        phone="555-0505",
        address="42 Bolt Lane",
    ),
    SeedVendor(
        name="Pro Tool Warehouse",
        contact_name="Lisa Ortega",
        email="lisa@protool.com",
        phone="555-0606",
        address="78 Wrench Way",
    ),
]

# ---------------------------------------------------------------------------
# Data — Products (vendor field is an index into VENDORS)
# ---------------------------------------------------------------------------

PRODUCTS: list[SeedProduct] = [
    # === LUMBER (Johnson Lumber) ===
    SeedProduct(
        name="2x4x8 Stud SPF",
        dept="LUM",
        vendor=0,
        price=5.99,
        cost=3.50,
        qty=450,
        min=100,
        unit="each",
        product="Dimensional Lumber",
        vendor_sku="JL-2X4-8",
    ),
    SeedProduct(
        name="2x6x12 Douglas Fir",
        dept="LUM",
        vendor=0,
        price=12.49,
        cost=7.80,
        qty=180,
        min=40,
        unit="each",
        product="Dimensional Lumber",
        vendor_sku="JL-2X6-12",
    ),
    SeedProduct(
        name="4x8 1/2in CDX Plywood",
        dept="LUM",
        vendor=0,
        price=42.99,
        cost=28.00,
        qty=85,
        min=20,
        unit="each",
        product="Sheet Goods",
        vendor_sku="JL-PLY-12",
    ),
    SeedProduct(
        name="4x8 3/4in Sanded Plywood",
        dept="LUM",
        vendor=0,
        price=64.99,
        cost=42.00,
        qty=45,
        min=15,
        unit="each",
        product="Sheet Goods",
        vendor_sku="JL-PLY-34",
    ),
    SeedProduct(
        name="1x6x8 Cedar Fence Board",
        dept="LUM",
        vendor=0,
        price=4.29,
        cost=2.50,
        qty=600,
        min=150,
        unit="each",
        vendor_sku="JL-CED-168",
    ),
    SeedProduct(
        name="2x4x10 Pressure Treated",
        dept="LUM",
        vendor=0,
        price=9.99,
        cost=6.20,
        qty=220,
        min=50,
        unit="each",
        product="Pressure Treated Lumber",
        vendor_sku="JL-PT-2410",
    ),
    SeedProduct(
        name="4x4x8 Post Treated",
        dept="LUM",
        vendor=0,
        price=14.99,
        cost=9.00,
        qty=60,
        min=20,
        unit="each",
        product="Pressure Treated Lumber",
        vendor_sku="JL-PT-448",
    ),
    SeedProduct(
        name="1x4x8 Furring Strip",
        dept="LUM",
        vendor=0,
        price=2.49,
        cost=1.30,
        qty=300,
        min=80,
        unit="each",
        vendor_sku="JL-FUR-148",
    ),
    # === PLUMBING (Pacific Plumbing) ===
    SeedProduct(
        name="1/2in PEX Pipe 100ft",
        dept="PLU",
        vendor=1,
        price=89.99,
        cost=52.00,
        qty=35,
        min=10,
        unit="roll",
        product="PEX Tubing",
        vendor_sku="PP-PEX-12-100",
    ),
    SeedProduct(
        name="3/4in PEX Pipe 100ft",
        dept="PLU",
        vendor=1,
        price=119.99,
        cost=72.00,
        qty=20,
        min=8,
        unit="roll",
        product="PEX Tubing",
        vendor_sku="PP-PEX-34-100",
    ),
    SeedProduct(
        name="1/2in Copper Elbow 90deg",
        dept="PLU",
        vendor=1,
        price=2.49,
        cost=1.20,
        qty=250,
        min=50,
        unit="each",
        product="Copper Fittings",
        vendor_sku="PP-CU-EL90",
    ),
    SeedProduct(
        name="3/4in PVC Coupling",
        dept="PLU",
        vendor=1,
        price=0.89,
        cost=0.35,
        qty=400,
        min=100,
        unit="each",
        vendor_sku="PP-PVC-CPL34",
    ),
    SeedProduct(
        name="SharkBite 1/2in Push Fitting",
        dept="PLU",
        vendor=1,
        price=7.99,
        cost=4.20,
        qty=80,
        min=20,
        unit="each",
        vendor_sku="PP-SB-12",
    ),
    SeedProduct(
        name="PVC Cement 16oz",
        dept="PLU",
        vendor=1,
        price=8.49,
        cost=4.50,
        qty=45,
        min=15,
        unit="each",
        vendor_sku="PP-CEM-16",
    ),
    SeedProduct(
        name="Teflon Tape 1/2in x 520in",
        dept="PLU",
        vendor=1,
        price=1.99,
        cost=0.60,
        qty=200,
        min=50,
        unit="roll",
        vendor_sku="PP-TEF-12",
    ),
    # === PAINT (National Paint) ===
    SeedProduct(
        name="5 Gal Interior Flat White",
        dept="PNT",
        vendor=2,
        price=149.99,
        cost=85.00,
        qty=18,
        min=8,
        unit="gallon",
        product="Interior Paint",
        vendor_sku="NP-INT-FW5",
        purchase_uom="pail",
        purchase_pack_qty=5,
    ),
    SeedProduct(
        name="5 Gal Interior Eggshell White",
        dept="PNT",
        vendor=2,
        price=164.99,
        cost=95.00,
        qty=14,
        min=6,
        unit="gallon",
        product="Interior Paint",
        vendor_sku="NP-INT-EW5",
        purchase_uom="pail",
        purchase_pack_qty=5,
    ),
    SeedProduct(
        name="1 Gal Exterior Semi-Gloss White",
        dept="PNT",
        vendor=2,
        price=44.99,
        cost=26.00,
        qty=30,
        min=10,
        unit="gallon",
        product="Exterior Paint",
        vendor_sku="NP-EXT-SGW1",
    ),
    SeedProduct(
        name="Primer 5 Gal",
        dept="PNT",
        vendor=2,
        price=109.99,
        cost=62.00,
        qty=12,
        min=5,
        unit="gallon",
        product="Interior Paint",
        vendor_sku="NP-PRM-5",
        purchase_uom="pail",
        purchase_pack_qty=5,
    ),
    SeedProduct(
        name="Wood Stain Golden Oak Qt",
        dept="PNT",
        vendor=2,
        price=18.99,
        cost=10.50,
        qty=25,
        min=8,
        unit="quart",
        vendor_sku="NP-STN-GO",
    ),
    SeedProduct(
        name="2in Angle Sash Brush",
        dept="PNT",
        vendor=2,
        price=8.99,
        cost=4.00,
        qty=60,
        min=20,
        unit="each",
        product="Paint Brushes",
        vendor_sku="NP-BR-2AS",
    ),
    SeedProduct(
        name="9in Roller Cover 3/8nap 3pk",
        dept="PNT",
        vendor=2,
        price=12.99,
        cost=6.50,
        qty=40,
        min=15,
        unit="pack",
        product="Paint Brushes",
        vendor_sku="NP-RC-938",
    ),
    SeedProduct(
        name="Painters Tape Blue 1.88in x 60yd",
        dept="PNT",
        vendor=2,
        price=7.49,
        cost=3.80,
        qty=75,
        min=25,
        unit="roll",
        vendor_sku="NP-TPB-188",
    ),
    # === ELECTRICAL (Allied Electrical) ===
    SeedProduct(
        name="12/2 NM-B Romex 250ft",
        dept="ELE",
        vendor=3,
        price=149.99,
        cost=92.00,
        qty=15,
        min=5,
        unit="roll",
        product="Romex Wire",
        vendor_sku="AE-ROM-122",
    ),
    SeedProduct(
        name="14/2 NM-B Romex 250ft",
        dept="ELE",
        vendor=3,
        price=119.99,
        cost=72.00,
        qty=18,
        min=5,
        unit="roll",
        product="Romex Wire",
        vendor_sku="AE-ROM-142",
    ),
    SeedProduct(
        name="Single Gang Old Work Box",
        dept="ELE",
        vendor=3,
        price=2.99,
        cost=1.40,
        qty=150,
        min=40,
        unit="each",
        vendor_sku="AE-BOX-1G",
    ),
    SeedProduct(
        name="Decora Switch White",
        dept="ELE",
        vendor=3,
        price=3.49,
        cost=1.60,
        qty=120,
        min=30,
        unit="each",
        product="Switches & Outlets",
        vendor_sku="AE-SW-DW",
    ),
    SeedProduct(
        name="Decora Outlet 15A White",
        dept="ELE",
        vendor=3,
        price=2.99,
        cost=1.30,
        qty=140,
        min=35,
        unit="each",
        product="Switches & Outlets",
        vendor_sku="AE-OUT-15W",
    ),
    SeedProduct(
        name="GFCI Outlet 15A White",
        dept="ELE",
        vendor=3,
        price=16.99,
        cost=9.00,
        qty=35,
        min=10,
        unit="each",
        product="Switches & Outlets",
        vendor_sku="AE-GFCI-15W",
    ),
    SeedProduct(
        name="Wire Nuts Assorted 100pk",
        dept="ELE",
        vendor=3,
        price=9.99,
        cost=4.20,
        qty=50,
        min=15,
        unit="pack",
        vendor_sku="AE-WN-100",
        purchase_uom="box",
        purchase_pack_qty=100,
    ),
    SeedProduct(
        name="Electrical Tape Black 3/4in",
        dept="ELE",
        vendor=3,
        price=3.49,
        cost=1.50,
        qty=90,
        min=25,
        unit="roll",
        vendor_sku="AE-ET-BK",
    ),
    # === HARDWARE (FastenAll) ===
    SeedProduct(
        name="#8 x 2-1/2in Deck Screw 5lb",
        dept="HDW",
        vendor=4,
        price=24.99,
        cost=13.00,
        qty=55,
        min=15,
        unit="box",
        product="Screws",
        vendor_sku="FA-DS-825",
    ),
    SeedProduct(
        name="#8 x 1-5/8in Drywall Screw 1lb",
        dept="HDW",
        vendor=4,
        price=6.99,
        cost=3.20,
        qty=80,
        min=25,
        unit="box",
        product="Screws",
        vendor_sku="FA-DW-816",
    ),
    SeedProduct(
        name="16d Framing Nail 50lb",
        dept="HDW",
        vendor=4,
        price=89.99,
        cost=52.00,
        qty=12,
        min=5,
        unit="box",
        vendor_sku="FA-FN-16D",
    ),
    SeedProduct(
        name="3in Cabinet Hinge Satin Nickel",
        dept="HDW",
        vendor=4,
        price=4.99,
        cost=2.30,
        qty=100,
        min=30,
        unit="each",
        product="Door Hardware",
        vendor_sku="FA-HNG-3SN",
    ),
    SeedProduct(
        name="Door Knob Passage Satin Nickel",
        dept="HDW",
        vendor=4,
        price=19.99,
        cost=10.50,
        qty=30,
        min=10,
        unit="each",
        product="Door Hardware",
        vendor_sku="FA-DK-PSN",
    ),
    SeedProduct(
        name="Deadbolt Single Cyl Satin Nickel",
        dept="HDW",
        vendor=4,
        price=34.99,
        cost=18.00,
        qty=20,
        min=8,
        unit="each",
        product="Door Hardware",
        vendor_sku="FA-DB-SSN",
    ),
    SeedProduct(
        name="Construction Adhesive 10oz",
        dept="HDW",
        vendor=4,
        price=5.99,
        cost=2.80,
        qty=60,
        min=20,
        unit="each",
        vendor_sku="FA-CA-10",
    ),
    # === Multi-vendor items ===
    SeedProduct(
        name="2in Angle Sash Brush",
        dept="PNT",
        vendor=4,
        price=7.99,
        cost=3.50,
        qty=40,
        min=15,
        unit="each",
        product="Paint Brushes",
        vendor_sku="FA-BR-2AS",
    ),
    SeedProduct(
        name="Painters Tape Blue 1.88in x 60yd",
        dept="PNT",
        vendor=4,
        price=6.99,
        cost=3.50,
        qty=50,
        min=20,
        unit="roll",
        vendor_sku="FA-TPB-188",
    ),
    SeedProduct(
        name="Electrical Tape Black 3/4in",
        dept="ELE",
        vendor=4,
        price=2.99,
        cost=1.20,
        qty=60,
        min=20,
        unit="roll",
        vendor_sku="FA-ET-BK",
    ),
    # === TOOLS (Pro Tool Warehouse) ===
    SeedProduct(
        name="20V Cordless Drill Kit",
        dept="TOL",
        vendor=5,
        price=129.99,
        cost=78.00,
        qty=8,
        min=3,
        unit="each",
        vendor_sku="PT-DRL-20V",
    ),
    SeedProduct(
        name="25ft Tape Measure",
        dept="TOL",
        vendor=5,
        price=14.99,
        cost=7.50,
        qty=25,
        min=10,
        unit="each",
        vendor_sku="PT-TM-25",
    ),
    SeedProduct(
        name="Speed Square 7in",
        dept="TOL",
        vendor=5,
        price=9.99,
        cost=5.00,
        qty=20,
        min=8,
        unit="each",
        vendor_sku="PT-SQ-7",
    ),
    SeedProduct(
        name="Utility Knife Retractable",
        dept="TOL",
        vendor=5,
        price=7.99,
        cost=3.80,
        qty=35,
        min=12,
        unit="each",
        vendor_sku="PT-UK-R",
    ),
    SeedProduct(
        name="Framing Hammer 22oz",
        dept="TOL",
        vendor=5,
        price=24.99,
        cost=13.00,
        qty=15,
        min=5,
        unit="each",
        vendor_sku="PT-HM-22",
    ),
    SeedProduct(
        name="Chalk Line Kit 100ft",
        dept="TOL",
        vendor=5,
        price=11.99,
        cost=6.00,
        qty=18,
        min=6,
        unit="each",
        vendor_sku="PT-CL-100",
    ),
    SeedProduct(
        name="Level 48in Aluminum",
        dept="TOL",
        vendor=5,
        price=34.99,
        cost=19.00,
        qty=10,
        min=4,
        unit="each",
        vendor_sku="PT-LV-48",
    ),
]

# ---------------------------------------------------------------------------
# Data — Low stock trigger names (must match PRODUCTS[].name exactly)
# ---------------------------------------------------------------------------

LOW_STOCK_NAMES: list[str] = [
    "4x8 3/4in Sanded Plywood",
    "GFCI Outlet 15A White",
    "5 Gal Interior Eggshell White",
    "20V Cordless Drill Kit",
]

LOW_STOCK_NAMES_FULL: list[str] = [
    *LOW_STOCK_NAMES,
    "SharkBite 1/2in Push Fitting",
    "Deadbolt Single Cyl Satin Nickel",
]

# ---------------------------------------------------------------------------
# Data — Withdrawal scenarios (for seed_realistic)
# ---------------------------------------------------------------------------

WITHDRAWAL_SCENARIOS: list[SeedWithdrawalScenario] = [
    SeedWithdrawalScenario(
        job_id="JOB-2026-0041",
        service_address="1420 Oak Valley Dr",
        days_ago=12,
        items=[
            SeedWithdrawalItem(product_name="2x4x8 Stud SPF", quantity=40),
            SeedWithdrawalItem(product_name="4x8 1/2in CDX Plywood", quantity=8),
            SeedWithdrawalItem(product_name="#8 x 2-1/2in Deck Screw 5lb", quantity=3),
            SeedWithdrawalItem(product_name="16d Framing Nail 50lb", quantity=1),
        ],
    ),
    SeedWithdrawalScenario(
        job_id="JOB-2026-0041",
        service_address="1420 Oak Valley Dr",
        days_ago=9,
        items=[
            SeedWithdrawalItem(product_name="12/2 NM-B Romex 250ft", quantity=2),
            SeedWithdrawalItem(product_name="Single Gang Old Work Box", quantity=12),
            SeedWithdrawalItem(product_name="Decora Switch White", quantity=8),
            SeedWithdrawalItem(product_name="Decora Outlet 15A White", quantity=10),
            SeedWithdrawalItem(product_name="GFCI Outlet 15A White", quantity=3),
            SeedWithdrawalItem(product_name="Wire Nuts Assorted 100pk", quantity=2),
        ],
    ),
    SeedWithdrawalScenario(
        job_id="JOB-2026-0043",
        service_address="890 Maple Creek Ln",
        days_ago=7,
        items=[
            SeedWithdrawalItem(product_name="1/2in PEX Pipe 100ft", quantity=3),
            SeedWithdrawalItem(product_name="SharkBite 1/2in Push Fitting", quantity=8),
            SeedWithdrawalItem(product_name="1/2in Copper Elbow 90deg", quantity=15),
            SeedWithdrawalItem(product_name="Teflon Tape 1/2in x 520in", quantity=5),
            SeedWithdrawalItem(product_name="PVC Cement 16oz", quantity=2),
        ],
    ),
    SeedWithdrawalScenario(
        job_id="JOB-2026-0044",
        service_address="2250 Birch Hill Ct",
        days_ago=5,
        items=[
            SeedWithdrawalItem(product_name="5 Gal Interior Flat White", quantity=3),
            SeedWithdrawalItem(product_name="Primer 5 Gal", quantity=2),
            SeedWithdrawalItem(product_name="2in Angle Sash Brush", quantity=6),
            SeedWithdrawalItem(product_name="9in Roller Cover 3/8nap 3pk", quantity=4),
            SeedWithdrawalItem(product_name="Painters Tape Blue 1.88in x 60yd", quantity=8),
        ],
    ),
    SeedWithdrawalScenario(
        job_id="JOB-2026-0041",
        service_address="1420 Oak Valley Dr",
        days_ago=3,
        items=[
            SeedWithdrawalItem(product_name="2x4x8 Stud SPF", quantity=20),
            SeedWithdrawalItem(product_name="2x6x12 Douglas Fir", quantity=10),
            SeedWithdrawalItem(product_name="Construction Adhesive 10oz", quantity=4),
        ],
    ),
    SeedWithdrawalScenario(
        job_id="JOB-2026-0045",
        service_address="505 Elm Park Way",
        days_ago=1,
        items=[
            SeedWithdrawalItem(product_name="1x6x8 Cedar Fence Board", quantity=80),
            SeedWithdrawalItem(product_name="4x4x8 Post Treated", quantity=6),
            SeedWithdrawalItem(product_name="#8 x 2-1/2in Deck Screw 5lb", quantity=4),
        ],
    ),
]

# ---------------------------------------------------------------------------
# Data — Contractors (for seed_full)
# ---------------------------------------------------------------------------

CONTRACTORS: list[SeedContractor] = [
    SeedContractor(
        name="Mike Brennan",
        email="mike@brennanbuilders.com",
        company="Brennan Builders LLC",
        billing_entity="Brennan Builders LLC",
        phone="555-1001",
    ),
    SeedContractor(
        name="Jessica Tran",
        email="jtran@tranconstruction.com",
        company="Tran Construction Inc",
        billing_entity="Tran Construction Inc",
        phone="555-1002",
    ),
    SeedContractor(
        name="Carlos Medina",
        email="carlos@medinahomes.com",
        company="Medina Custom Homes",
        billing_entity="Medina Custom Homes",
        phone="555-1003",
    ),
    SeedContractor(
        name="Anita Kapoor",
        email="anita@kapoorenergy.com",
        company="Kapoor Energy Solutions",
        billing_entity="Kapoor Energy Solutions",
        phone="555-1004",
    ),
    SeedContractor(
        name="Ray Dubois",
        email="ray@duboismaintenance.com",
        company="DuBois Property Maintenance",
        billing_entity="DuBois Property Maintenance",
        phone="555-1005",
    ),
    SeedContractor(
        name="Sandra Walsh",
        email="swalsh@walshplumbing.com",
        company="Walsh Plumbing & Heating",
        billing_entity="Walsh Plumbing & Heating",
        phone="555-1006",
    ),
    SeedContractor(
        name="Derek Okonkwo",
        email="derek@deobuilds.com",
        company="DEO Builds",
        billing_entity="DEO Builds",
        phone="555-1007",
    ),
    SeedContractor(
        name="Linda Park",
        email="linda@parkrenovations.com",
        company="Park Renovations",
        billing_entity="Park Renovations",
        phone="555-1008",
    ),
]

# ---------------------------------------------------------------------------
# Data — Jobs (for seed_full)
# ---------------------------------------------------------------------------

JOBS: list[SeedJob] = [
    SeedJob(id="JOB-2026-0050", address="310 Evergreen Terrace"),
    SeedJob(id="JOB-2026-0051", address="742 Willow Springs Rd"),
    SeedJob(id="JOB-2026-0052", address="18 Granite Falls Ct"),
    SeedJob(id="JOB-2026-0053", address="5600 Lakeshore Blvd"),
    SeedJob(id="JOB-2026-0054", address="203 Cedar Ridge Ln"),
    SeedJob(id="JOB-2026-0055", address="880 Industrial Pkwy Unit 4"),
    SeedJob(id="JOB-2026-0056", address="1215 Sycamore Ave"),
    SeedJob(id="JOB-2026-0057", address="44 Harbor View Dr"),
    SeedJob(id="JOB-2026-0058", address="999 Pine Crest Loop"),
    SeedJob(id="JOB-2026-0059", address="66 Brookside Way"),
    SeedJob(id="JOB-2026-0060", address="2300 Mission Hill Rd"),
    SeedJob(id="JOB-2026-0061", address="411 Orchard Park Dr"),
]

# ---------------------------------------------------------------------------
# Data — Tenants (for seed.py multi-tenant demo)
# ---------------------------------------------------------------------------

TENANTS: list[SeedTenant] = [
    SeedTenant(id="north", name="Supply Yard North", slug="north"),
    SeedTenant(id="south", name="Supply Yard South", slug="south"),
]

TENANT_USERS: list[SeedTenantUser] = [
    SeedTenantUser(email="admin@{slug}.demo", name="Admin", role="admin"),
    SeedTenantUser(email="contractor@{slug}.demo", name="Contractor", role="contractor"),
]

RETURN_REASONS: list[str] = ["wrong_item", "defective", "overorder", "job_cancelled", "other"]
