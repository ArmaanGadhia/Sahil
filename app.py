"""
Sahil Communication & Mobile Repairs - Web Application, E-Commerce Store & Admin Portal
Apple-inspired responsive frontend with Dark/Light mode, distinct sections for Mobiles, Accessories, 
and Spare Parts, full Cart & Checkout e-commerce buying flow, and Admin Console.
"""

import os
import json
import random
import re
import sqlite3
import secrets
import time
from collections import defaultdict
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, abort
from dotenv import load_dotenv
import db_adapter

load_dotenv()

def get_or_create_secret_key():
    env_key = os.environ.get("FLASK_SECRET_KEY")
    if env_key:
        return env_key
    key_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".secret_key")
    if os.path.exists(key_path):
        try:
            with open(key_path, "r", encoding="utf-8") as f:
                k = f.read().strip()
                if len(k) >= 32:
                    return k
        except Exception:
            pass
    new_key = secrets.token_hex(32)
    try:
        with open(key_path, "w", encoding="utf-8") as f:
            f.write(new_key)
    except Exception:
        pass
    return new_key

app = Flask(__name__)
app.secret_key = get_or_create_secret_key()

# Production Security Configurations
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=False,
    PERMANENT_SESSION_LIFETIME=timedelta(hours=4),
    MAX_CONTENT_LENGTH=10 * 1024 * 1024  # Max 10MB payload to prevent memory-exhaustion DoS
)

# Admin Security Hashing
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
DEFAULT_ADMIN_HASH = generate_password_hash(os.environ.get("ADMIN_PASSWORD", "sahil123"), method="pbkdf2:sha256")
ADMIN_PASSWORD_HASH = os.environ.get("ADMIN_PASSWORD_HASH", DEFAULT_ADMIN_HASH)

DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "database.db")
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "images")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
ALLOWED_EXTENSIONS = {"jpg", "jpeg"}

def is_allowed_jpg(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

# In-Memory Rate Limiting & Brute Force Lockout
_request_records = defaultdict(list)
_failed_logins = defaultdict(list)
_lockout_until = {}

def get_real_ip():
    cf_ip = request.headers.get("CF-Connecting-IP")
    if cf_ip:
        return cf_ip.strip()
    x_forwarded = request.headers.get("X-Forwarded-For")
    if x_forwarded:
        return x_forwarded.split(",")[0].strip()
    return request.remote_addr or "127.0.0.1"

def is_rate_limited(bucket_name, max_requests, window_seconds):
    ip = get_real_ip()
    key = f"{bucket_name}:{ip}"
    now = time.time()
    valid_window = now - window_seconds
    _request_records[key] = [t for t in _request_records[key] if t > valid_window]
    if len(_request_records[key]) >= max_requests:
        return True
    _request_records[key].append(now)
    return False

def is_login_locked(ip):
    now = time.time()
    if ip in _lockout_until and now < _lockout_until[ip]:
        return True, int(_lockout_until[ip] - now)
    return False, 0

def record_failed_login(ip):
    now = time.time()
    _failed_logins[ip] = [t for t in _failed_logins[ip] if now - t < 600]
    _failed_logins[ip].append(now)
    if len(_failed_logins[ip]) >= 5:
        _lockout_until[ip] = now + 900  # 15 minutes lockout
        return True
    return False

def reset_login_attempts(ip):
    _failed_logins.pop(ip, None)
    _lockout_until.pop(ip, None)


def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    # Products Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS products (
        id TEXT PRIMARY KEY,
        category TEXT NOT NULL,       -- 'mobiles', 'accessories', 'spare_parts'
        subcategory TEXT,
        title TEXT NOT NULL,
        condition TEXT,
        battery_health TEXT,
        storage TEXT,
        color TEXT,
        price INTEGER NOT NULL,
        original_price INTEGER,
        warranty TEXT,
        image TEXT,
        specs TEXT,                  -- JSON string
        badge TEXT,
        in_stock INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Orders Table (E-Commerce)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_number TEXT UNIQUE NOT NULL,
        customer_name TEXT NOT NULL,
        customer_phone TEXT NOT NULL,
        customer_email TEXT,
        delivery_type TEXT NOT NULL,  -- 'store_pickup' or 'home_delivery'
        address TEXT,
        branch_pickup TEXT,
        payment_method TEXT NOT NULL, -- 'cod_upi', 'store_pay', 'upi_online'
        total_amount INTEGER NOT NULL,
        status TEXT DEFAULT 'Confirmed', -- 'Confirmed', 'Processing', 'Ready for Pickup', 'Dispatched', 'Delivered'
        items_json TEXT NOT NULL,     -- JSON array of cart items
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Customer Repair / Hold Inquiries Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS inquiries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        phone TEXT NOT NULL,
        model TEXT NOT NULL,
        service TEXT NOT NULL,
        branch TEXT NOT NULL,
        status TEXT DEFAULT 'New',    -- 'New', 'Contacted', 'Completed'
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Branches Table (from info.md)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS branches (
        id TEXT PRIMARY KEY,
        branch_num TEXT NOT NULL,
        name TEXT NOT NULL,
        address TEXT NOT NULL,
        landmark TEXT,
        phone TEXT NOT NULL,
        tagline TEXT,
        hours TEXT NOT NULL,
        map_query TEXT,
        specialties TEXT
    )
    """)

    # Check & Seed Branches if empty
    cursor.execute("SELECT COUNT(*) FROM branches")
    if cursor.fetchone()[0] == 0:
        initial_branches = [
            (
                "branch-1",
                "1st Branch",
                "Shivaji Nagar Branch",
                "1st Main, 2nd Cross Rd, Shivaji Nagar, Belagavi, Karnataka 590016",
                "Near Shivaji Garden",
                "7019412520",
                "Pre-Owned iPhone Showroom & Rapid Screen Center",
                "10:00 AM – 8:30 PM",
                "1st+Main+2nd+Cross+Rd+Shivaji+Nagar+Belagavi+Karnataka+590016",
                json.dumps(["Pre-Owned iPhone Inventory", "Screen Replacement", "Battery Health Diagnostics"])
            ),
            (
                "branch-2",
                "2nd Branch (Main Landmark)",
                "Raviwar Peth / Khade Bazar Branch",
                "Kaktives Rd, opp. Devaki Vasati Gruha (Lodging), beside Dargah, Khade Bazar, Raviwar Peth, Belagavi, Karnataka 590001",
                "Opposite Zuber Biryaniwala & Beside Dargah",
                "7019412520",
                "Second Hand Mobiles & Master Micro-Soldering Lab",
                "10:00 AM – 8:30 PM",
                "Kaktives+Rd+Khade+Bazar+Raviwar+Peth+Belagavi+Karnataka+590001",
                json.dumps(["Certified Flagship Devices", "Water-Damage Lab", "Original Accessories Hub", "Motherboard IC Repair"])
            ),
            (
                "branch-3",
                "3rd Branch",
                "Shivbasava Nagar / Nehru Nagar Branch",
                "Shop No 3, Siddiqiya Masjid, Shivbasava Nagar Main Rd, Sector 2, Shivabasava Nagar, Nehru Nagar, Belagavi, Karnataka 590010",
                "Shop No 3, Siddiqiya Masjid",
                "9964403115",
                "Express Tablet, iPad & Mobile Care Hub",
                "10:00 AM – 8:30 PM",
                "Siddiqiya+Masjid+Shivbasava+Nagar+Nehru+Nagar+Belagavi+Karnataka+590010",
                json.dumps(["Budget & Premium Second Hand Phones", "Tablet/iPad Repair", "Instant Charging Port Fix"])
            )
        ]
        cursor.executemany("""
            INSERT INTO branches (id, branch_num, name, address, landmark, phone, tagline, hours, map_query, specialties)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, initial_branches)

    # Check & Seed Products if empty
    cursor.execute("SELECT COUNT(*) FROM products")
    if cursor.fetchone()[0] == 0:
        initial_products = [
            # --- 1. SECOND HAND MOBILES ---
            (
                "sh-iphone-16-pro",
                "mobiles",
                "iphone",
                "iPhone 16 Pro Max",
                "Sahil Certified Pristine A+",
                "99% Battery Health",
                "256 GB",
                "Desert Titanium",
                89999,
                144900,
                "6 Months Sahil In-Store Warranty",
                "twin-iphones.jpg",
                json.dumps(["Grade A+ Flawless", "A18 Pro Chip", "Apple Intelligence Ready", "Sahil 32-Point Inspected"]),
                "Latest Flagship",
                1
            ),
            (
                "sh-iphone-15-pro",
                "mobiles",
                "iphone",
                "iPhone 15 Pro",
                "Grade A+ Mint",
                "97% Battery Health",
                "128 GB",
                "Natural Titanium",
                69999,
                129900,
                "6 Months Sahil In-Store Warranty",
                "iphone-titanium.jpg",
                json.dumps(["Action Button", "Titanium Frame", "48MP Main Camera", "Type-C Fast Charging"]),
                "Top Seller",
                1
            ),
            (
                "sh-samsung-s23-ultra",
                "mobiles",
                "android",
                "Samsung Galaxy S23 Ultra 5G",
                "Certified Like New",
                "100% Functional",
                "256 GB (12GB RAM)",
                "Phantom Black",
                52499,
                104999,
                "6 Months Sahil In-Store Warranty",
                "hero-devices.jpg",
                json.dumps(["200MP Quad Camera", "Snapdragon 8 Gen 2", "Built-in S-Pen", "Dynamic AMOLED 120Hz"]),
                "Flagship Android",
                1
            ),
            (
                "sh-iphone-14-pro",
                "mobiles",
                "iphone",
                "iPhone 14 Pro",
                "Grade A Mint",
                "94% Battery Health",
                "128 GB",
                "Deep Purple",
                56999,
                119900,
                "6 Months Sahil In-Store Warranty",
                "iphone-titanium.jpg",
                json.dumps(["Dynamic Island", "A16 Bionic", "120Hz ProMotion", "Original Box Included"]),
                "Customer Choice",
                1
            ),
            (
                "sh-oneplus-11",
                "mobiles",
                "android",
                "OnePlus 11 5G",
                "Super Mint Grade",
                "96% Battery Health",
                "256 GB (16GB RAM)",
                "Titan Black",
                31999,
                61999,
                "6 Months Sahil In-Store Warranty",
                "hero-devices.jpg",
                json.dumps(["100W SuperVOOC Charger Included", "Hasselblad Optics", "120Hz AMOLED", "Dual SIM 5G"]),
                "Speed Beast",
                1
            ),
            (
                "sh-iphone-13",
                "mobiles",
                "iphone",
                "iPhone 13",
                "Grade A Pre-Owned",
                "92% Battery Health",
                "128 GB",
                "Midnight",
                34999,
                69900,
                "6 Months Sahil In-Store Warranty",
                "hero-devices.jpg",
                json.dumps(["A15 Bionic", "Cinematic 4K Mode", "Ceramic Shield", "Verified Clean IMEI"]),
                "Best Value",
                1
            ),

            # --- 2. ACCESSORIES ---
            (
                "acc-airpods-pro-2",
                "accessories",
                "audio",
                "Apple AirPods Pro (2nd Gen)",
                "Pre-Owned Grade A+",
                "30-Hr Battery Case",
                "USB-C MagSafe Case",
                "Gloss White",
                9999,
                24900,
                "3 Months Sahil Warranty",
                "accessories.jpg",
                json.dumps(["Active Noise Cancellation", "Adaptive Audio", "Sterilized & Cleaned", "Original Apple Serial"]),
                "Staff Pick",
                1
            ),
            (
                "acc-apple-20w-adapter",
                "accessories",
                "power",
                "Apple 20W USB-C Power Adapter",
                "Brand New Sealed Genuine",
                "N/A",
                "20W Fast Charging",
                "White",
                1499,
                1900,
                "1 Year Replacement Warranty",
                "accessories.jpg",
                json.dumps(["BIS Certified", "USB Power Delivery", "Original Apple Part", "Fast Charges 0-50% in 30m"]),
                "Genuine Original",
                1
            ),
            (
                "acc-magsafe-charger",
                "accessories",
                "power",
                "Apple MagSafe Wireless Charger Pad",
                "Certified Pre-Owned",
                "N/A",
                "15W Magnetic Fast Snap",
                "Silver Aluminum",
                2499,
                4500,
                "6 Months Sahil Warranty",
                "accessories.jpg",
                json.dumps(["Strong Neodymium Magnets", "Qi Standard Compatible", "Braided 1m Cable", "Optimal Alignment"]),
                "Essential",
                1
            ),
            (
                "acc-shockproof-armor-case",
                "accessories",
                "protection",
                "Military Shockproof MagSafe Armor Case",
                "Brand New Premium",
                "N/A",
                "iPhone 13 to 16 Series",
                "Matte Stealth Black",
                799,
                1999,
                "Sahil Fitment Guarantee",
                "accessories.jpg",
                json.dumps(["10ft Drop Certified", "Raised Camera Lip", "MagSafe Ring Embedded", "Anti-Yellowing Coating"]),
                "High Protection",
                1
            ),
            (
                "acc-braided-fast-cable",
                "accessories",
                "power",
                "Ultra-Durable Braided USB-C Cable",
                "Brand New Reinforced",
                "N/A",
                "1.5 Metre (100W PD)",
                "Space Grey Woven",
                499,
                1299,
                "6 Months Replacement Warranty",
                "accessories.jpg",
                json.dumps(["Aramid Fiber Core", "100W Fast Charge Support", "30,000+ Bend Tested", "Aluminum Shell"]),
                "Best Seller",
                1
            ),
            (
                "acc-sapphire-tempered-glass",
                "accessories",
                "protection",
                "9H Sapphire Edge-to-Edge Tempered Glass",
                "Brand New with Free Installation",
                "N/A",
                "All iPhone & Samsung Models",
                "Ultra-Clear 99.9% Transmittance",
                299,
                799,
                "Free Bubble-Free In-Store Fit",
                "accessories.jpg",
                json.dumps(["Electroplated Oleophobic Layer", "Dust Proof Speaker Filter", "Curved 2.5D Polished Edges", "Free Fitment at any Branch"]),
                "Free Fitting",
                1
            ),

            # --- 3. SPARE PARTS ---
            (
                "sp-oled-display",
                "spare_parts",
                "display",
                "Super Retina XDR & AMOLED Display Assembly",
                "Original OEM Grade",
                "N/A",
                "True-Tone & 120Hz Compatible",
                "Deep OLED Black",
                3499,
                8999,
                "6 Months Display Warranty",
                "spare-parts.jpg",
                json.dumps(["High Nit Peak Brightness", "True-Tone IC Programmable", "Zero Dead Pixel Guarantee", "Touch IC Pre-Calibrated"]),
                "OEM Grade",
                1
            ),
            (
                "sp-motherboard",
                "spare_parts",
                "motherboard",
                "Original Logic Board & Motherboard (Unlocked)",
                "Tested & Working 100%",
                "N/A",
                "128GB / 256GB / 512GB",
                "Multi-Layer PCB",
                6999,
                18500,
                "3 Months Motherboard Warranty",
                "spare-parts.jpg",
                json.dumps(["Clean IMEI & iCloud Unlocked", "Face ID / Biometric Paired", "Thermal Pad Included", "32-Point Diagnostic Tested"]),
                "Lab Certified",
                1
            ),
            (
                "sp-camera-module",
                "spare_parts",
                "camera",
                "High-Definition Primary & Telephoto Camera Module",
                "Original Pull / Grade A+",
                "N/A",
                "48MP / 200MP OIS Supported",
                "Sapphire Lens Ring",
                2499,
                6499,
                "6 Months Warranty",
                "spare-parts.jpg",
                json.dumps(["Optical Image Stabilization", "4K 60FPS Video Ready", "Anti-Glare Coated Glass", "Zero Fogging Sealed Unit"]),
                "Crisp Optics",
                1
            ),
            (
                "sp-loudspeaker",
                "spare_parts",
                "speaker",
                "Acoustic Loudspeaker & Earpiece Assembly",
                "Original Sound Calibrated",
                "N/A",
                "Stereo Dolby Atmos Passthrough",
                "Acoustic Mesh Sealed",
                799,
                1899,
                "6 Months Warranty",
                "spare-parts.jpg",
                json.dumps(["Distortion-Free High Volume", "Waterproof Dust Mesh", "Deep Bass Resonance", "Quick 20-Min Fitting"]),
                "Crystal Clear",
                1
            ),
            (
                "sp-mic-flex",
                "spare_parts",
                "mic",
                "Digital Noise-Canceling Microphone & Ribbon Flex",
                "OEM Micro-Acoustic",
                "N/A",
                "Dual / Triple Mic Array",
                "Gold-Plated Contacts",
                599,
                1499,
                "6 Months Warranty",
                "spare-parts.jpg",
                json.dumps(["Studio Voice Pickup", "Active Background Noise Suppression", "Original Flexible PCB", "Instant Voice Fix"]),
                "Original Part",
                1
            ),
            (
                "sp-battery-pack",
                "spare_parts",
                "battery",
                "High-Capacity Zero-Cycle OEM Battery Pack",
                "100% Health Brand New",
                "Zero-Cycle 100%",
                "Original mAh Capacity",
                "Lithium-Cobalt",
                1499,
                3499,
                "1 Year Battery Warranty",
                "spare-parts.jpg",
                json.dumps(["Original Texas Instruments TI Gas Gauge", "Overcharge & Thermal Protection", "Zero-Cycle Count", "Free In-Store Replacement"]),
                "100% Health",
                1
            ),
            (
                "sp-charging-port",
                "spare_parts",
                "port",
                "USB-C / Lightning Fast Charging Port Flex Dock",
                "OEM Grade Reinforced",
                "N/A",
                "PD 20W - 100W Fast Charge",
                "Brushed Steel Port",
                899,
                2199,
                "6 Months Warranty",
                "spare-parts.jpg",
                json.dumps(["Tight Snug Cable Lock", "High-Speed Data Sync Flex", "Integrated Mic & Antenna", "Water Resistance Gasket"]),
                "Fast Charge",
                1
            ),
            (
                "sp-power-volume-buttons",
                "spare_parts",
                "buttons",
                "Tactile Power, Volume & Action Button Flex Set",
                "Original Click Mechanism",
                "N/A",
                "Sealed Waterproof O-Rings",
                "Titanium / Anodized",
                499,
                1199,
                "6 Months Warranty",
                "spare-parts.jpg",
                json.dumps(["Crisp Tactile Click Feedback", "Zero Latency Response", "Sealed Rubber Gasket", "Complete Internal Bracket"]),
                "Tactile Feel",
                1
            )
        ]
        cursor.executemany("""
            INSERT INTO products (id, category, subcategory, title, condition, battery_health, storage, color, price, original_price, warranty, image, specs, badge, in_stock)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, initial_products)

    conn.commit()
    conn.close()

init_db()

# Services from info.md
SERVICES = [
    {"name": "Screen Replacement", "turnaround": "30-45 mins", "desc": "Original grade OLED & Super Retina displays with true-tone programming."},
    {"name": "Battery Replacement", "turnaround": "20 mins", "desc": "100% capacity zero-cycle batteries with warranty."},
    {"name": "Water-Damage Restoration", "turnaround": "Same day", "desc": "Deep ultrasonic PCB wash and circuit isolation diagnostic scan."},
    {"name": "Motherboard & IC Repair", "turnaround": "1-3 hours", "desc": "BGA micro-soldering, baseband fixes, audio IC & power IC recovery."},
    {"name": "Camera & Lens Repair", "turnaround": "45 mins", "desc": "Optical image stabilization (OIS) fix and genuine sensor modules."},
    {"name": "Charging Port & Buttons", "turnaround": "30 mins", "desc": "USB-C, Lightning, Power, and volume tactile switch replacements."},
    {"name": "Microphone & Speaker", "turnaround": "25 mins", "desc": "Acoustic mesh declogging, ear speaker, and loud speaker rebuilds."},
    {"name": "Data Backup & Recovery", "turnaround": "1-2 hours", "desc": "Secure extraction from boot-looped or physically damaged units."},
    {"name": "Tablet & iPad Repair", "turnaround": "Same day", "desc": "Digitizer glass bonding, charging IC, and structural frame repair."}
]

REVIEWS = [
    {
        "name": "Sameer Kulkarni",
        "rating": 5,
        "text": "Bought a second-hand iPhone 14 Pro from their Raviwar Peth branch. The phone is in pristine condition with 96% battery health and genuine parts. Unbeatable price compared to other Belgaum shops!",
        "device": "iPhone 14 Pro Pre-Owned",
        "date": "2 weeks ago"
    },
    {
        "name": "Prashant Patil",
        "rating": 5,
        "text": "Replaced the shattered display of my Samsung S23 Ultra in under 40 minutes at Shivaji Nagar branch. 100% genuine AMOLED screen with fingerprint working flawlessly. 4.9 stars truly justified.",
        "device": "Display Replacement Service",
        "date": "1 month ago"
    },
    {
        "name": "Zaid Ahmed",
        "rating": 5,
        "text": "The best mobile repair and second hand gadget shop in Belagavi. Their diagnostic scan identified the issue right away. Honest pricing and very courteous technicians.",
        "device": "Water-Damage Repair & Battery",
        "date": "3 weeks ago"
    }
]

STORE_INFO = {
    "name": "Sahil Communication & Mobile Repairs",
    "short_name": "Sahil Communication",
    "rating": "4.9",
    "reviews_count": "120+",
    "timing": "10:00 AM – 8:30 PM (Mon – Sun)",
    "branches_count": 3,
    "primary_phone": "7019412520",
    "secondary_phone": "9964403115"
}

# Cart Helper Functions
def get_cart():
    if "cart" not in session:
        session["cart"] = {}
    return session["cart"]

def get_cart_count():
    cart = get_cart()
    return sum(item["quantity"] for item in cart.values())

def get_cart_total():
    cart = get_cart()
    return sum(item["price"] * item["quantity"] for item in cart.values())

def get_csrf_token():
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_hex(32)
    return session["_csrf_token"]

@app.before_request
def csrf_and_dos_protection():
    # 1. Global DoS Protection: max 120 requests per 10s per IP
    if is_rate_limited("global", 120, 10):
        return render_template("error.html",
            error_code="429",
            error_title="Rate Limit Exceeded",
            error_message="Too many requests in a short period. Please slow down and try again.",
            current_theme=session.get("theme", "light")), 429

    # 2. CSRF Validation on all state-mutating HTTP methods
    if request.method in ["POST", "PUT", "DELETE", "PATCH"]:
        token = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
        session_token = session.get("_csrf_token")
        if not session_token or not token or not secrets.compare_digest(token, session_token):
            return render_template("error.html",
                error_code="403",
                error_title="Security Verification Failed",
                error_message="CSRF validation failed or token expired. Please refresh the page and try again.",
                current_theme=session.get("theme", "light")), 403

@app.after_request
def add_security_headers(response):
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com data:; "
        "img-src 'self' data: https:; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "form-action 'self'; "
        "base-uri 'self';"
    )
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
    response.headers["X-Permitted-Cross-Domain-Policies"] = "none"
    response.headers["Server"] = "SecureServer"
    return response

@app.context_processor
def inject_global_data():
    return {
        "cart_count": get_cart_count(),
        "cart_total": get_cart_total(),
        "current_theme": session.get("theme", "light"),
        "csrf_token": get_csrf_token,
        "database_status": db_adapter.get_database_status(),
        "is_supabase": db_adapter.is_using_supabase()
    }

# Custom error handlers to prevent stack trace leaks
@app.errorhandler(400)
def handle_bad_request(e):
    return render_template("error.html", 
        error_code="400", 
        error_title="Bad Request", 
        error_message="Invalid request syntax or parameters.",
        current_theme=session.get("theme", "light")), 400

@app.errorhandler(403)
def handle_forbidden(e):
    return render_template("error.html", 
        error_code="403", 
        error_title="Access Forbidden", 
        error_message="You do not have permission to access this resource.",
        current_theme=session.get("theme", "light")), 403

@app.errorhandler(404)
def handle_not_found(e):
    return render_template("error.html", 
        error_code="404", 
        error_title="Page Not Found", 
        error_message="The requested page could not be located.",
        current_theme=session.get("theme", "light")), 404

@app.errorhandler(413)
def handle_payload_too_large(e):
    return render_template("error.html", 
        error_code="413", 
        error_title="Payload Too Large", 
        error_message="The uploaded data exceeds the allowed size limit (10MB).",
        current_theme=session.get("theme", "light")), 413

@app.errorhandler(429)
def handle_too_many_requests(e):
    return render_template("error.html", 
        error_code="429", 
        error_title="Too Many Requests", 
        error_message="Rate limit exceeded. Please wait a moment before trying again.",
        current_theme=session.get("theme", "light")), 429

@app.errorhandler(500)
def handle_server_error(e):
    return render_template("error.html", 
        error_code="500", 
        error_title="Internal Server Error", 
        error_message="An internal server error occurred.",
        current_theme=session.get("theme", "light")), 500

# =========================================================================
# PUBLIC STORE ROUTES
# =========================================================================

@app.route("/")
def home():
    # When user opens the website using link, default theme is always light
    if not session.get("has_user_toggled"):
        session["theme"] = "light"
    theme = session.get("theme", "light")

    mobiles = db_adapter.get_products_by_category("mobiles")
    accessories = db_adapter.get_products_by_category("accessories")
    spare_parts = db_adapter.get_products_by_category("spare_parts")
    branches = db_adapter.get_branches()

    return render_template(
        "index.html",
        store=STORE_INFO,
        branches=branches,
        services=SERVICES,
        mobiles=mobiles,
        accessories=accessories,
        spare_parts=spare_parts,
        reviews=REVIEWS,
        theme=theme
    )

@app.route("/toggle-theme")
def toggle_theme():
    current_theme = session.get("theme", "light")
    new_theme = "dark" if current_theme == "light" else "light"
    session["theme"] = new_theme
    session["has_user_toggled"] = True
    redirect_target = request.referrer or url_for("home")
    return redirect(redirect_target)

# =========================================================================
# E-COMMERCE CART & CHECKOUT ROUTES
# =========================================================================

@app.route("/cart/add/<prod_id>", methods=["POST", "GET"])
def add_to_cart(prod_id):
    product = db_adapter.get_product(prod_id)

    if product:
        cart = get_cart()
        if prod_id in cart:
            cart[prod_id]["quantity"] += 1
        else:
            cart[prod_id] = {
                "id": product["id"],
                "title": product["title"],
                "price": product["price"],
                "original_price": product["original_price"],
                "image": product["image"],
                "category": product["category"],
                "condition": product["condition"],
                "quantity": 1
            }
        session["cart"] = cart
        flash(f"Added '{product['title']}' to your shopping bag!", "success")

    action = request.form.get("action") or request.args.get("action")
    if action == "buy_now":
        return redirect(url_for("view_cart"))

    return redirect(request.referrer or url_for("home"))

@app.route("/cart")
def view_cart():
    cart = get_cart()
    cart_items = list(cart.values())
    total = sum(item["price"] * item["quantity"] for item in cart_items)
    branches = db_adapter.get_branches()

    return render_template(
        "cart.html",
        store=STORE_INFO,
        cart_items=cart_items,
        total=total,
        branches=branches,
        theme=session.get("theme", "light")
    )

@app.route("/cart/update/<prod_id>", methods=["POST"])
def update_cart(prod_id):
    action = request.form.get("action", "")
    cart = get_cart()

    if prod_id in cart:
        if action == "increase":
            cart[prod_id]["quantity"] += 1
        elif action == "decrease":
            cart[prod_id]["quantity"] -= 1
            if cart[prod_id]["quantity"] <= 0:
                del cart[prod_id]
        elif action == "remove":
            del cart[prod_id]

    session["cart"] = cart
    return redirect(url_for("view_cart"))

@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    cart = get_cart()
    if not cart:
        flash("Your shopping bag is empty. Please add items to checkout.", "info")
        return redirect(url_for("home"))

    branches = db_adapter.get_branches()
    cart_items = list(cart.values())
    total_amount = sum(item["price"] * item["quantity"] for item in cart_items)

    if request.method == "POST":
        if is_rate_limited("checkout", 5, 180):
            flash("Too many checkout attempts. Please wait a few moments and try again.", "error")
            return redirect(url_for("checkout"))

        customer_name = request.form.get("name", "").strip()[:100]
        raw_phone = request.form.get("phone", "").strip()
        customer_phone = re.sub(r"[^\d+]", "", raw_phone)[:15]
        customer_email = request.form.get("email", "").strip()[:120]
        delivery_type = "home_delivery" if request.form.get("delivery_type") == "home_delivery" else "store_pickup"
        address = request.form.get("address", "").strip()[:300]
        branch_pickup = request.form.get("branch_pickup", "Raviwar Peth").strip()[:100]
        payment_method = request.form.get("payment_method", "cod_upi").strip()[:50]

        if not customer_name or not customer_phone:
            flash("Please provide your name and contact phone number.", "error")
            return redirect(url_for("checkout"))

        order_number = f"SAHIL-{secrets.randbelow(900000) + 100000}"

        order_data = {
            "order_number": order_number,
            "customer_name": customer_name,
            "customer_phone": customer_phone,
            "customer_email": customer_email,
            "delivery_type": delivery_type,
            "address": address,
            "branch_pickup": branch_pickup,
            "payment_method": payment_method,
            "total_amount": total_amount,
            "items_json": cart_items
        }
        db_adapter.create_order(order_data)

        session["cart"] = {}
        return redirect(url_for("order_success", order_number=order_number))

    return render_template(
        "checkout.html",
        store=STORE_INFO,
        cart_items=cart_items,
        total=total_amount,
        branches=branches,
        theme=session.get("theme", "light")
    )

@app.route("/order-success/<order_number>")
def order_success(order_number):
    order = db_adapter.get_order_by_number(order_number)
    if not order:
        flash("Order not found.", "error")
        return redirect(url_for("home"))

    return render_template("order_success.html", store=STORE_INFO, order=order, theme=session.get("theme", "light"))

# =========================================================================
# REPAIR INQUIRY ROUTE
# =========================================================================

@app.route("/repair-inquiry", methods=["POST"])
def repair_inquiry():
    if is_rate_limited("inquiry", 5, 180):
        flash("Too many requests. Please wait a few moments before submitting another repair inquiry.", "error")
        return redirect(url_for("home", _anchor="repair-estimator"))

    name = request.form.get("name", "").strip()[:100]
    raw_phone = request.form.get("phone", "").strip()
    phone = re.sub(r"[^\d+]", "", raw_phone)[:15]
    model = request.form.get("model", "").strip()[:100]
    service = request.form.get("service", "").strip()[:100]
    branch = request.form.get("branch", "").strip()[:100]
    notes = request.form.get("notes", "").strip()[:500]

    if name and phone:
        db_adapter.create_inquiry({
            "name": name,
            "phone": phone,
            "model": model,
            "service": service,
            "branch": branch,
            "notes": notes
        })
        flash(
            f"Thank you, {name}! Your inquiry for '{model}' ({service}) has been received at our {branch} branch. Our technician will call you on {phone} shortly.",
            "success"
        )
    else:
        flash("Please provide your name and phone number.", "error")

    return redirect(url_for("home", _anchor="repair-estimator"))

# =========================================================================
# ADMIN PORTAL
# =========================================================================

def is_admin():
    return session.get("admin_logged_in", False)

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    ip = get_real_ip()
    locked, remaining = is_login_locked(ip)

    if request.method == "POST":
        if locked:
            mins = max(1, remaining // 60 + 1)
            flash(f"Too many failed login attempts! IP blocked for security. Please try again in {mins} minute(s).", "error")
            return render_template("admin_login.html", store=STORE_INFO, theme=session.get("theme", "light")), 429

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        if secrets.compare_digest(username, ADMIN_USERNAME) and check_password_hash(ADMIN_PASSWORD_HASH, password):
            reset_login_attempts(ip)
            session.permanent = True
            session["admin_logged_in"] = True
            flash("Welcome back, Sahil Admin Console!", "success")
            return redirect(url_for("admin_dashboard"))
        else:
            is_now_locked = record_failed_login(ip)
            if is_now_locked:
                flash("Maximum failed attempts exceeded! IP has been temporarily locked for 15 minutes.", "error")
            else:
                flash("Invalid username or password. Access denied.", "error")

    if locked:
        mins = max(1, remaining // 60 + 1)
        flash(f"Notice: Too many failed attempts. Login submissions paused for {mins} minute(s).", "info")

    return render_template("admin_login.html", store=STORE_INFO, theme=session.get("theme", "light"))

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    flash("Logged out of Admin Portal.", "info")
    return redirect(url_for("admin_login"))

@app.route("/admin")
def admin_dashboard():
    if not is_admin():
        return redirect(url_for("admin_login"))

    counts = db_adapter.get_dashboard_counts()

    return render_template(
        "admin_dashboard.html",
        store=STORE_INFO,
        database_status=db_adapter.get_database_status(),
        is_supabase=db_adapter.is_using_supabase(),
        mobiles_count=counts["mobiles_count"],
        accessories_count=counts["accessories_count"],
        spare_parts_count=counts["spare_parts_count"],
        inquiries_count=counts["inquiries_count"],
        total_orders=counts["total_orders"],
        total_revenue=counts["total_revenue"],
        products=counts["products"],
        orders=counts["orders"],
        inquiries=counts["inquiries"],
        branches=counts["branches"],
        theme=session.get("theme", "light")
    )

@app.route("/admin/product/add", methods=["POST"])
def admin_add_product():
    if not is_admin():
        return redirect(url_for("admin_login"))

    title = request.form.get("title", "").strip()[:150]
    category = request.form.get("category", "mobiles").strip()[:50]
    subcategory = request.form.get("subcategory", "").strip()[:50]
    condition = request.form.get("condition", "Certified A+").strip()[:50]
    battery_health = request.form.get("battery_health", "N/A").strip()[:20]
    storage = request.form.get("storage", "").strip()[:30]
    color = request.form.get("color", "").strip()[:50]
    
    try:
        price = max(0, min(10000000, int(request.form.get("price", 0))))
        original_price = max(0, min(10000000, int(request.form.get("original_price", price))))
    except (ValueError, TypeError):
        price = 0
        original_price = 0

    warranty = request.form.get("warranty", "6 Months Warranty").strip()[:100]
    badge = request.form.get("badge", "New Arrival").strip()[:50]
    specs_raw = request.form.get("specs", "")[:500]
    specs = [s.strip()[:60] for s in specs_raw.split(",") if s.strip()]

    image_filename = "twin-iphones.jpg"
    if "image_file" in request.files:
        file = request.files["image_file"]
        if file and file.filename != "":
            if not is_allowed_jpg(file.filename):
                flash("Upload Rejected: Only genuine JPG images (.jpg, .jpeg) are accepted!", "error")
                return redirect(url_for("admin_dashboard", _anchor="section-add-product"))

            header = file.read(3)
            file.seek(0)
            if header != b"\xff\xd8\xff":
                flash("Security Alert: File signature mismatch! Uploaded file is not a valid JPEG.", "error")
                return redirect(url_for("admin_dashboard", _anchor="section-add-product"))

            ext = file.filename.rsplit(".", 1)[1].lower()
            orig_name = file.filename.rsplit(".", 1)[0]
            clean_name = secure_filename(orig_name).lower() or "product"
            random_tag = secrets.token_hex(6)
            image_filename = f"{clean_name}_{random_tag}.{ext}"
            file.save(os.path.join(UPLOAD_FOLDER, image_filename))
        elif request.form.get("image"):
            image_filename = secure_filename(request.form.get("image").strip())
    elif request.form.get("image"):
        image_filename = secure_filename(request.form.get("image").strip())

    slug = re.sub(r"[^a-zA-Z0-9-]", "", title.lower().replace(" ", "-"))[:30]
    prod_id = f"{category[:3]}-{slug}-{secrets.token_hex(4)}"

    product_data = {
        "id": prod_id,
        "category": category,
        "subcategory": subcategory,
        "title": title,
        "condition": condition,
        "battery_health": battery_health,
        "storage": storage,
        "color": color,
        "price": price,
        "original_price": original_price,
        "warranty": warranty,
        "image": image_filename,
        "specs": specs,
        "badge": badge,
        "in_stock": 1
    }
    db_adapter.add_product(product_data)

    flash(f"Added product '{title}' to catalog successfully!", "success")
    return redirect(url_for("admin_dashboard", _anchor="tab-products"))

@app.route("/admin/product/delete/<prod_id>", methods=["POST"])
def admin_delete_product(prod_id):
    if not is_admin():
        return redirect(url_for("admin_login"))

    db_adapter.delete_product(prod_id)
    flash("Product deleted successfully!", "info")
    return redirect(url_for("admin_dashboard", _anchor="tab-products"))

@app.route("/admin/order/status/<int:order_id>", methods=["POST"])
def admin_update_order_status(order_id):
    if not is_admin():
        return redirect(url_for("admin_login"))

    new_status = request.form.get("status", "Processing")[:50]
    db_adapter.update_order_status(order_id, new_status)

    flash(f"Order #{order_id} status updated to '{new_status}'!", "success")
    return redirect(url_for("admin_dashboard", _anchor="tab-orders"))

@app.route("/admin/inquiry/status/<int:inquiry_id>", methods=["POST"])
def admin_update_inquiry_status(inquiry_id):
    if not is_admin():
        return redirect(url_for("admin_login"))

    new_status = request.form.get("status", "Contacted")[:50]
    db_adapter.update_inquiry_status(inquiry_id, new_status)

    flash(f"Inquiry #{inquiry_id} status updated to '{new_status}'!", "success")
    return redirect(url_for("admin_dashboard", _anchor="tab-inquiries"))

@app.route("/admin/inquiry/delete/<int:inquiry_id>", methods=["POST"])
def admin_delete_inquiry(inquiry_id):
    if not is_admin():
        return redirect(url_for("admin_login"))

    db_adapter.delete_inquiry(inquiry_id)
    flash(f"Inquiry #{inquiry_id} deleted successfully.", "info")
    return redirect(url_for("admin_dashboard", _anchor="tab-inquiries"))

if __name__ == "__main__":
    print(f"Starting {STORE_INFO['name']} Production-Hardened Server...")
    print("Store Front: http://127.0.0.1:5000")
    print("Admin Portal: http://127.0.0.1:5000/admin")
    # Debug mode explicitly disabled to prevent remote code execution (RCE)
    app.run(host="127.0.0.1", port=5000, debug=False)
