import sqlite3
import pandas as pd
import random
from datetime import datetime, timedelta
import hashlib
import json
import os

# --- POINT 6: FREE DATABASE CONNECTION GUIDANCE ---
# This system uses SQLite (inventory_system.db) by default.
# SQLite is a serverless, file-based database engine that is:
# 1. FREE and requires no setup.
# 2. Native to Python (no pip install needed).
# 3. Thread-safe for local development and demos.
#
# For Multi-Terminal / Multi-POS Simulation:
# - SQLite handles concurrent read/writes using file locking.
# - To simulate multiple POS terminals, open the app in multiple browser tabs/windows.
# - Each tab acts as a separate "Terminal" session sharing this DB.
#
# For Production Deployment:
# - Replace get_connection() to return a psycopg2 connection (PostgreSQL).
# - Example: return psycopg2.connect(os.environ["DATABASE_URL"])
DB_NAME = "inventory_system.db"

def get_connection():
    """Returns a connection to the SQLite database."""
    return sqlite3.connect(DB_NAME, check_same_thread=False, timeout=30)

def init_db():
    """Initializes the database, tables, and seeds default data."""
    conn = get_connection()
    c = conn.cursor()
    
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
    
    # FIX 4 & 7: Added cancellation_reason and cancelled_by
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
                  points_redeemed INTEGER DEFAULT 0,
                  cancellation_reason TEXT,
                  cancelled_by TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS system_settings
                 (key TEXT PRIMARY KEY, value TEXT)''')

    c.execute('''CREATE TABLE IF NOT EXISTS categories
                 (name TEXT PRIMARY KEY)''')

    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (username TEXT PRIMARY KEY, 
                  password_hash TEXT, 
                  role TEXT, 
                  full_name TEXT,
                  status TEXT DEFAULT 'Active')''')
                 
    c.execute('''CREATE TABLE IF NOT EXISTS logs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, 
                  user TEXT, action TEXT, details TEXT)''')
                  
    c.execute('''CREATE TABLE IF NOT EXISTS active_sessions
                 (pos_id TEXT PRIMARY KEY, username TEXT, login_time TEXT, role TEXT)''')

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

    c.execute('''CREATE TABLE IF NOT EXISTS coupons
                 (code TEXT PRIMARY KEY, 
                  discount_type TEXT, 
                  value REAL, 
                  min_bill REAL, 
                  valid_until TEXT, 
                  usage_limit INTEGER, 
                  used_count INTEGER DEFAULT 0)''')

    c.execute('''CREATE TABLE IF NOT EXISTS campaigns
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  name TEXT, 
                  type TEXT, 
                  start_time TEXT, 
                  end_time TEXT, 
                  config_json TEXT,
                  is_active TEXT DEFAULT 'True')''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS lucky_draws
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  draw_date TEXT, 
                  winner_name TEXT, 
                  winner_mobile TEXT, 
                  prize TEXT, 
                  criteria TEXT)''')

    # --- MIGRATIONS ---
    try: c.execute("ALTER TABLE products ADD COLUMN last_restock_date TEXT")
    except: pass
    try: c.execute("ALTER TABLE sales ADD COLUMN pos_id TEXT DEFAULT 'POS-1'")
    except: pass
    try: c.execute("ALTER TABLE sales ADD COLUMN customer_mobile TEXT")
    except: pass
    try: c.execute("ALTER TABLE sales ADD COLUMN tax_amount REAL DEFAULT 0.0")
    except: pass
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
    try: c.execute("ALTER TABLE products ADD COLUMN expiry_date TEXT")
    except: pass
    try: c.execute("ALTER TABLE products ADD COLUMN is_dead_stock TEXT DEFAULT 'False'")
    except: pass
    try: c.execute("ALTER TABLE products ADD COLUMN image_data BLOB")
    except: pass
    
    # FIX 4 & 7: Cancellation Columns
    try: c.execute("ALTER TABLE sales ADD COLUMN cancellation_reason TEXT")
    except: pass
    try: c.execute("ALTER TABLE sales ADD COLUMN cancelled_by TEXT")
    except: pass

    c.execute("DELETE FROM active_sessions")

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

def process_sale_transaction(cart_items, total, mode, operator, pos_id, customer_mobile, 
                             tax_amount, discount_amount, coupon_code, points_redeemed, 
                             points_earned, integrity_hash, time_taken):
    conn = get_connection()
    c = conn.cursor()
    sale_id = None
    try:
        for item in cart_items:
            c.execute("UPDATE products SET stock = stock - 1, sales_count = sales_count + 1 WHERE id=?", (item['id'],))
        
        if coupon_code:
            c.execute("UPDATE coupons SET used_count = used_count + 1 WHERE code=?", (coupon_code,))

        items_json = json.dumps([i['id'] for i in cart_items])
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        c.execute("""INSERT INTO sales (timestamp, total_amount, items_json, integrity_hash, 
                     operator, payment_mode, time_taken, pos_id, customer_mobile, 
                     tax_amount, discount_amount, coupon_applied, points_redeemed) 
                     VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (timestamp, total, items_json, integrity_hash, operator, mode, time_taken, 
                 pos_id, customer_mobile, tax_amount, discount_amount, coupon_code, points_redeemed))
        sale_id = c.lastrowid

        if customer_mobile:
            customer_mobile = customer_mobile.strip()
            c.execute("SELECT total_spend, loyalty_points FROM customers WHERE mobile=?", (customer_mobile,))
            res = c.fetchone()
            if res:
                curr_spend, curr_points = res
                new_spend = curr_spend + total
                
                new_seg = "New"
                if new_spend > 50000: new_seg = "High-Value"
                elif new_spend > 10000: new_seg = "Regular"
                else: new_seg = "Occasional"
                
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

# --- FIX 7: ROLE-BASED ORDER CANCELLATION ---
def cancel_sale_transaction(sale_id, operator, role, reason):
    """
    Enhanced Undo Logic:
    - Checks role permissions
    - Requires reason
    - Updates cancelled_by and cancellation_reason
    - Restores Inventory
    """
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("SELECT items_json, status, operator FROM sales WHERE id=?", (sale_id,))
        res = c.fetchone()
        if not res:
            return False, "Sale ID not found"
        
        items_json_str, status, sale_operator = res
        
        if status == 'Cancelled':
            return False, "Sale already cancelled"
            
        # Permission Check
        if role == 'Operator' and sale_operator != operator:
            return False, "Permission Denied: Operators can only cancel their own sales."

        items_ids = json.loads(items_json_str)
        
        for pid in items_ids:
            c.execute("UPDATE products SET stock = stock + 1, sales_count = sales_count - 1 WHERE id=?", (pid,))
            
        c.execute("""UPDATE sales SET status = 'Cancelled', cancellation_reason = ?, cancelled_by = ? 
                     WHERE id=?""", (reason, operator, sale_id))
        
        c.execute("INSERT INTO logs (timestamp, user, action, details) VALUES (?, ?, ?, ?)",
                  (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), operator, "Undo Sale", 
                   f"Cancelled Sale #{sale_id}. Reason: {reason}"))
        
        conn.commit()
        return True, "Success"
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()

def redo_sale_transaction(sale_id, operator):
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("SELECT items_json, status FROM sales WHERE id=?", (sale_id,))
        res = c.fetchone()
        if not res: return False, "ID not found"
        
        items_json_str, status = res
        if status != 'Cancelled': return False, "Sale is not cancelled"
        
        items_ids = json.loads(items_json_str)
        
        for pid in items_ids:
            c.execute("UPDATE products SET stock = stock - 1, sales_count = sales_count + 1 WHERE id=?", (pid,))
            
        c.execute("UPDATE sales SET status = 'Completed', cancellation_reason=NULL, cancelled_by=NULL WHERE id=?", (sale_id,))
        
        c.execute("INSERT INTO logs (timestamp, user, action, details) VALUES (?, ?, ?, ?)",
                  (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), operator, "Redo Sale", f"Restored Sale #{sale_id}"))
        
        conn.commit()
        return True, "Success"
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()

def get_customer(mobile):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM customers WHERE mobile=?", (mobile.strip(),))
    row = c.fetchone()
    conn.close()
    if row:
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
    return res[0] if res else "Active"

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

# --- FIX 9: AUTOMATED COUPON GENERATION ---
def generate_auto_coupon(customer_mobile):
    """Generates a personalized coupon after a sale."""
    if not customer_mobile: return None
    
    code = f"SAVE10-{random.randint(1000,9999)}"
    # Simple rule: 10% off for next visit, valid 30 days
    if create_coupon(code, "%", 10.0, 500.0, 30, 1):
        return code
    return None

def create_campaign(name, c_type, start, end, config):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT INTO campaigns (name, type, start_time, end_time, config_json) VALUES (?, ?, ?, ?, ?)",
              (name, c_type, start, end, config_json := json.dumps(config)))
    conn.commit()
    conn.close()

def get_active_campaigns():
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    df = pd.read_sql("SELECT * FROM campaigns WHERE is_active='True' AND start_time <= ? AND end_time >= ?", conn, params=(now_str, now_str))
    conn.close()
    return df

def pick_lucky_winner(days_lookback, min_spend):
    start_dt = (datetime.now() - timedelta(days=days_lookback)).strftime("%Y-%m-%d")
    conn = get_connection()
    query = f"""
    SELECT DISTINCT customer_mobile
    FROM sales 
    WHERE timestamp >= '{start_dt}' AND total_amount >= {min_spend} 
    AND customer_mobile IS NOT NULL AND customer_mobile != '' AND customer_mobile != 'None'
    """
    df = pd.read_sql(query, conn)
    
    winner = None
    if not df.empty:
        winner_mobile = random.choice(df['customer_mobile'].tolist())
        cust = get_customer(winner_mobile)
        name_val = cust['name'] if cust else "Unknown Customer"
        
        winner = {"name": name_val, "mobile": winner_mobile}
        
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

def get_all_terminals():
    conn = get_connection()
    df = pd.read_sql("SELECT * FROM terminals", conn)
    conn.close()
    return df

def get_all_terminals_status():
    """
    Returns terminals joined with active session data
    to determine real-time availability.
    """
    conn = get_connection()
    query = """
    SELECT t.id, t.name, t.location, t.status, s.username as current_user, s.login_time 
    FROM terminals t
    LEFT JOIN active_sessions s ON t.id = s.pos_id
    """
    df = pd.read_sql(query, conn)
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

def force_unlock_terminal(pos_id):
    """Forcefully removes a session lock for a specific terminal."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM active_sessions WHERE pos_id=?", (pos_id,))
    conn.commit()
    conn.close()

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

def add_product(name, category, price, stock, cost_price, expiry_date=None, image_data=None):
    conn = get_connection()
    c = conn.cursor()
    
    if expiry_date == "NA":
        expiry_str = "NA"
    elif expiry_date:
        expiry_str = expiry_date.strftime("%Y-%m-%d")
    else:
        expiry_str = (datetime.now() + timedelta(days=365)).strftime("%Y-%m-%d")

    try:
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
    conn = get_connection()
    c = conn.cursor()
    val = 'True' if is_dead else 'False'
    c.execute("UPDATE products SET is_dead_stock=? WHERE id=?", (val, p_id))
    conn.commit()
    conn.close()

def get_all_products():
    conn = get_connection()
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
        col_names = [description[0] for description in c.description]
        data = dict(zip(col_names, row))
        return data
    return None

def restock_product(p_id, quantity):
    if quantity <= 0: return False
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE products SET stock = stock + ?, last_restock_date = ? WHERE id=?",
              (quantity, datetime.now().strftime("%Y-%m-%d"), p_id))
    conn.commit()
    conn.close()
    return True

def is_pos_occupied(pos_id):
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

def get_sales_data():
    conn = get_connection()
    df = pd.read_sql("SELECT * FROM sales", conn)
    conn.close()
    return df

def seed_advanced_demo_data():
    conn = get_connection()
    c = conn.cursor()

    demo_categories = [
        "Snacks", "Beverages", "Grocery", "Dairy", "Bakery", 
        "Frozen", "Personal Care", "Stationery", "Electronics", "Household"
    ]
    for cat in demo_categories:
        c.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (cat,))

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
                exp_days = random.randint(30, 365)
                expiry = (datetime.now() + timedelta(days=exp_days)).strftime("%Y-%m-%d")
                c.execute("INSERT INTO products (name, category, price, stock, cost_price, last_restock_date, expiry_date, is_dead_stock) VALUES (?, ?, ?, ?, ?, ?, ?, 'False')",
                          (name, cat, price, stock, cost, datetime.now().strftime("%Y-%m-%d"), expiry))
    
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
        c.execute("INSERT OR REPLACE INTO users (username, password_hash, role, full_name, status) VALUES (?, ?, ?, ?, 'Active')", (u, ph, r, n))

    # REALISTIC CUSTOMER DATA FOR EXAM EVALUATION
    demo_customers = [
        ("9876500001", "Amit Sharma", "amit.s@example.com", "Regular"),
        ("9876500002", "Priya Singh", "priya.s@example.com", "High-Value"),
        ("9876500003", "Rahul Verma", "rahul.v@example.com", "Occasional"),
        ("9876500004", "Sneha Gupta", "sneha.g@example.com", "New"),
        ("9876500005", "Vikram Malhotra", "vikram.m@example.com", "High-Value"),
        ("9876500006", "Anjali Mehta", "anjali.m@example.com", "Regular"),
        ("9876500007", "Rohan Das", "rohan.d@example.com", "New"),
        ("9876500008", "Ishita Patel", "ishita.p@example.com", "Regular"),
        ("9876500009", "Karan Johar", "karan.j@example.com", "Occasional"),
        ("9876500010", "Simran Kaur", "simran.k@example.com", "High-Value"),
        ("9876500011", "Arjun Rampal", "arjun.r@example.com", "Regular"),
        ("9876500012", "Deepika P", "deepika.p@example.com", "High-Value"),
        ("9876500013", "Ranveer S", "ranveer.s@example.com", "Regular"),
        ("9876500014", "Alia B", "alia.b@example.com", "New"),
        ("9876500015", "Ranbir K", "ranbir.k@example.com", "Occasional"),
        ("9876500016", "Katrina K", "katrina.k@example.com", "Regular"),
        ("9876500017", "Salman K", "salman.k@example.com", "High-Value"),
        ("9876500018", "Shahrukh K", "shahrukh.k@example.com", "High-Value"),
        ("9876500019", "Aamir K", "aamir.k@example.com", "Occasional"),
        ("9876500020", "Akshay K", "akshay.k@example.com", "Regular")
    ]
    for mob, name, email, seg in demo_customers:
        c.execute("INSERT OR IGNORE INTO customers (mobile, name, email, segment, visits, total_spend, loyalty_points) VALUES (?, ?, ?, ?, 0, 0, 0)", 
                  (mob, name, email, seg))

    c.execute("SELECT count(*) FROM sales")
    if c.fetchone()[0] < 50:
        ops = ['pos_op_1', 'pos_op_2', 'pos_op_3', 'pos_op_4']
        modes = ['Cash', 'UPI', 'Card']
        c.execute("SELECT id, price FROM products")
        all_prods = c.fetchall()
        
        for i in range(60): # Generate 60 transactions
            days_ago = random.randint(0, 30)
            txn_dt = datetime.now() - timedelta(days=days_ago, hours=random.randint(0, 12), minutes=random.randint(0, 59))
            timestamp = txn_dt.strftime("%Y-%m-%d %H:%M:%S")
            
            operator = random.choice(ops)
            mode = random.choice(modes)
            cust = random.choice(demo_customers)
            cust_mobile = cust[0]
            
            num_items = random.randint(1, 8)
            cart_items = random.sample(all_prods, min(num_items, len(all_prods)))
            total = sum(p[1] for p in cart_items)
            items_json = json.dumps([p[0] for p in cart_items])
            
            # 10% chance of being cancelled
            status = 'Completed'
            reason = None
            cancelled_by = None
            if random.random() < 0.1:
                status = 'Cancelled'
                reason = 'Customer Changed Mind'
                cancelled_by = 'ammar_admin'
            
            c.execute("""INSERT INTO sales (timestamp, total_amount, items_json, integrity_hash, 
                         operator, payment_mode, time_taken, pos_id, customer_mobile, status, cancellation_reason, cancelled_by) 
                         VALUES (?, ?, ?, 'demo_hash', ?, ?, ?, 'POS-1', ?, ?, ?, ?)""",
                      (timestamp, total, items_json, operator, mode, random.randint(20, 120), cust_mobile, status, reason, cancelled_by))
            
            if status == 'Completed':
                c.execute("UPDATE customers SET visits = visits + 1, total_spend = total_spend + ?, loyalty_points = loyalty_points + ? WHERE mobile=?",
                        (total, int(total/100), cust_mobile))
                c.execute("INSERT INTO logs (timestamp, user, action, details) VALUES (?, ?, 'Sale', ?)",
                        (timestamp, operator, f"Completed Sale for {total}"))
            else:
                c.execute("INSERT INTO logs (timestamp, user, action, details) VALUES (?, ?, 'Undo Sale', ?)",
                        (timestamp, operator, f"Cancelled Sale for {total}"))

    conn.commit()
    conn.close()

def get_transaction_history(filters=None):
    query = "SELECT id, timestamp, total_amount, payment_mode, operator, customer_mobile, status, pos_id, integrity_hash FROM sales WHERE 1=1"
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
    try:
        df = pd.read_sql(query, conn, params=params)
    except:
        df = pd.DataFrame()
    finally:
        conn.close()
    return df

def get_full_logs():
    conn = get_connection()
    df = pd.read_sql("SELECT * FROM logs ORDER BY id DESC", conn)
    conn.close()
    return df

def get_category_performance():
    conn = get_connection()
    # FIX 3: Exclude Cancelled Orders
    sales = pd.read_sql("SELECT items_json, total_amount FROM sales WHERE status != 'Cancelled'", conn)
    products = pd.read_sql("SELECT id, category FROM products", conn)
    conn.close()
    
    cat_map = products.set_index('id')['category'].to_dict()
    cat_sales = {}
    
    for _, row in sales.iterrows():
        try:
            item_ids = json.loads(row['items_json'])
            if not item_ids: continue
            
            for iid in item_ids:
                cat = cat_map.get(iid, "Unknown")
                share = row['total_amount'] / len(item_ids) 
                cat_sales[cat] = cat_sales.get(cat, 0) + share
        except: continue
        
    return pd.DataFrame(list(cat_sales.items()), columns=['Category', 'Revenue']).sort_values('Revenue', ascending=False)

# --- FIX 3: CATEGORY & TERMINAL METHODS ---
def get_categories_list():
    """Fetches distinct categories for UI filters."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT name FROM categories")
    cats = [row[0] for row in c.fetchall()]
    conn.close()
    return cats

def add_category(name):
    """Adds a new category."""
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO categories (name) VALUES (?)", (name,))
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

def get_terminal_stats():
    """Calculates active orders and revenue per POS terminal."""
    conn = get_connection()
    df = pd.read_sql("""
        SELECT 
            pos_id, 
            COUNT(*) as order_count, 
            SUM(total_amount) as total_revenue,
            MAX(timestamp) as last_active
        FROM sales 
        WHERE status != 'Cancelled'
        GROUP BY pos_id
    """, conn)
    conn.close()
    return df
