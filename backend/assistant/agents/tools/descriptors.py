"""Tool descriptors for unified agent — used by tool index for semantic retrieval."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ToolDescriptor:
    """Structured descriptor for embedding and retrieval."""

    name: str
    description: str
    use_cases: list[str]


def get_unified_tool_descriptors() -> dict[str, ToolDescriptor]:
    """Return descriptors for all unified agent tools. Used by tool index."""
    return {
        "search_products": ToolDescriptor(
            "search_products",
            "Search products by name, SKU, or barcode.",
            ["find product", "lookup SKU", "barcode search"],
        ),
        "search_semantic": ToolDescriptor(
            "search_semantic",
            "Semantic/concept search for products. Use when exact search fails or query is descriptive.",
            ["concept search", "find by description", "fuzzy product search"],
        ),
        "get_product_details": ToolDescriptor(
            "get_product_details",
            "Get full details for one product by SKU: price, cost, vendor, UOM, barcode, reorder point.",
            ["product details", "single product", "SKU info"],
        ),
        "get_inventory_stats": ToolDescriptor(
            "get_inventory_stats",
            "Catalogue summary: total_skus, total_cost_value, low_stock_count, out_of_stock_count.",
            ["inventory summary", "catalogue stats", "stock counts"],
        ),
        "list_low_stock": ToolDescriptor(
            "list_low_stock",
            "List products at or below their reorder point.",
            ["low stock", "reorder point", "needs reorder"],
        ),
        "list_departments": ToolDescriptor(
            "list_departments",
            "List all departments with product counts.",
            ["departments", "categories"],
        ),
        "list_vendors": ToolDescriptor(
            "list_vendors",
            "List all vendors with product counts.",
            ["vendors", "suppliers"],
        ),
        "get_usage_velocity": ToolDescriptor(
            "get_usage_velocity",
            "How fast a product moves: total and average daily withdrawals over the last N days.",
            ["velocity", "usage rate", "movement"],
        ),
        "get_reorder_suggestions": ToolDescriptor(
            "get_reorder_suggestions",
            "Priority reorder list: low-stock products ranked by urgency.",
            ["reorder", "what to order", "urgent stock"],
        ),
        "get_department_health": ToolDescriptor(
            "get_department_health",
            "Per-department breakdown showing healthy, low-stock, and out-of-stock product counts.",
            ["department health", "department stats"],
        ),
        "get_slow_movers": ToolDescriptor(
            "get_slow_movers",
            "Products with stock on hand but very low or zero withdrawal activity.",
            ["slow movers", "dead stock", "stale inventory"],
        ),
        "get_top_products": ToolDescriptor(
            "get_top_products",
            "Top products by volume or revenue over a period.",
            ["top products", "best sellers", "revenue leaders"],
        ),
        "get_department_activity": ToolDescriptor(
            "get_department_activity",
            "Stock movement summary for a department over a period.",
            ["department activity", "department movement"],
        ),
        "forecast_stockout": ToolDescriptor(
            "forecast_stockout",
            "Products predicted to run out soonest based on recent withdrawal velocity.",
            ["stockout", "run out", "forecast"],
        ),
        "get_contractor_history": ToolDescriptor(
            "get_contractor_history",
            "Withdrawal history for a contractor (by name). Shows jobs, materials pulled, amounts.",
            ["contractor", "withdrawal history"],
        ),
        "get_job_materials": ToolDescriptor(
            "get_job_materials",
            "All materials pulled for a specific job ID.",
            ["job materials", "job details"],
        ),
        "list_recent_withdrawals": ToolDescriptor(
            "list_recent_withdrawals",
            "Recent material withdrawals across all jobs.",
            ["withdrawals", "recent activity"],
        ),
        "list_pending_material_requests": ToolDescriptor(
            "list_pending_material_requests",
            "Material requests from contractors awaiting approval.",
            ["pending requests", "material requests"],
        ),
        "get_daily_withdrawal_activity": ToolDescriptor(
            "get_daily_withdrawal_activity",
            "Daily withdrawal volume trends for a product or overall.",
            ["daily activity", "withdrawal trends"],
        ),
        "get_payment_status_breakdown": ToolDescriptor(
            "get_payment_status_breakdown",
            "Withdrawal totals grouped by payment status (paid/invoiced/unpaid) for the period.",
            ["payment status", "paid unpaid"],
        ),
        "get_invoice_summary": ToolDescriptor(
            "get_invoice_summary",
            "Invoice counts and totals grouped by status (draft, sent, paid).",
            ["invoices", "invoice status"],
        ),
        "get_outstanding_balances": ToolDescriptor(
            "get_outstanding_balances",
            "Unpaid withdrawal balances grouped by billing entity/contractor.",
            ["outstanding", "AR", "unpaid balances"],
        ),
        "get_revenue_summary": ToolDescriptor(
            "get_revenue_summary",
            "Revenue summary for the last N days: total revenue, tax collected, transaction count.",
            ["revenue", "sales summary"],
        ),
        "get_pl_summary": ToolDescriptor(
            "get_pl_summary",
            "Profit & loss for the last N days: revenue, COGS, gross profit and margin.",
            ["P&L", "profit loss", "margin"],
        ),
        "get_finance_top_products": ToolDescriptor(
            "get_finance_top_products",
            "Top revenue-generating products over a period.",
            ["top revenue", "finance top products"],
        ),
        "get_trend_series": ToolDescriptor(
            "get_trend_series",
            "Revenue, cost, or profit time series. Group by day, week, or month.",
            ["trends", "time series", "revenue over time"],
        ),
        "get_ar_aging": ToolDescriptor(
            "get_ar_aging",
            "Accounts receivable aging buckets by billing entity (current, 1-30, 31-60, 61-90, 90+).",
            ["AR aging", "receivables aging"],
        ),
        "get_product_margins": ToolDescriptor(
            "get_product_margins",
            "Per-product revenue, COGS, profit, and margin percentage.",
            ["margins", "product profitability"],
        ),
        "get_department_profitability": ToolDescriptor(
            "get_department_profitability",
            "Revenue, COGS, shrinkage, profit, and margin by department.",
            ["department profitability", "department P&L"],
        ),
        "get_job_profitability": ToolDescriptor(
            "get_job_profitability",
            "Per-job P&L with margins.",
            ["job profit", "job P&L"],
        ),
        "get_entity_summary": ToolDescriptor(
            "get_entity_summary",
            "Per billing entity: AR balance, revenue, cost, profit, transaction count.",
            ["billing entity", "entity summary"],
        ),
        "get_contractor_spend": ToolDescriptor(
            "get_contractor_spend",
            "Revenue and AR balance by contractor over the period.",
            ["contractor spend", "contractor revenue"],
        ),
        "get_purchase_spend": ToolDescriptor(
            "get_purchase_spend",
            "Total inventory additions from PO receipts in the period.",
            ["purchase spend", "PO receipts"],
        ),
        "get_vendor_catalog": ToolDescriptor(
            "get_vendor_catalog",
            "SKUs a vendor supplies with cost, lead time, MOQ, preferred status.",
            ["vendor catalog", "vendor products"],
        ),
        "get_vendor_performance": ToolDescriptor(
            "get_vendor_performance",
            "Vendor reliability: PO count, spend, avg lead time, fill rate.",
            ["vendor performance", "vendor reliability"],
        ),
        "get_sku_vendor_options": ToolDescriptor(
            "get_sku_vendor_options",
            "All vendors that supply a specific SKU with cost, lead time, MOQ, preferred, last PO date.",
            ["vendor options", "SKU vendors", "who supplies"],
        ),
        "get_purchase_history": ToolDescriptor(
            "get_purchase_history",
            "Recent POs for a vendor with items and costs.",
            ["purchase history", "PO history"],
        ),
        "get_po_summary": ToolDescriptor(
            "get_po_summary",
            "Purchase order counts and totals grouped by status (ordered/partial/received).",
            ["PO summary", "purchase orders"],
        ),
        "get_reorder_with_vendor_context": ToolDescriptor(
            "get_reorder_with_vendor_context",
            "Low-stock SKUs with vendor options (cost, lead time, preferred vendor) for procurement planning.",
            ["reorder plan", "procurement", "vendor options for reorder"],
        ),
        "list_all_vendors_detail": ToolDescriptor(
            "list_all_vendors_detail",
            "All vendors with ID, name, contact, email, phone.",
            ["all vendors", "vendor list"],
        ),
        "search_vendors_semantic": ToolDescriptor(
            "search_vendors_semantic",
            "Find vendors by description or concept.",
            ["find vendor", "vendor search", "that plumbing supplier"],
        ),
        "search_purchase_orders_semantic": ToolDescriptor(
            "search_purchase_orders_semantic",
            "Find POs by concept.",
            ["find PO", "PO search", "that order from last quarter"],
        ),
        "search_jobs_semantic": ToolDescriptor(
            "search_jobs_semantic",
            "Find jobs by concept.",
            ["find job", "job search", "that big job"],
        ),
        "run_weekly_sales_report": ToolDescriptor(
            "run_weekly_sales_report",
            "Generate a full weekly sales report: revenue, P&L, top products, outstanding balances.",
            ["weekly report", "sales report", "finance overview"],
        ),
        "run_inventory_overview": ToolDescriptor(
            "run_inventory_overview",
            "Generate a full inventory overview: stats, department health, low stock, slow movers.",
            ["inventory overview", "what needs attention", "stock health"],
        ),
        "analyze_procurement": ToolDescriptor(
            "analyze_procurement",
            "Delegate to the procurement analyst for reorder optimization, vendor selection, cost comparison.",
            ["what to order", "which vendor", "optimize purchasing", "procurement plan"],
        ),
        "analyze_trends": ToolDescriptor(
            "analyze_trends",
            "Delegate to the trend analyst for time series analysis, anomaly detection, period-over-period comparison.",
            ["trends", "compare to last month", "anomaly", "growth rate"],
        ),
        "assess_business_health": ToolDescriptor(
            "assess_business_health",
            "Delegate to the business health analyst for holistic assessment across inventory, finance, and operations.",
            ["business health", "what needs attention", "quarterly review"],
        ),
    }
