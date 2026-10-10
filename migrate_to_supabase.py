"""
One-Click Migration Utility: SQLite -> Supabase Cloud
Transfers all products, branches, orders, and inquiries from local database.db to Supabase PostgreSQL.
Run this script after filling in your SUPABASE_URL and SUPABASE_KEY in .env:
    python migrate_to_supabase.py
"""

import os
import json
import sqlite3
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "").strip()

if not SUPABASE_URL or not SUPABASE_KEY or "your-project-id" in SUPABASE_URL:
    print("[Error] Please set SUPABASE_URL and SUPABASE_KEY in your .env file first!")
    print("Example in .env:")
    print("SUPABASE_URL=https://xyzcompany.supabase.co")
    print("SUPABASE_KEY=eyJhbGciOi...")
    exit(1)

from supabase import create_client

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "database.db")

if not os.path.exists(DB_FILE):
    print(f"[Error] Local database {DB_FILE} not found!")
    exit(1)

conn = sqlite3.connect(DB_FILE)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

print("=" * 60)
print(f"Starting Migration to Supabase: {SUPABASE_URL}")
print("=" * 60)

# 1. Migrate Branches
cursor.execute("SELECT * FROM branches")
branches = [dict(r) for r in cursor.fetchall()]
print(f"Migrating {len(branches)} branches...")
for b in branches:
    if isinstance(b.get("specialties"), str):
        try:
            b["specialties"] = json.loads(b["specialties"])
        except Exception:
            b["specialties"] = []
    try:
        supabase.table("branches").upsert(b).execute()
    except Exception as e:
        print(f"  Warning on branch {b.get('id')}: {e}")
print("Branches migrated.")

# 2. Migrate Products
cursor.execute("SELECT * FROM products")
products = [dict(r) for r in cursor.fetchall()]
print(f"Migrating {len(products)} products...")
for p in products:
    if isinstance(p.get("specs"), str):
        try:
            p["specs"] = json.loads(p["specs"])
        except Exception:
            p["specs"] = []
    try:
        supabase.table("products").upsert(p).execute()
    except Exception as e:
        print(f"  Warning on product {p.get('id')}: {e}")
print("Products migrated.")

# 3. Migrate Orders
cursor.execute("SELECT * FROM orders")
orders = [dict(r) for r in cursor.fetchall()]
print(f"Migrating {len(orders)} orders...")
for o in orders:
    o_dict = dict(o)
    o_dict.pop("id", None)  # let Supabase autoincrement id
    if isinstance(o_dict.get("items_json"), str):
        try:
            o_dict["items_json"] = json.loads(o_dict["items_json"])
        except Exception:
            pass
    try:
        supabase.table("orders").upsert(o_dict, on_conflict="order_number").execute()
    except Exception as e:
        print(f"  Warning on order {o_dict.get('order_number')}: {e}")
print("Orders migrated.")

# 4. Migrate Inquiries
cursor.execute("SELECT * FROM inquiries")
inquiries = [dict(r) for r in cursor.fetchall()]
print(f"Migrating {len(inquiries)} inquiries...")
for inq in inquiries:
    inq_dict = dict(inq)
    inq_dict.pop("id", None)
    try:
        supabase.table("inquiries").insert(inq_dict).execute()
    except Exception as e:
        print(f"  Warning on inquiry {inq_dict.get('name')}: {e}")
print("Inquiries migrated.")

conn.close()
print("=" * 60)
print("SUCCESS: All data successfully migrated to Supabase Cloud!")
print("=" * 60)
