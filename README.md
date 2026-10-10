# Sahil Communication & Mobile Repairs

A modern, Apple-inspired e-commerce web platform and store management portal for **Sahil Communication & Mobile Repairs** (Belagavi, Karnataka).

## Features
- **Modern Responsive Design**: Apple-inspired clean UI with dynamic light and dark theme persistence.
- **E-Commerce Catalog**: Pre-owned certified smartphones, original accessories, and genuine spare parts.
- **Shopping Bag & Checkout**: Online ordering flow supporting in-store pickup across 3 Belagavi branches and home delivery.
- **Repair Estimator & Inquiries**: Customer device repair lead booking system.
- **Admin Management Console**: Catalog management, order tracking, repair leads dashboard, and real-time revenue analytics.
- **Enterprise-Grade Security**: CSRF protection, PBKDF2 password hashing, brute-force IP rate limiting, strict Content Security Policy (CSP), clickjacking defense, and payload verification.
- **Supabase Cloud Backend**: Connected to Supabase Cloud PostgreSQL with automatic local SQLite fallback.

## Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment (Optional for Supabase)
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Add your Supabase URL and Key:
```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-supabase-key
```
*(If left blank, the app will automatically use the local SQLite database without breaking!)*

### 3. Run the Server
```bash
python app.py
```
Visit:
- **Storefront**: [http://127.0.0.1:5000](http://127.0.0.1:5000)
- **Admin Portal**: [http://127.0.0.1:5000/admin](http://127.0.0.1:5000/admin)
