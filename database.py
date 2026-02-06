import sqlite3
import pandas as pd
import random
from datetime import datetime, timedelta
import hashlib
import json
import os

DB_NAME = "inventory_system.db"

def get_connection():
    """Returns a connection to the SQLite database."""
    # Added timeout to wait for locks to clear if necessary
    return sqlite3.connect(DB_NAME, check_same_thread=False, timeout=30)

def init_db():
    """Initializes the database, tables, and seeds default data."""
    conn = get_connection()
    c = conn.cursor()
    
    # --- TABLE DEFINITIONS ---
    c.execute('''CREATE TABLE IF NOT EXISTS products
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  name TEXT NOT NULL, 
                  category TEXT, 
                  price REAL, 
                  stock INTEGER, 
                  cost_price REAL, 
                  sales_count INTEGER DEFAULT 0,
                  last_restock_date TEXT,
                  expiry_date TEXT,
                  is_dead_stock TEXT DEFAULT 'False',
                  image_data BLOB)''')
    
    # Updated Sales table for Coupons/Points
    c.execute('''CREATE TABLE IF NOT EXISTS sales
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  timestamp TEXT, 
                  total_amount REAL, 
                  items_json TEXT, 
                  integrity_hash TEXT,
                  operator TEXT, 
                  payment_mode TEXT, 
                  status TEXT DEFAULT 'Completed', 
                  time_taken REAL DEFAULT 0, 
                  pos_id TEXT DEFAULT 'POS-1',
                  customer_mobile TEXT,
                  tax_amount REAL DEFAULT 0.0,
                  discount_amount REAL DEFAULT 0.0,
                  coupon_applied TEXT,
                  points_redeemed INTEGER DEFAULT 0)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS system_settings
                 (key TEXT PRIMARY KEY, value TEXT)''')

    c.execute('''CREATE TABLE IF NOT EXISTS categories
                 (name TEXT PRIMARY KEY)''')

    # Updated Users table for Status
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (username TEXT PRIMARY KEY, 
                  password_hash TEXT, 
                  role TEXT, 
                  full_name TEXT,
                  status TEXT DEFAULT 'Active')''')
                 
    c.execute('''CREATE TABLE IF NOT EXISTS logs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, 
                  user TEXT, action TEXT, details TEXT)''')
                  
    # Active Sessions for Concurrency Control
    c.execute('''CREATE TABLE IF NOT EXISTS active_sessions
                 (pos_id TEXT PRIMARY KEY, username TEXT, login_time TEXT, role TEXT)''')

    # Updated Customers table for Loyalty
    c.execute('''CREATE TABLE IF NOT EXISTS customers
                 (mobile TEXT PRIMARY KEY, 
                  name TEXT, 
                  email TEXT, 
                  visits INTEGER DEFAULT 0, 
                  total_spend REAL DEFAULT 0.0,
                  loyalty_points INTEGER DEFAULT 0,
                  segment TEXT DEFAULT 'New')''')

    c.execute('''CREATE TABLE IF NOT EXISTS terminals
                 (id TEXT PRIMARY KEY, 
                  name TEXT, 
                  location TEXT, 
                  status TEXT DEFAULT 'Active')''')

    c.execute('''CREATE TABLE IF NOT EXISTS stock_requests
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  product_id INTEGER, 
                  product_name TEXT, 
                  quantity INTEGER, 
                  notes TEXT, 
                  status TEXT DEFAULT 'Pending', 
                  requested_by TEXT, 
                  timestamp TEXT)''')

    # FEATURE 2: COUPONS
    c.execute('''CREATE TABLE IF NOT EXISTS coupons
                 (code TEXT PRIMARY KEY, 
                  discount_type TEXT, 
                  value REAL, 
                  min_bill REAL, 
                  valid_until TEXT, 
                  usage_limit INTEGER, 
                  used_count INTEGER DEFAULT 0)''')

    # FEATURE 3 & 8: MARKETING CAMPAIGNS (Festival/Flash)
    c.execute('''CREATE TABLE IF NOT EXISTS campaigns
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  name TEXT, 
                  type TEXT, 
                  start_time TEXT, 
                  end_time TEXT, 
                  config_json TEXT,
                  is_active TEXT DEFAULT 'True')''')
    
    # FEATURE 4: LUCKY DRAWS
    c.execute('''CREATE TABLE IF NOT EXISTS lucky_draws
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  draw_date TEXT, 
                  winner_name TEXT, 
                  winner_mobile TEXT, 
                  prize TEXT, 
                  criteria TEXT)''')

    # --- MIGRATIONS ---
    # Ensure all columns exist (for updates on existing DB files)
    try: c.execute("ALTER TABLE products ADD COLUMN last_restock_date TEXT")
    except: pass
    try: c.execute("ALTER TABLE sales ADD COLUMN pos_id TEXT DEFAULT 'POS-1'")
    except: pass
    try: c.execute("ALTER TABLE sales ADD COLUMN customer_mobile TEXT")
    except: pass
    try: c.execute("ALTER TABLE sales ADD COLUMN tax_amount REAL DEFAULT 0.0")
    except: pass
    # New Migrations
    try: c.execute("ALTER TABLE sales ADD COLUMN discount_amount REAL DEFAULT 0.0")
    except: pass
    try: c.execute("ALTER TABLE sales ADD COLUMN coupon_applied TEXT")
    except: pass
    try: c.execute("ALTER TABLE sales ADD COLUMN points_redeemed INTEGER DEFAULT 0")
    except: pass
    try: c.execute("ALTER TABLE users ADD COLUMN status TEXT DEFAULT 'Active'")
    except: pass
    try: c.execute("ALTER TABLE customers ADD COLUMN loyalty_points INTEGER DEFAULT 0")
    except: pass
    try: c.execute("ALTER TABLE customers ADD COLUMN segment TEXT DEFAULT 'New'")
    except: pass
    # Analytics Migrations
    try: c.execute("ALTER TABLE products ADD COLUMN expiry_date TEXT")
    except: pass
    try: c.execute("ALTER TABLE products ADD COLUMN is_dead_stock TEXT DEFAULT 'False'")
    except: pass
    # Visuals Migration
    try: c.execute("ALTER TABLE products ADD COLUMN image_data BLOB")
    except: pass

    # --- CLEANUP ON RESTART ---
    c.execute("DELETE FROM active_sessions")

    # --- SEED DATA ---
    defaults = {
        "store_name": "SmartInventory Enterprise",
        "upi_id": "merchant@okaxis",
        "currency_symbol": "₹",
        "tax_rate": "18",
        "gst_enabled": "False",
        "default_bill_mode": "Non-GST"
    }
    for k, v in defaults.items():
        c.execute("INSERT OR IGNORE INTO system_settings (key, value) VALUES (?, ?)", (k, v))

    default_cats = ["Electronics", "Groceries", "Beverages", "Fashion", "Stationery", "Health"]
    for cat in default_cats:
        c.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (cat,))

    users = [
        ('ammar', 'admin123', 'Admin', 'Ammar Admin'),
        ('manager', 'manager123', 'Manager', 'Store Manager'),
        ('staff', 'staff123', 'Operator', 'Counter Staff 1'),
        ('staff2', 'staff123', 'Operator', 'Counter Staff 2'),
        ('inv_man', 'inv123', 'Inventory Manager', 'Logistics Head')
    ]
    for u, p, r, n in users:
        ph = hashlib.sha256(p.encode()).hexdigest()
        # FIX: Changed INSERT OR IGNORE to INSERT OR REPLACE to ensure password updates and fixes are applied
        c.execute("INSERT OR REPLACE INTO users (username, password_hash, role, full_name, status) VALUES (?, ?, ?, ?, 'Active')", (u, ph, r, n))

    c.execute("SELECT count(*) FROM products")
    if c.fetchone()[0] == 0:
        products = [
            ('Gaming Laptop', 'Electronics', 85000.00, 5, 70000.00),
            ('Wireless Mouse', 'Electronics', 650.00, 45, 300.00),
            ('Mech Keyboard', 'Electronics', 3500.00, 20, 2000.00),
            ('Premium Tea', 'Beverages', 450.00, 100, 200.00),
            ('Notebook Set', 'Stationery', 120.00, 200, 50.00),
        ]
        for p in products:
            c.execute("INSERT INTO products (name, category, price, stock, cost_price, last_restock_date) VALUES (?, ?, ?, ?, ?, ?)", 
                      (p[0], p[1], p[2], p[3], p[4], datetime.now().strftime("%Y-%m-%d")))

    terminals = [
        ('POS-1', 'Main Counter', 'Entrance', 'Active'),
        ('POS-2', 'Drive Thru', 'Side Window', 'Active'),
        ('Office Dashboard', 'Back Office', 'HQ', 'Active')
    ]
    for t_id, t_name, t_loc, t_stat in terminals:
        c.execute("INSERT OR IGNORE INTO terminals (id, name, location, status) VALUES (?, ?, ?, ?)", (t_id, t_name, t_loc, t_stat))

    conn.commit()
    conn.close()

# --- UTILITY FUNCTIONS ---
def get_setting(key):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT value FROM system_settings WHERE key=?", (key,))
    res = c.fetchone()
    conn.close()
    return res[0] if res else None

def set_setting(key, value):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO system_settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()

def log_activity(user, action, details):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT INTO logs (timestamp, user, action, details) VALUES (?, ?, ?, ?)",
              (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user, action, details))
    conn.commit()
    conn.close()

# --- ATOMIC TRANSACTION MANAGER (FIX FOR LOCKING ISSUES) ---
def process_sale_transaction(cart_items, total, mode, operator, pos_id, customer_mobile, 
                             tax_amount, discount_amount, coupon_code, points_redeemed, 
                             points_earned, integrity_hash, time_taken):
    """
    Handles the entire sale process in a SINGLE database connection to prevent 'database is locked' errors.
    1. Updates Stock
    2. Updates Coupon Usage
    3. Inserts Sale Record
    4. Updates Customer Stats & Loyalty
    """
    conn = get_connection()
    c = conn.cursor()
    sale_id = None
    try:
        # 1. Update Stock
        for item in cart_items:
            c.execute("UPDATE products SET stock = stock - 1, sales_count = sales_count + 1 WHERE id=?", (item['id'],))
        
        # 2. Update Coupon Usage
        if coupon_code:
            c.execute("UPDATE coupons SET used_count = used_count + 1 WHERE code=?", (coupon_code,))

        # 3. Insert Sale Record
        items_json = json.dumps([i['id'] for i in cart_items])
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        c.execute("""INSERT INTO sales (timestamp, total_amount, items_json, integrity_hash, 
                     operator, payment_mode, time_taken, pos_id, customer_mobile, 
                     tax_amount, discount_amount, coupon_applied, points_redeemed) 
                     VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (timestamp, total, items_json, integrity_hash, operator, mode, time_taken, 
                 pos_id, customer_mobile, tax_amount, discount_amount, coupon_applied, points_redeemed))
        sale_id = c.lastrowid

        # 4. Update Customer Stats
        if customer_mobile:
            customer_mobile = customer_mobile.strip()
            # Fetch current data first inside this transaction
            c.execute("SELECT total_spend, loyalty_points FROM customers WHERE mobile=?", (customer_mobile,))
            res = c.fetchone()
            if res:
                curr_spend, curr_points = res
                new_spend = curr_spend + total
                
                # Segmentation Logic
                new_seg = "New"
                if new_spend > 50000: new_seg = "High-Value"
                elif new_spend > 10000: new_seg = "Regular"
                else: new_seg = "Occasional"
                
                # Update stats
                new_points = curr_points + points_earned - points_redeemed
                c.execute("""UPDATE customers SET visits = visits + 1, total_spend = ?, 
                             loyalty_points = ?, segment = ? WHERE mobile=?""", 
                          (new_spend, new_points, new_seg, customer_mobile))

        conn.commit()
        return sale_id
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

# --- CUSTOMER MANAGEMENT (Updated) ---
def get_customer(mobile):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM customers WHERE mobile=?", (mobile.strip(),))
    row = c.fetchone()
    conn.close()
    if row:
        # Schema: mobile, name, email, visits, total_spend, loyalty_points, segment
        lp = row[5] if len(row) > 5 and row[5] is not None else 0
        seg = row[6] if len(row) > 6 and row[6] is not None else 'New'
        return {"mobile": row[0], "name": row[1], "email": row[2], "visits": row[3], "total_spend": row[4], "loyalty_points": lp, "segment": seg}
    return None

def upsert_customer(mobile, name, email):
    mobile = mobile.strip()
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT visits FROM customers WHERE mobile=?", (mobile,))
    res = c.fetchone()
    if res:
        c.execute("UPDATE customers SET name=?, email=? WHERE mobile=?", (name, email, mobile))
    else:
        c.execute("INSERT INTO customers (mobile, name, email, visits, total_spend, loyalty_points, segment) VALUES (?, ?, ?, 0, 0, 0, 'New')", (mobile, name, email))
    conn.commit()
    conn.close()

def get_all_customers():
    conn = get_connection()
    df = pd.read_sql("SELECT * FROM customers", conn)
    conn.close()
    return df

# --- USER MANAGEMENT (Feature #1) ---
def create_user(username, password, role, fullname):
    conn = get_connection()
    c = conn.cursor()
    ph = hashlib.sha256(password.encode()).hexdigest()
    try:
        c.execute("INSERT INTO users (username, password_hash, role, full_name, status) VALUES (?, ?, ?, ?, 'Active')", (username, ph, role, fullname))
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

def update_user_status(username, status):
    """Admin feature to disable/enable users."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE users SET status=? WHERE username=?", (status, username))
    conn.commit()
    conn.close()

def get_user_status(username):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT status FROM users WHERE username=?", (username,))
    res = c.fetchone()
    conn.close()
    return res[0] if res else "Active" # Default to active if not found (or during setup)

def update_password(username, new_password):
    conn = get_connection()
    c = conn.cursor()
    ph = hashlib.sha256(new_password.encode()).hexdigest()
    c.execute("UPDATE users SET password_hash=? WHERE username=?", (ph, username))
    conn.commit()
    conn.close()

def update_fullname(username, name):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE users SET full_name=? WHERE username=?", (name, username))
    conn.commit()
    conn.close()

def get_all_users():
    conn = get_connection()
    df = pd.read_sql("SELECT username, role, full_name, status FROM users", conn)
    conn.close()
    return df

def verify_password(username, password):
    conn = get_connection()
    c = conn.cursor()
    ph = hashlib.sha256(password.encode()).hexdigest()
    c.execute("SELECT 1 FROM users WHERE username=? AND password_hash=?", (username, ph))
    res = c.fetchone()
    conn.close()
    return res is not None

# --- MARKETING: COUPONS (Feature #2) ---
def create_coupon(code, dtype, value, min_bill, days_valid, limit):
    valid_until = (datetime.now() + timedelta(days=days_valid)).strftime("%Y-%m-%d")
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO coupons (code, discount_type, value, min_bill, valid_until, usage_limit) VALUES (?, ?, ?, ?, ?, ?)",
                  (code, dtype, value, min_bill, valid_until, limit))
        conn.commit()
        return True
    except: return False
    finally: conn.close()

def get_coupon(code):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM coupons WHERE code=?", (code,))
    c_data = c.fetchone()
    conn.close()
    if c_data:
        # Schema: code, type, value, min_bill, valid_until, limit, used
        expiry = c_data[4]
        limit = c_data[5]
        used = c_data[6]
        
        if datetime.now() > datetime.strptime(expiry, "%Y-%m-%d"):
            return None, "Expired"
        if used >= limit:
            return None, "Usage Limit Reached"
        
        return {
            "code": c_data[0], "type": c_data[1], "value": c_data[2],
            "min_bill": c_data[3]
        }, "Valid"
    return None, "Invalid Code"

def get_all_coupons():
    conn = get_connection()
    df = pd.read_sql("SELECT * FROM coupons", conn)
    conn.close()
    return df

# --- MARKETING: CAMPAIGNS (Feature #3 & #8) ---
def create_campaign(name, c_type, start, end, config):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT INTO campaigns (name, type, start_time, end_time, config_json) VALUES (?, ?, ?, ?, ?)",
              (name, c_type, start, end, config_json := json.dumps(config)))
    conn.commit()
    conn.close()

def get_active_campaigns():
    """Returns campaigns active RIGHT NOW."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    df = pd.read_sql("SELECT * FROM campaigns WHERE is_active='True' AND start_time <= ? AND end_time >= ?", conn, params=(now_str, now_str))
    conn.close()
    return df

# --- MARKETING: LUCKY DRAW (Feature #4) ---
def pick_lucky_winner(days_lookback, min_spend):
    """Picks a random winner from sales in last X days above Y amount."""
    start_dt = (datetime.now() - timedelta(days=days_lookback)).strftime("%Y-%m-%d")
    conn = get_connection()
    
    # Select distinct customers eligible
    query = f"""
    SELECT DISTINCT customer_mobile
    FROM sales 
    WHERE timestamp >= '{start_dt}' AND total_amount >= {min_spend} AND customer_mobile IS NOT NULL
    """
    df = pd.read_sql(query, conn)
    
    winner = None
    if not df.empty:
        winner_mobile = random.choice(df['customer_mobile'].tolist())
        # Get name
        cust = get_customer(winner_mobile)
        winner = {"name": cust['name'], "mobile": winner_mobile}
        
        # Log it
        c = conn.cursor()
        c.execute("INSERT INTO lucky_draws (draw_date, winner_name, winner_mobile, prize, criteria) VALUES (?, ?, ?, ?, ?)",
                  (datetime.now().strftime("%Y-%m-%d"), winner['name'], winner['mobile'], "Mystery Gift", f"Spend > {min_spend}"))
        conn.commit()
        
    conn.close()
    return winner

def get_lucky_draw_history():
    conn = get_connection()
    df = pd.read_sql("SELECT * FROM lucky_draws ORDER BY id DESC", conn)
    conn.close()
    return df

# --- TERMINAL MANAGEMENT ---
def get_all_terminals():
    conn = get_connection()
    df = pd.read_sql("SELECT * FROM terminals", conn)
    conn.close()
    return df

def get_active_terminal_ids():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT id FROM terminals WHERE status='Active'")
    res = [r[0] for r in c.fetchall()]
    conn.close()
    if "Office Dashboard" not in res: res.append("Office Dashboard")
    return res

def check_terminal_status(t_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT status FROM terminals WHERE id=?", (t_id,))
    res = c.fetchone()
    conn.close()
    return res[0] if res else "Unknown"

def add_terminal(t_id, name, location):
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO terminals (id, name, location, status) VALUES (?, ?, ?, 'Active')", (t_id, name, location))
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

def update_terminal_status(t_id, status):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE terminals SET status=? WHERE id=?", (status, t_id))
    conn.commit()
    conn.close()

# --- STOCK REQUESTS ---
def create_stock_request(prod_id, prod_name, qty, notes, user):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT INTO stock_requests (product_id, product_name, quantity, notes, status, requested_by, timestamp) VALUES (?, ?, ?, ?, 'Pending', ?, ?)",
              (prod_id, prod_name, qty, notes, user, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

def get_stock_requests():
    conn = get_connection()
    df = pd.read_sql("SELECT * FROM stock_requests ORDER BY id DESC", conn)
    conn.close()
    return df

def update_request_status(req_id, status):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE stock_requests SET status=? WHERE id=?", (status, req_id))
    conn.commit()
    conn.close()

# --- PRODUCT MANAGEMENT (CRUD) ---

def add_product(name, category, price, stock, cost_price, expiry_date=None, image_data=None):
    conn = get_connection()
    c = conn.cursor()
    
    # Logic update for NA support
    if expiry_date == "NA":
        expiry_str = "NA"
    elif expiry_date:
        expiry_str = expiry_date.strftime("%Y-%m-%d")
    else:
        # Default behavior if nothing specified: 1 year expiry (Backward compatibility)
        expiry_str = (datetime.now() + timedelta(days=365)).strftime("%Y-%m-%d")

    try:
        # Ensure image_data is bytes or None
        img_blob = sqlite3.Binary(image_data) if image_data else None
        
        c.execute("INSERT INTO products (name, category, price, stock, cost_price, sales_count, last_restock_date, expiry_date, is_dead_stock, image_data) VALUES (?, ?, ?, ?, ?, 0, ?, ?, 'False', ?)",
                  (name, category, price, stock, cost_price, datetime.now().strftime("%Y-%m-%d"), expiry_str, img_blob))
        conn.commit()
        return True
    except Exception as e:
        print(e)
        return False
    finally:
        conn.close()

def update_product(p_id, name, category, price, stock, cost_price):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE products SET name=?, category=?, price=?, stock=?, cost_price=? WHERE id=?",
              (name, category, price, stock, cost_price, p_id))
    conn.commit()
    conn.close()

def delete_product(p_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM products WHERE id=?", (p_id,))
    conn.commit()
    conn.close()

def toggle_dead_stock(p_id, is_dead):
    """Marks a product as Dead Stock."""
    conn = get_connection()
    c = conn.cursor()
    val = 'True' if is_dead else 'False'
    c.execute("UPDATE products SET is_dead_stock=? WHERE id=?", (val, p_id))
    conn.commit()
    conn.close()

def get_all_products():
    conn = get_connection()
    # Need to select image_data as well if used in views, usually safer to select *
    df = pd.read_sql("SELECT * FROM products", conn)
    conn.close()
    return df

def get_product_by_id(p_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM products WHERE id=?", (p_id,))
    row = c.fetchone()
    conn.close()
    if row:
        # Adjusted schema index for new columns
        # id, name, category, price, stock, cost_price, sales_count, last_restock_date, expiry, dead_stock, image
        # Using dict for safety as columns might shift
        col_names = [description[0] for description in c.description]
        data = dict(zip(col_names, row))
        return data
    return None

def restock_product(p_id, quantity):
    """Safely increments stock for a product."""
    if quantity <= 0: return False
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE products SET stock = stock + ?, last_restock_date = ? WHERE id=?",
              (quantity, datetime.now().strftime("%Y-%m-%d"), p_id))
    conn.commit()
    conn.close()
    return True

# --- SESSION LOCKING ---

def is_pos_occupied(pos_id):
    """Returns username if occupied, else None"""
    if pos_id == "Office Dashboard": return None
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT username FROM active_sessions WHERE pos_id=?", (pos_id,))
    res = c.fetchone()
    conn.close()
    return res[0] if res else None

def lock_terminal(pos_id, username, role):
    conn = get_connection()
    c = conn.cursor()
    lock_key = pos_id
    if pos_id == "Office Dashboard":
        lock_key = f"Office_{username}_{random.randint(1000,9999)}"
    c.execute("INSERT OR REPLACE INTO active_sessions (pos_id, username, login_time, role) VALUES (?, ?, ?, ?)",
              (lock_key, username, datetime.now().strftime("%H:%M:%S"), role))
    conn.commit()
    conn.close()

def unlock_terminal(username):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM active_sessions WHERE username=?", (username,))
    conn.commit()
    conn.close()

def force_clear_all_sessions():
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM active_sessions")
    conn.commit()
    conn.close()

# --- ANALYTICS DATA ---

def get_sales_data():
    conn = get_connection()
    df = pd.read_sql("SELECT * FROM sales", conn)
    conn.close()
    return df

def seed_historical_data_if_needed():
    """Retained for backward compatibility. Use seed_advanced_demo_data instead."""
    seed_advanced_demo_data()

def get_categories_list():
    conn = get_connection()
    df = pd.read_sql("SELECT name FROM categories", conn)
    conn.close()
    return df['name'].tolist()

def add_category(name):
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO categories (name) VALUES (?)", (name,))
        conn.commit()
        conn.close()
        return True
    except:
        conn.close()
        return False

# --- NEW: ADVANCED DEMO DATA & FEATURES ---

def seed_advanced_demo_data():
    """Populates the database with rich demo data for categories, products, users, and sales."""
    conn = get_connection()
    c = conn.cursor()

    # 1. Categories
    demo_categories = [
        "Snacks", "Beverages", "Grocery", "Dairy", "Bakery", 
        "Frozen", "Personal Care", "Stationery", "Electronics", "Household"
    ]
    for cat in demo_categories:
        c.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (cat,))

    # 2. Products (~150 items)
    c.execute("SELECT count(*) FROM products")
    if c.fetchone()[0] < 50:
        demo_products = {
            "Snacks": [("Lays Classic", 20, 15), ("Doritos Cheese", 30, 25), ("Pringles", 100, 80), ("Oreo", 40, 30), ("KitKat", 25, 18), ("Lays Chili", 20, 15), ("Cheetos", 25, 18), ("Popcorn", 50, 35), ("Pretzels", 60, 45), ("Biscuits", 30, 20)],
            "Beverages": [("Coke 500ml", 40, 30), ("Pepsi 500ml", 40, 30), ("Red Bull", 125, 90), ("Tropicana Juice", 110, 80), ("Water Bottle", 20, 10), ("Fanta", 40, 30), ("Sprite", 40, 30), ("Iced Tea", 60, 40), ("Cold Coffee", 80, 50), ("Lemonade", 30, 15)],
            "Grocery": [("Rice 1kg", 80, 60), ("Wheat Flour 1kg", 60, 45), ("Sugar 1kg", 50, 40), ("Salt", 20, 10), ("Cooking Oil 1L", 180, 150), ("Dal", 120, 90), ("Spices Pack", 200, 150), ("Pasta", 70, 50), ("Noodles", 20, 15), ("Ketchup", 90, 70)],
            "Dairy": [("Milk 1L", 60, 50), ("Cheese Slices", 120, 90), ("Butter 100g", 55, 45), ("Yogurt", 30, 20), ("Cream", 80, 60)],
            "Bakery": [("Bread", 40, 30), ("Bun", 20, 10), ("Croissant", 80, 50), ("Muffin", 50, 30), ("Cake Slice", 100, 60)],
            "Frozen": [("Frozen Peas", 90, 60), ("Ice Cream Tub", 250, 180), ("French Fries", 150, 100), ("Chicken Nuggets", 300, 220), ("Pizza", 200, 150)],
            "Personal Care": [("Shampoo", 200, 150), ("Soap", 40, 25), ("Toothpaste", 80, 60), ("Face Wash", 150, 100), ("Deodorant", 180, 120)],
            "Stationery": [("Notebook", 50, 30), ("Pen Set", 100, 70), ("Pencil Box", 80, 50), ("A4 Paper Rim", 300, 220), ("Stapler", 120, 80)],
            "Electronics": [("USB Cable", 150, 50), ("Earphones", 500, 300), ("Charger", 400, 200), ("Power Bank", 1200, 900), ("Mouse", 600, 400)],
            "Household": [("Detergent", 200, 160), ("Dish Soap", 80, 50), ("Sponge", 30, 10), ("Trash Bags", 100, 70), ("Air Freshener", 150, 100)]
        }
        for cat, items in demo_products.items():
            for name, price, cost in items:
                stock = random.randint(20, 100)
                # Random expiry 30-365 days
                exp_days = random.randint(30, 365)
                expiry = (datetime.now() + timedelta(days=exp_days)).strftime("%Y-%m-%d")
                c.execute("INSERT INTO products (name, category, price, stock, cost_price, last_restock_date, expiry_date, is_dead_stock) VALUES (?, ?, ?, ?, ?, ?, ?, 'False')",
                          (name, cat, price, stock, cost, datetime.now().strftime("%Y-%m-%d"), expiry))
    
    # 3. Users (Multi-Role)
    demo_users = [
        ('ammar_admin', 'admin123', 'Admin', 'Ammar Husain'),
        ('manager_1', 'manager123', 'Manager', 'Sarah Manager'),
        ('manager_2', 'manager123', 'Manager', 'Mike Manager'),
        ('pos_op_1', 'pos123', 'Operator', 'Alice Operator'),
        ('pos_op_2', 'pos123', 'Operator', 'Bob Operator'),
        ('pos_op_3', 'pos123', 'Operator', 'Charlie Operator'),
        ('pos_op_4', 'pos123', 'Operator', 'Diana Operator')
    ]
    for u, p, r, n in demo_users:
        ph = hashlib.sha256(p.encode()).hexdigest()
        # FIX: Changed INSERT OR IGNORE to INSERT OR REPLACE to ensure password updates and fixes are applied
        c.execute("INSERT OR REPLACE INTO users (username, password_hash, role, full_name, status) VALUES (?, ?, ?, ?, 'Active')", (u, ph, r, n))

    # 4. Sales & Transactions (50+ records)
    c.execute("SELECT count(*) FROM sales")
    if c.fetchone()[0] < 20:
        ops = ['pos_op_1', 'pos_op_2', 'pos_op_3', 'pos_op_4']
        modes = ['Cash', 'UPI', 'Card']
        c.execute("SELECT id, price FROM products")
        all_prods = c.fetchall() # List of (id, price)
        
        for i in range(50):
            # Randomize date within last 30 days
            days_ago = random.randint(0, 30)
            txn_dt = datetime.now() - timedelta(days=days_ago, hours=random.randint(0, 12), minutes=random.randint(0, 59))
            timestamp = txn_dt.strftime("%Y-%m-%d %H:%M:%S")
            
            operator = random.choice(ops)
            mode = random.choice(modes)
            
            # Random Cart
            num_items = random.randint(1, 8)
            cart_items = random.sample(all_prods, min(num_items, len(all_prods)))
            total = sum(p[1] for p in cart_items)
            items_json = json.dumps([p[0] for p in cart_items])
            
            # Customer
            cust_name = f"Customer {i+1}"
            cust_mobile = f"98765{random.randint(10000, 99999)}"
            
            # Insert Sales
            c.execute("""INSERT INTO sales (timestamp, total_amount, items_json, integrity_hash, 
                         operator, payment_mode, time_taken, pos_id, customer_mobile, status) 
                         VALUES (?, ?, ?, 'demo_hash', ?, ?, ?, 'POS-1', ?, 'Completed')""",
                      (timestamp, total, items_json, operator, mode, random.randint(20, 120), cust_mobile))
            
            # Insert Log
            c.execute("INSERT INTO logs (timestamp, user, action, details) VALUES (?, ?, 'Sale', ?)",
                      (timestamp, operator, f"Completed Sale #{i+1} for {total}"))

    conn.commit()
    conn.close()

def get_transaction_history(filters=None):
    """Retrieves full transaction history with optional filters."""
    query = "SELECT id, timestamp, total_amount, payment_mode, operator, customer_mobile, status FROM sales WHERE 1=1"
    params = []
    
    if filters:
        if filters.get('bill_no'):
            query += " AND id = ?"
            params.append(filters['bill_no'])
        if filters.get('operator'):
            query += " AND operator LIKE ?"
            params.append(f"%{filters['operator']}%")
        if filters.get('date'):
            query += " AND timestamp LIKE ?"
            params.append(f"{filters['date']}%")
            
    query += " ORDER BY id DESC"
    
    conn = get_connection()
    df = pd.read_sql(query, conn, params=params)
    conn.close()
    return df

def get_full_logs():
    """Retrieves all system logs."""
    conn = get_connection()
    df = pd.read_sql("SELECT * FROM logs ORDER BY timestamp DESC", conn)
    conn.close()
    return df

def get_category_performance():
    """Analyzes sales by category."""
    conn = get_connection()
    # Join sales and products (simulated via parsing) - SQLite doesn't have easy JSON parse in old versions
    # So we fetch sales and process in Python
    sales = pd.read_sql("SELECT items_json, total_amount FROM sales", conn)
    products = pd.read_sql("SELECT id, category FROM products", conn)
    conn.close()
    
    cat_map = products.set_index('id')['category'].to_dict()
    cat_sales = {}
    
    for _, row in sales.iterrows():
        try:
            item_ids = json.loads(row['items_json'])
            for iid in item_ids:
                cat = cat_map.get(iid, "Unknown")
                # Estimate item price share (simplified: average split)
                share = row['total_amount'] / len(item_ids) if item_ids else 0
                cat_sales[cat] = cat_sales.get(cat, 0) + share
        except: continue
        
    return pd.DataFrame(list(cat_sales.items()), columns=['Category', 'Revenue']).sort_values('Revenue', ascending=False)
