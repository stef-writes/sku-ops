"""
Chat AI assistant with tools and ReAct reasoning loops.
Uses Gemini 1.5 Flash (free tier). Tools: search products, inventory stats, low stock, departments, vendors.
"""
import asyncio
import json
import logging

from config import LLM_API_KEY, LLM_AVAILABLE, LLM_SETUP_URL
from db import get_connection

logger = logging.getLogger(__name__)

LLM_NOT_CONFIGURED_MSG = (
    "AI assistant is not configured. Add LLM_API_KEY to backend/.env. "
    f"Get a free key at {LLM_SETUP_URL}"
)

GEMINI_MODEL = "gemini-1.5-flash"
MAX_ACT_LOOPS = 8  # Prevent runaway tool loops

SYSTEM_PROMPT = """You are a helpful AI assistant for a hardware store inventory system (SKU-Ops).
You can search products, check inventory stats, list low-stock items, departments, and vendors.
Be concise. Use tools when needed to answer questions. If asked about stock, products, or data, use the appropriate tool.
Format numbers and lists clearly. When showing product lists, include SKU, name, quantity, and min_stock if relevant."""

TOOL_DECLARATIONS = [
    {
        "name": "search_products",
        "description": "Search products by name, SKU, or barcode. Returns matching products with sku, name, quantity, min_stock, department_name.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search term for product name, SKU, or barcode"},
                "limit": {"type": "integer", "description": "Max results to return", "default": 20},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_inventory_stats",
        "description": "Get high-level inventory stats: total products, total quantity/value, low stock count.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "list_low_stock",
        "description": "List products at or below their reorder point (quantity <= min_stock).",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max products to return", "default": 20},
            },
        },
    },
    {
        "name": "list_departments",
        "description": "List all departments with product counts and next SKU.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "list_vendors",
        "description": "List all vendors with product counts.",
        "parameters": {"type": "object", "properties": {}},
    },
]


async def execute_tool(name: str, args: dict) -> str:
    """Execute a tool and return JSON string result."""
    from repositories import product_repo, department_repo, vendor_repo

    try:
        if name == "search_products":
            query = (args.get("query") or "").strip()
            limit = int(args.get("limit") or 20)
            limit = min(limit, 50)
            items = await product_repo.list_products(search=query, limit=limit)
            # Simplify for LLM
            out = [{"sku": p.get("sku"), "name": p.get("name"), "quantity": p.get("quantity"), "min_stock": p.get("min_stock"), "department": p.get("department_name")} for p in items]
            return json.dumps({"count": len(out), "products": out[:limit]})

        if name == "get_inventory_stats":
            conn = get_connection()
            cur = await conn.execute("SELECT COUNT(*) FROM products")
            total_products = (await cur.fetchone())[0]
            cur = await conn.execute("SELECT COALESCE(SUM(quantity), 0), COALESCE(SUM(quantity * cost), 0) FROM products")
            row = await cur.fetchone()
            total_qty = int(row[0]) if row else 0
            total_value = round(float(row[1] or 0), 2)
            cur = await conn.execute("SELECT COUNT(*) FROM products WHERE quantity <= min_stock")
            low_count = (await cur.fetchone())[0]
            return json.dumps({
                "total_products": total_products,
                "total_quantity": total_qty,
                "total_cost_value": total_value,
                "low_stock_count": low_count,
            })

        if name == "list_low_stock":
            limit = int(args.get("limit") or 20)
            limit = min(limit, 50)
            items = await product_repo.list_low_stock(limit=limit)
            out = [{"sku": p.get("sku"), "name": p.get("name"), "quantity": p.get("quantity"), "min_stock": p.get("min_stock")} for p in items]
            return json.dumps({"count": len(out), "products": out})

        if name == "list_departments":
            depts = await department_repo.list_all()
            from repositories import sku_repo
            counters = await sku_repo.get_all_counters()
            out = []
            for d in depts:
                code = d.get("code", "")
                next_num = counters.get(code, 0) + 1
                next_sku = f"{code}-ITM-{str(next_num).zfill(6)}"
                out.append({"name": d.get("name"), "code": code, "product_count": d.get("product_count", 0), "next_sku": next_sku})
            return json.dumps({"departments": out})

        if name == "list_vendors":
            vendors = await vendor_repo.list_all()
            out = [{"name": v.get("name"), "product_count": v.get("product_count", 0)} for v in vendors]
            return json.dumps({"vendors": out})

        return json.dumps({"error": f"Unknown tool: {name}"})
    except Exception as e:
        logger.warning(f"Tool {name} error: {e}")
        return json.dumps({"error": str(e)})


def _build_tools():
    """Build Gemini Tool from declarations."""
    import google.generativeai as genai
    from google.generativeai.types import Tool, FunctionDeclaration

    decls = []
    for d in TOOL_DECLARATIONS:
        decls.append(FunctionDeclaration(
            name=d["name"],
            description=d.get("description", ""),
            parameters=d.get("parameters", {}),
        ))
    return [Tool(function_declarations=decls)]


async def chat(messages: list[dict], user_message: str) -> dict:
    """
    ReAct loop: send to Gemini with tools, execute any function_call, feed result back, repeat.
    Returns { "response": "...", "tool_calls": [...] }.
    """
    if not LLM_AVAILABLE:
        return {"response": LLM_NOT_CONFIGURED_MSG, "tool_calls": []}

    try:
        import google.generativeai as genai
        genai.configure(api_key=LLM_API_KEY)
        model = genai.GenerativeModel(GEMINI_MODEL, system_instruction=SYSTEM_PROMPT)
        tools = _build_tools()
    except Exception as e:
        logger.warning(f"Assistant init: {e}")
        return {"response": f"Could not initialize AI: {e}", "tool_calls": []}

    # Build conversation history for Gemini (prior turns only; we send user_message next)
    prior_history = []
    for m in messages:
        role = "user" if m.get("role") == "user" else "model"
        text = (m.get("content") or "").strip()
        if text:
            prior_history.append({"role": role, "parts": [text]})

    tool_calls_made = []

    chat = model.start_chat(history=prior_history, enable_automatic_function_calling=False)
    to_send = user_message

    for loop in range(MAX_ACT_LOOPS):
        try:
            response = await asyncio.to_thread(chat.send_message, to_send)
        except Exception as e:
            logger.warning(f"Assistant generate: {e}")
            return {"response": f"AI error: {e}", "tool_calls": tool_calls_made}

        if not response or not response.candidates:
            return {"response": "No response from AI.", "tool_calls": tool_calls_made}

        parts = response.candidates[0].content.parts if response.candidates[0].content else []
        function_call = None
        text_part = None

        for p in parts:
            if hasattr(p, "function_call") and p.function_call:
                function_call = p.function_call
                break
            if hasattr(p, "text") and p.text:
                text_part = p.text
                break

        if function_call:
            name = getattr(function_call, "name", None) or getattr(function_call, "get", lambda k: None)("name")
            args = getattr(function_call, "args", None) or getattr(function_call, "get", lambda k: {})("args") or {}
            if hasattr(args, "items"):
                args = dict(args)
            else:
                args = {}
            result = await execute_tool(name, args)
            tool_calls_made.append({"tool": name, "args": args})

            # Send function response as next user turn
            from google.generativeai.protos import Part, FunctionResponse
            from google.protobuf import struct_pb2
            try:
                resp_struct = struct_pb2.Struct()
                resp_struct.update({"result": result})
                fr = FunctionResponse(name=name, response=resp_struct)
                to_send = Part(function_response=fr)
            except Exception:
                to_send = {"function_response": {"name": name, "response": {"result": result}}}
            continue

        # Text response - we're done
        final = text_part or (response.text if response else "")
        if not final and hasattr(response, "text"):
            final = str(response.text) if response.text else ""
        return {"response": final or "I couldn't generate a response.", "tool_calls": tool_calls_made}

    return {"response": "Reached maximum reasoning steps. Try a simpler question.", "tool_calls": tool_calls_made}
