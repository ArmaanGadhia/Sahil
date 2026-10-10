"""
Database Adapter for Sahil Communication & Mobile Repairs
Supports Supabase (Cloud PostgreSQL) as primary backend, with automatic
fallback to local SQLite (database.db) if Supabase credentials are not yet configured.
"""

import os
import json
import sqlite3
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "").strip()

DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "database.db")

supabase_client = None
USE_SUPABASE = False

if SUPABASE_URL and SUPABASE_KEY and "your-project-id" not in SUPABASE_URL:
    try:
        from supabase import create_client, Client
        supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
        USE_SUPABASE = True
        print(f"[Database] Connected to Supabase Cloud at {SUPABASE_URL}")
    except Exception as e:
        print(f"[Database Warning] Failed to initialize Supabase client: {e}. Falling back to SQLite.")
        USE_SUPABASE = False
else:
    print("[Database] Using local SQLite database (database.db). Add SUPABASE_URL and SUPABASE_KEY in .env to switch to Supabase.")

# ---------------------------------------------------------------------
# SQLite Helpers (Fallback)
# ---------------------------------------------------------------------
def get_sqlite_conn():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

# ---------------------------------------------------------------------
# Unified Database Interface
# ---------------------------------------------------------------------
def get_database_status():
    if USE_SUPABASE:
        return "Supabase (Cloud PostgreSQL)"
    return "SQLite (Local Database)"

def is_using_supabase():
    return USE_SUPABASE

# --- Branches ---
def get_branches():
    if USE_SUPABASE:
        try:
            res = supabase_client.table("branches").select("*").execute()
            branches = res.data or []
            for b in branches:
                if isinstance(b.get("specialties"), str):
                    try:
                        b["specialties"] = json.loads(b["specialties"])
                    except Exception:
                        b["specialties"] = []
                elif not b.get("specialties"):
                    b["specialties"] = []
            return branches
        except Exception as e:
            print(f"[Supabase Error: get_branches] {e}")

    conn = get_sqlite_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM branches")
    branches = [dict(row) for row in cursor.fetchall()]
    conn.close()
    for b in branches:
        if b.get("specialties"):
            try:
                b["specialties"] = json.loads(b["specialties"])
            except Exception:
                b["specialties"] = []
        else:
            b["specialties"] = []
    return branches

# --- Products ---
def get_products_by_category(category):
    if USE_SUPABASE:
        try:
            res = supabase_client.table("products").select("*").eq("category", category).eq("in_stock", 1).order("price", desc=True).execute()
            products = res.data or []
            for p in products:
                if isinstance(p.get("specs"), str):
                    try:
                        p["specs"] = json.loads(p["specs"])
                    except Exception:
                        p["specs"] = []
                elif not p.get("specs"):
                    p["specs"] = []
            return products
        except Exception as e:
            print(f"[Supabase Error: get_products_by_category] {e}")

    conn = get_sqlite_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM products WHERE category = ? AND in_stock = 1 ORDER BY price DESC", (category,))
    products = [dict(row) for row in cursor.fetchall()]
    conn.close()
    for p in products:
        p["specs"] = json.loads(p["specs"]) if p.get("specs") else []
    return products

def get_all_products():
    if USE_SUPABASE:
        try:
            res = supabase_client.table("products").select("*").order("category").order("price", desc=True).execute()
            products = res.data or []
            for p in products:
                if isinstance(p.get("specs"), str):
                    try:
                        p["specs"] = json.loads(p["specs"])
                    except Exception:
                        p["specs"] = []
                elif not p.get("specs"):
                    p["specs"] = []
            return products
        except Exception as e:
            print(f"[Supabase Error: get_all_products] {e}")

    conn = get_sqlite_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM products ORDER BY category, price DESC")
    products = [dict(row) for row in cursor.fetchall()]
    conn.close()
    for p in products:
        p["specs"] = json.loads(p["specs"]) if p.get("specs") else []
    return products

def get_product(prod_id):
    if USE_SUPABASE:
        try:
            res = supabase_client.table("products").select("*").eq("id", prod_id).limit(1).execute()
            if res.data and len(res.data) > 0:
                p = res.data[0]
                if isinstance(p.get("specs"), str):
                    try:
                        p["specs"] = json.loads(p["specs"])
                    except Exception:
                        p["specs"] = []
                elif not p.get("specs"):
                    p["specs"] = []
                return p
        except Exception as e:
            print(f"[Supabase Error: get_product] {e}")

    conn = get_sqlite_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM products WHERE id = ?", (prod_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        p = dict(row)
        p["specs"] = json.loads(p["specs"]) if p.get("specs") else []
        return p
    return None

def add_product(data):
    if USE_SUPABASE:
        try:
            payload = dict(data)
            if isinstance(payload.get("specs"), str):
                try:
                    payload["specs"] = json.loads(payload["specs"])
                except Exception:
                    payload["specs"] = []
            res = supabase_client.table("products").insert(payload).execute()
            return res.data
        except Exception as e:
            print(f"[Supabase Error: add_product] {e}")

    conn = get_sqlite_conn()
    cursor = conn.cursor()
    specs_str = json.dumps(data["specs"]) if isinstance(data["specs"], list) else data["specs"]
    cursor.execute("""
        INSERT INTO products (id, category, subcategory, title, condition, battery_health, storage, color, price, original_price, warranty, image, specs, badge, in_stock)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
    """, (
        data["id"], data["category"], data["subcategory"], data["title"],
        data["condition"], data["battery_health"], data["storage"], data["color"],
        data["price"], data["original_price"], data["warranty"], data["image"],
        specs_str, data["badge"]
    ))
    conn.commit()
    conn.close()
    return True

def delete_product(prod_id):
    if USE_SUPABASE:
        try:
            res = supabase_client.table("products").delete().eq("id", prod_id).execute()
            return res.data
        except Exception as e:
            print(f"[Supabase Error: delete_product] {e}")

    conn = get_sqlite_conn()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM products WHERE id = ?", (prod_id,))
    conn.commit()
    conn.close()
    return True

# --- Orders ---
def create_order(data):
    if USE_SUPABASE:
        try:
            payload = dict(data)
            if isinstance(payload.get("items_json"), str):
                try:
                    payload["items_json"] = json.loads(payload["items_json"])
                except Exception:
                    pass
            res = supabase_client.table("orders").insert(payload).execute()
            return res.data
        except Exception as e:
            print(f"[Supabase Error: create_order] {e}")

    conn = get_sqlite_conn()
    cursor = conn.cursor()
    items_str = json.dumps(data["items_json"]) if isinstance(data["items_json"], list) else data["items_json"]
    cursor.execute("""
        INSERT INTO orders (order_number, customer_name, customer_phone, customer_email, delivery_type, address, branch_pickup, payment_method, total_amount, items_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data["order_number"], data["customer_name"], data["customer_phone"],
        data.get("customer_email", ""), data["delivery_type"], data.get("address", ""),
        data.get("branch_pickup", ""), data["payment_method"], data["total_amount"],
        items_str
    ))
    conn.commit()
    conn.close()
    return True

def get_orders():
    if USE_SUPABASE:
        try:
            res = supabase_client.table("orders").select("*").order("created_at", desc=True).execute()
            orders = res.data or []
            for o in orders:
                if isinstance(o.get("items_json"), str):
                    try:
                        o["items"] = json.loads(o["items_json"])
                    except Exception:
                        o["items"] = []
                elif isinstance(o.get("items_json"), list):
                    o["items"] = o["items_json"]
                else:
                    o["items"] = []
            return orders
        except Exception as e:
            print(f"[Supabase Error: get_orders] {e}")

    conn = get_sqlite_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders ORDER BY created_at DESC")
    orders = [dict(row) for row in cursor.fetchall()]
    conn.close()
    for o in orders:
        o["items"] = json.loads(o["items_json"]) if o.get("items_json") else []
    return orders

def get_order_by_number(order_number):
    if USE_SUPABASE:
        try:
            res = supabase_client.table("orders").select("*").eq("order_number", order_number).limit(1).execute()
            if res.data and len(res.data) > 0:
                o = res.data[0]
                if isinstance(o.get("items_json"), str):
                    try:
                        o["order_items"] = json.loads(o["items_json"])
                    except Exception:
                        o["order_items"] = []
                elif isinstance(o.get("items_json"), list):
                    o["order_items"] = o["items_json"]
                else:
                    o["order_items"] = []
                return o
        except Exception as e:
            print(f"[Supabase Error: get_order_by_number] {e}")

    conn = get_sqlite_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders WHERE order_number = ?", (order_number,))
    row = cursor.fetchone()
    conn.close()
    if row:
        o = dict(row)
        o["order_items"] = json.loads(o["items_json"]) if o.get("items_json") else []
        return o
    return None

def update_order_status(order_id, status):
    if USE_SUPABASE:
        try:
            res = supabase_client.table("orders").update({"status": status}).eq("id", order_id).execute()
            return res.data
        except Exception as e:
            print(f"[Supabase Error: update_order_status] {e}")

    conn = get_sqlite_conn()
    cursor = conn.cursor()
    cursor.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))
    conn.commit()
    conn.close()
    return True

# --- Inquiries ---
def create_inquiry(data):
    if USE_SUPABASE:
        try:
            res = supabase_client.table("inquiries").insert(data).execute()
            return res.data
        except Exception as e:
            print(f"[Supabase Error: create_inquiry] {e}")

    conn = get_sqlite_conn()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO inquiries (name, phone, model, service, branch, notes)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        data["name"], data["phone"], data["model"],
        data["service"], data["branch"], data.get("notes", "")
    ))
    conn.commit()
    conn.close()
    return True

def get_inquiries():
    if USE_SUPABASE:
        try:
            res = supabase_client.table("inquiries").select("*").order("created_at", desc=True).execute()
            return res.data or []
        except Exception as e:
            print(f"[Supabase Error: get_inquiries] {e}")

    conn = get_sqlite_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM inquiries ORDER BY created_at DESC")
    inquiries = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return inquiries

def update_inquiry_status(inquiry_id, status):
    if USE_SUPABASE:
        try:
            res = supabase_client.table("inquiries").update({"status": status}).eq("id", inquiry_id).execute()
            return res.data
        except Exception as e:
            print(f"[Supabase Error: update_inquiry_status] {e}")

    conn = get_sqlite_conn()
    cursor = conn.cursor()
    cursor.execute("UPDATE inquiries SET status = ? WHERE id = ?", (status, inquiry_id))
    conn.commit()
    conn.close()
    return True

def delete_inquiry(inquiry_id):
    if USE_SUPABASE:
        try:
            res = supabase_client.table("inquiries").delete().eq("id", inquiry_id).execute()
            return res.data
        except Exception as e:
            print(f"[Supabase Error: delete_inquiry] {e}")

    conn = get_sqlite_conn()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM inquiries WHERE id = ?", (inquiry_id,))
    conn.commit()
    conn.close()
    return True

# --- Stats for Admin Dashboard ---
def get_dashboard_counts():
    products = get_all_products()
    orders = get_orders()
    inquiries = get_inquiries()

    mobiles_count = sum(1 for p in products if p.get("category") == "mobiles")
    accessories_count = sum(1 for p in products if p.get("category") == "accessories")
    spare_parts_count = sum(1 for p in products if p.get("category") == "spare_parts")

    total_orders = len(orders)
    total_revenue = sum(o.get("total_amount", 0) for o in orders)

    return {
        "mobiles_count": mobiles_count,
        "accessories_count": accessories_count,
        "spare_parts_count": spare_parts_count,
        "inquiries_count": len(inquiries),
        "total_orders": total_orders,
        "total_revenue": total_revenue,
        "products": products,
        "orders": orders,
        "inquiries": inquiries,
        "branches": get_branches()
    }
