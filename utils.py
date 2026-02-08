import hashlib
import time
import math
import random
import pandas as pd
import numpy as np
import qrcode
from io import BytesIO
from fpdf import FPDF
import urllib.parse
from datetime import datetime, timedelta
import shutil
import os
import json
from PIL import Image
import re

# --- CONDITIONAL IMPORT FOR OPENCV (CLOUD COMPATIBILITY) ---
try:
    import cv2
except (ImportError, OSError):
    cv2 = None

# --- FIX 1: ROBUST PYZBAR IMPORT ---
# Catch OSError which happens when libzbar0 is missing on Linux
try:
    from pyzbar.pyzbar import decode as qr_decode
except (ImportError, OSError):
    qr_decode = None

# --- CONDITIONAL IMPORT FOR TKINTER ---
try:
    import tkinter as tk
    from PIL import ImageTk
except (ImportError, OSError):
    tk = None
    ImageTk = None

# --- SYSTEM TIME HELPER ---
def get_system_time():
    """Returns current system time. Useful for centralized time sync."""
    return datetime.now()

# --- SECURITY: PASSWORD STRENGTH ---
def check_password_strength(password):
    """
    Validates password strength.
    Returns: (score [0-4], label, color)
    """
    score = 0
    if len(password) >= 8: score += 1
    if re.search(r"[A-Z]", password): score += 1
    if re.search(r"[a-z]", password): score += 1
    if re.search(r"\d", password) or re.search(r"[ !@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?]", password): score += 1
    
    if score == 0: return 0, "Very Weak", "#ef4444"
    elif score == 1: return 1, "Weak", "#ef4444"
    elif score == 2: return 2, "Medium", "#f59e0b"
    elif score == 3: return 3, "Strong", "#10b981"
    elif score == 4: return 4, "Very Strong", "#059669"
    return 0, "Unknown", "#ef4444"

# --- REAL-TIME LIVE SCANNER ---
class LiveBarcodeScanner:
    def __init__(self):
        self.detected_code = None
        self.cap = None
        self.root = None
        self.panel = None

    def start_scanner(self):
        if tk is None or cv2 is None:
            return None

        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            return None, "Error: Could not access camera."

        self.root = tk.Tk()
        self.root.title("POS Live Scanner - Point at Barcode")
        self.root.geometry("640x520")
        self.root.resizable(False, False)
        
        lbl_instruct = tk.Label(self.root, text="Scanning... Hold product steady.", font=("Arial", 12), bg="black", fg="white")
        lbl_instruct.pack(fill=tk.X)
        
        self.panel = tk.Label(self.root)
        self.panel.pack(padx=10, pady=10)
        
        btn_cancel = tk.Button(self.root, text="Cancel Scan", command=self.close_scanner, bg="#ef4444", fg="white", font=("Arial", 10, "bold"))
        btn_cancel.pack(pady=5)

        self.video_loop()
        self.root.protocol("WM_DELETE_WINDOW", self.close_scanner)
        self.root.mainloop()
        
        if self.cap and self.cap.isOpened():
            self.cap.release()
            
        return self.detected_code

    def video_loop(self):
        if self.detected_code: return

        ret, frame = self.cap.read()
        if ret:
            decoded_objects = qr_decode(frame)
            for obj in decoded_objects:
                points = obj.polygon
                if len(points) == 4:
                    pts = np.array(points, dtype=np.int32)
                    cv2.polylines(frame, [pts], True, (0, 255, 0), 3)
                
                raw_data = obj.data.decode("utf-8")
                self.detected_code = raw_data
                self.root.after(500, self.close_scanner)
                
            cv2image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGBA)
            img = Image.fromarray(cv2image)
            if ImageTk:
                imgtk = ImageTk.PhotoImage(image=img)
                self.panel.imgtk = imgtk
                self.panel.config(image=imgtk)
            
            self.root.after(10, self.video_loop)
        else:
            self.close_scanner()

    def close_scanner(self):
        if self.root:
            self.root.quit()
            self.root.destroy()
            self.root = None

def run_live_scan():
    if qr_decode is None:
        return None, "Error: pyzbar library not installed (missing libzbar0)."
    
    if tk is None:
        return None, "⚠️ Live camera scanning is disabled in Cloud Runtime (Tkinter missing). Use manual entry."
    
    if cv2 is None:
        return None, "⚠️ Live camera scanning is disabled (OpenCV libGL missing). Use manual entry."
    
    scanner = LiveBarcodeScanner()
    try:
        code = scanner.start_scanner()
        if code:
            return code, "Success"
        else:
            return None, "Scan cancelled or no code found."
    except Exception as e:
        return None, f"Scanner Error: {str(e)}"

# --- LOYALTY ---
def calculate_loyalty_points(amount):
    return int(amount // 100)

# --- RECOMMENDATION ---
def get_personalized_offer(customer, product_df):
    if not customer: return "Scan customer to see offers."
    if not product_df.empty:
        cats = product_df['category'].unique()
        fav_cat = random.choice(cats)
        return f"🌟 Special for you: 10% OFF on all {fav_cat} today!"
    return "Check out our new arrivals!"

# --- QR GENERATION ---
def generate_product_qr_image(product_id, product_name):
    data = f"PROD:{product_id}"
    qr = qrcode.QRCode(box_size=10, border=4)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf)
    return buf.getvalue()

def generate_qr_labels_pdf(products):
    """
    Fixed Bulk QR Generator.
    Ensures all products are iterated and placed correctly.
    """
    pdf = FPDF(orientation='P', unit='mm', format='A4')
    pdf.set_auto_page_break(True, margin=10)
    pdf.add_page()
    pdf.set_font("Arial", size=10)
    
    x_start, y_start = 10, 10
    w, h = 60, 40 
    margin = 5
    col, row = 0, 0
    
    # Pre-generate temp files to avoid IO race conditions
    temp_files = []
    
    try:
        for p in products:
            x = x_start + (col * (w + margin))
            y = y_start + (row * (h + margin))
            
            # Draw Border
            pdf.rect(x, y, w, h)
            
            # Text
            pdf.set_xy(x + 2, y + 2)
            pdf.set_font("Arial", 'B', 8)
            safe_name = p['name'].encode('latin-1', 'replace').decode('latin-1')
            pdf.multi_cell(w-4, 4, f"{safe_name[:35]}", align='C')
            
            pdf.set_xy(x + 2, y + 10)
            pdf.set_font("Arial", '', 7)
            pdf.cell(w-4, 4, f"ID: {p['id']} | Cat: {p['category'][:10]}", align='C')
            
            # Generate QR
            qr_bytes = generate_product_qr_image(p['id'], p['name'])
            
            # Unique temp file
            temp_path = f"temp_qr_{p['id']}_{random.randint(1000,9999)}.png"
            with open(temp_path, "wb") as f:
                f.write(qr_bytes)
            temp_files.append(temp_path)
            
            # Place Image
            pdf.image(temp_path, x=x+20, y=y+16, w=20, h=20)
            
            col += 1
            if col >= 3:
                col = 0
                row += 1
                if row >= 6:
                    row = 0
                    pdf.add_page()
                    
    finally:
        # Cleanup
        for tf in temp_files:
            if os.path.exists(tf):
                os.remove(tf)
                
    return pdf.output(dest='S').encode('latin-1')

# --- EXPIRY LOGIC ---
def calculate_advanced_loss_prevention(cart_items):
    if not cart_items: return 0.0, []
    
    today = datetime.now()
    discount = 0.0
    messages = []
    
    item_counts = {}
    for item in cart_items:
        if item['id'] not in item_counts:
            item_counts[item['id']] = {'obj': item, 'count': 0}
        item_counts[item['id']]['count'] += 1
        
    for pid, data in item_counts.items():
        item = data['obj']
        qty = data['count']
        
        exp_date_str = item.get('expiry_date')
        if not exp_date_str or str(exp_date_str).upper() == "NA":
            continue
            
        try:
            exp_date = datetime.strptime(str(exp_date_str), "%Y-%m-%d")
            days_left = (exp_date - today).days
            
            if days_left < 0:
                pass
            elif days_left <= 10:
                item_discount = qty * item['price']
                discount += item_discount
                messages.append(f"CRITICAL: {item['name']} is FREE (Expires in {days_left}d)")
            elif 10 < days_left <= 30:
                free_items = qty // 2
                if free_items > 0:
                    item_discount = free_items * item['price']
                    discount += item_discount
                    messages.append(f"BOGO Applied: {item['name']} ({days_left}d left)")
            elif 30 < days_left <= 60:
                item_discount = qty * item['price'] * 0.50
                discount += item_discount
                messages.append(f"50% Clearance: {item['name']} ({days_left}d left)")
            elif 60 < days_left <= 90:
                item_discount = qty * item['price'] * 0.40
                discount += item_discount
                messages.append(f"40% Discount: {item['name']} ({days_left}d left)")
        except:
            pass
            
    return discount, messages

def calculate_expiry_bogo(cart_items):
    return calculate_advanced_loss_prevention(cart_items)

def parse_qr_input(data_str):
    if not data_str: return None
    try:
        if data_str.startswith("PROD:"):
            return int(data_str.split(":")[1])
    except:
        return None
    return None

def decode_qr_image(image_file):
    if qr_decode is None:
        return None
    try:
        image = Image.open(image_file)
        decoded_objects = qr_decode(image)
        for obj in decoded_objects:
            return obj.data.decode("utf-8")
    except Exception as e:
        return None
    return None

def get_sound_html(sound_type):
    if sound_type == 'success':
        src = "https://www.soundjay.com/buttons/sounds/button-3.mp3"
    elif sound_type == 'error':
        src = "https://www.soundjay.com/buttons/sounds/button-10.mp3"
    elif sound_type == 'celebration':
        # Short cheer/tada sound
        src = "https://www.soundjay.com/human/sounds/applause-01.mp3"
    else: 
        src = "https://www.soundjay.com/buttons/sounds/button-16.mp3"
        
    return f"""
    <audio autoplay>
        <source src="{src}" type="audio/mpeg">
    </audio>
    """

def generate_hash(data_string):
    return hashlib.sha256(data_string.encode()).hexdigest()

def generate_integrity_hash(txn_data):
    raw_string = f"{txn_data[0]}|{txn_data[1]}|{txn_data[2]}|{txn_data[3]}"
    return hashlib.sha256(raw_string.encode()).hexdigest()

# --- TRIE ---
class TrieNode:
    def __init__(self):
        self.children = {}
        self.is_end_of_word = False
        self.data = None

class Trie:
    def __init__(self):
        self.root = TrieNode()

    def insert(self, word, data):
        node = self.root
        for char in word.lower():
            if char not in node.children:
                node.children[char] = TrieNode()
            node = node.children[char]
        node.is_end_of_word = True
        node.data = data

    def search_prefix(self, prefix):
        node = self.root
        for char in prefix.lower():
            if char not in node.children:
                return []
            node = node.children[char]
        return self._collect_words(node)

    def _collect_words(self, node):
        results = []
        if node.is_end_of_word:
            results.append(node.data)
        for child in node.children.values():
            results.extend(self._collect_words(child))
        return results

def linear_search(data_list, key, value):
    for item in data_list:
        if str(item.get(key)).lower() == str(value).lower():
            return item
    return None

def binary_search(sorted_list, key, value):
    low = 0
    high = len(sorted_list) - 1
    
    while low <= high:
        mid = (low + high) // 2
        mid_val = sorted_list[mid].get(key)
        
        if mid_val < value:
            low = mid + 1
        elif mid_val > value:
            high = mid - 1
        else:
            return sorted_list[mid]
    return None

class POSQueueSimulator:
    def __init__(self):
        self.queue = [] 
    
    def simulate_peak_hour(self, num_customers):
        wait_times = []
        service_time_per_customer = 3 
        
        for i in range(num_customers):
            arrival_offset = random.randint(0, 10)
            wait = (i * service_time_per_customer) + arrival_offset
            wait_times.append(wait)
        
        return {
            "avg_wait": sum(wait_times)/len(wait_times),
            "max_queue_length": num_customers,
            "throughput": num_customers / ((max(wait_times)/60) + 0.1) 
        }

def calculate_abc_analysis(df_products):
    if df_products.empty: return df_products
    
    df = df_products.copy()
    df['inventory_value'] = df['price'] * df['stock']
    df = df.sort_values('inventory_value', ascending=False)
    
    df['cumulative_value'] = df['inventory_value'].cumsum()
    df['total_value'] = df['inventory_value'].sum()
    df['cumulative_perc'] = df['cumulative_value'] / df['total_value']
    
    def classify(perc):
        if perc <= 0.70: return 'A (High Value)'
        elif perc <= 0.90: return 'B (Medium Value)'
        else: return 'C (Low Value)'
        
    df['abc_class'] = df['cumulative_perc'].apply(classify)
    return df

def calculate_inventory_metrics(df_sales, df_products):
    # FIX: Ensure sales DF excludes cancelled items before metric calc
    if 'status' in df_sales.columns:
        df_sales = df_sales[df_sales['status'] != 'Cancelled']

    metrics = []
    for _, prod in df_products.iterrows():
        annual_demand = prod['sales_count'] * 12 if prod['sales_count'] > 0 else 10 
        holding_cost = prod['cost_price'] * 0.20 
        order_cost = 500 
        
        eoq = 0
        if holding_cost > 0:
            eoq = math.sqrt((2 * annual_demand * order_cost) / holding_cost)
            
        metrics.append({
            "name": prod['name'],
            "annual_demand_est": annual_demand,
            "eoq": math.ceil(eoq),
            "reorder_point": math.ceil(annual_demand/365 * 7) + 5 
        })
    return pd.DataFrame(metrics)

def forecast_next_period(sales_array, window=5):
    if len(sales_array) < window:
        return np.mean(sales_array) if len(sales_array) > 0 else 0
        
    recent = sales_array[-window:]
    weights = np.arange(1, len(recent) + 1)
    return np.dot(recent, weights) / weights.sum()

def analyze_trend_slope(sales_series):
    if len(sales_series) < 2: return "Stable"
    x = np.arange(len(sales_series))
    y = np.array(sales_series)
    slope, _ = np.polyfit(x, y, 1)
    
    if slope > 0.5: return "↗️ Increasing"
    elif slope < -0.5: return "↘️ Decreasing"
    else: return "➡️ Stable"

def detect_fraud(cart_items, total, time_sec):
    flags = []
    qty_map = {}
    for i in cart_items: qty_map[i['name']] = qty_map.get(i['name'], 0) + 1
    
    if any(q > 10 for q in qty_map.values()):
        flags.append("Bulk Purchase Anomaly (>10 units)")
        
    if len(cart_items) > 3 and time_sec < 5:
        flags.append("Superhuman Speed (<5s)")
        
    if total > 100000:
        flags.append("High Value Transaction (>1L)")
        
    return flags

def rank_products(df_sales, df_products):
    if df_sales.empty: return pd.DataFrame()
    
    # FIX 3: Filter out cancelled transactions for ranking
    if 'status' in df_sales.columns:
        active_sales = df_sales[df_sales['status'] != 'Cancelled']
    else:
        active_sales = df_sales

    import json
    all_items = []
    for _, row in active_sales.iterrows():
        try:
            ids = json.loads(row['items_json'])
            all_items.extend(ids)
        except: continue
        
    from collections import Counter
    counts = Counter(all_items)
    
    ranking_data = []
    for _, prod in df_products.iterrows():
        qty = counts.get(prod['id'], 0)
        rev = qty * prod['price']
        ranking_data.append({
            "name": prod['name'],
            "qty_sold": qty,
            "revenue": rev,
            "score": (qty * 10) + (rev * 0.01) 
        })
        
    ranking_data.sort(key=lambda x: x['score'], reverse=True)
    
    for i, item in enumerate(ranking_data):
        if i == 0: item['rank'] = "🥇 Top Seller"
        elif i < len(ranking_data)/2: item['rank'] = "🥈 Average Performer"
        else: item['rank'] = "🥉 Low Performer"
        
    return pd.DataFrame(ranking_data)

# --- PROFIT & LOSS ANALYSIS ---
def calculate_profit_loss(df_sales, df_products):
    if df_sales.empty or df_products.empty:
        return {"net_profit": 0, "total_revenue": 0, "total_cost": 0, "margin_percent": 0}, pd.DataFrame()

    # FIX 3: STRICT FINANCIAL ACCURACY - Exclude Cancelled Orders
    if 'status' in df_sales.columns:
        active_sales = df_sales[df_sales['status'] != 'Cancelled']
    else:
        active_sales = df_sales

    prod_map = df_products.set_index('id')[['name', 'category', 'cost_price', 'price']].to_dict('index')
    
    category_pl = {}
    total_rev = 0
    total_cost = 0

    for _, row in active_sales.iterrows():
        try:
            items = json.loads(row['items_json'])
            for pid in items:
                if pid in prod_map:
                    p = prod_map[pid]
                    cp = p['cost_price']
                    sp = p['price']
                    
                    profit = sp - cp
                    
                    total_rev += sp
                    total_cost += cp
                    
                    cat = p['category']
                    if cat not in category_pl:
                        category_pl[cat] = {'revenue': 0, 'cost': 0, 'profit': 0}
                    category_pl[cat]['revenue'] += sp
                    category_pl[cat]['cost'] += cp
                    category_pl[cat]['profit'] += profit
                    
        except: continue

    net_profit = total_rev - total_cost
    
    pl_data = []
    for cat, metrics in category_pl.items():
        pl_data.append({
            "Category": cat,
            "Revenue": metrics['revenue'],
            "Cost": metrics['cost'],
            "Profit": metrics['profit'],
            "Margin %": (metrics['profit'] / metrics['revenue'] * 100) if metrics['revenue'] > 0 else 0
        })
    
    return {
        "net_profit": net_profit, 
        "total_revenue": total_rev, 
        "total_cost": total_cost,
        "margin_percent": (net_profit / total_rev * 100) if total_rev > 0 else 0
    }, pd.DataFrame(pl_data)

def analyze_risk_inventory(df_products):
    if df_products.empty: return {}, pd.DataFrame()
    
    today = datetime.now()
    risk_data = []
    
    dead_stock_val = 0
    expired_stock_val = 0
    near_expiry_val = 0
    
    for _, row in df_products.iterrows():
        status = "Safe"
        is_dead = str(row.get('is_dead_stock', 'False')) == 'True'
        exp_date_str = row.get('expiry_date')
        
        if exp_date_str and str(exp_date_str).upper() != "NA":
            try:
                exp_date = datetime.strptime(str(exp_date_str), "%Y-%m-%d")
                days_left = (exp_date - today).days
                
                if days_left < 0:
                    status = "Expired"
                    expired_stock_val += (row['stock'] * row['cost_price'])
                elif days_left < 30:
                    status = "Near Expiry"
                    near_expiry_val += (row['stock'] * row['cost_price'])
            except: 
                pass
        elif str(exp_date_str).upper() == "NA":
             status = "Non-Expirable"
            
        if is_dead:
            dead_stock_val += (row['stock'] * row['cost_price'])
            
        risk_data.append({
            "Name": row['name'],
            "Stock": row['stock'],
            "Value": row['stock'] * row['cost_price'],
            "Status": status,
            "Is Dead Stock": "Yes" if is_dead else "No",
            "Expiry": exp_date_str
        })
        
    return {
        "dead_stock_value": dead_stock_val,
        "expired_loss": expired_stock_val,
        "near_expiry_risk": near_expiry_val
    }, pd.DataFrame(risk_data)

def calculate_financial_ratios(df_sales, df_products):
    current_inv_val = (df_products['stock'] * df_products['cost_price']).sum()
    
    # FIX 3: Filter Cancelled
    if 'status' in df_sales.columns:
        active_sales = df_sales[df_sales['status'] != 'Cancelled']
    else:
        active_sales = df_sales

    cogs = 0
    prod_cp_map = df_products.set_index('id')['cost_price'].to_dict()
    
    for _, row in active_sales.iterrows():
        try:
            items = json.loads(row['items_json'])
            for pid in items:
                cogs += prod_cp_map.get(pid, 0)
        except: continue
        
    turnover_ratio = (cogs / current_inv_val) if current_inv_val > 0 else 0
    
    return {
        "inventory_turnover_ratio": round(turnover_ratio, 2),
        "inventory_valuation": current_inv_val,
        "cogs": cogs
    }

def backup_system():
    if not os.path.exists("backups"): os.makedirs("backups")
    fname = f"backups/inventory_backup_{int(time.time())}.db"
    try:
        shutil.copy("inventory_system.db", fname)
        return fname
    except Exception as e:
        return None

class PDFReceipt(FPDF):
    def __init__(self, store_name, logo_path=None):
        super().__init__()
        self.store_name = store_name
        self.logo_path = logo_path

    def header(self):
        if self.logo_path and os.path.exists(self.logo_path):
            try:
                self.image(self.logo_path, 10, 8, 25)
                self.set_xy(40, 10)
            except: pass
        
        self.set_font('Arial', 'B', 15)
        self.cell(0, 10, self.store_name, 0, 1, 'C')
        self.set_font('Arial', '', 9)
        self.cell(0, 5, 'Retail & POS System', 0, 1, 'C')
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

def generate_receipt_pdf(store_name, txn_id, time_str, items, total, operator, mode, pos, customer=None, tax_info=None):
    logo_path = "logo.png" if os.path.exists("logo.png") else None
    
    pdf = PDFReceipt(store_name, logo_path)
    pdf.add_page()
    
    pdf.set_font("Arial", size=10)
    
    pdf.cell(100, 6, f"Receipt No: #{txn_id}", 0, 0)
    pdf.cell(0, 6, f"Date: {time_str}", 0, 1, 'R')
    pdf.cell(100, 6, f"Cashier: {operator}", 0, 0)
    pdf.cell(0, 6, f"POS: {pos}", 0, 1, 'R')
    pdf.cell(100, 6, f"Payment Mode: {mode}", 0, 1, 'L')
    
    if customer:
        pdf.ln(5)
        pdf.set_font("Arial", 'B', 10)
        pdf.cell(0, 6, "Customer Details:", 0, 1, 'L')
        pdf.set_font("Arial", '', 10)
        pdf.cell(0, 5, f"Name: {customer.get('name', 'N/A')}", 0, 1)
        pdf.cell(0, 5, f"Mobile: {customer.get('mobile', 'N/A')}", 0, 1)
        if customer.get('loyalty_points'):
            pdf.cell(0, 5, f"Loyalty Balance: {customer.get('loyalty_points')} Pts", 0, 1)

    pdf.ln(5)
    
    pdf.set_fill_color(220, 220, 220)
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(100, 8, "Item", 1, 0, 'L', True)
    pdf.cell(30, 8, "Price", 1, 0, 'C', True)
    pdf.cell(20, 8, "Qty", 1, 0, 'C', True)
    pdf.cell(40, 8, "Total", 1, 1, 'R', True)
    
    pdf.set_font("Arial", '', 10)
    item_summary = {}
    for i in items:
        if i['name'] in item_summary:
            item_summary[i['name']]['qty'] += 1
            item_summary[i['name']]['total'] += i['price']
        else:
            item_summary[i['name']] = {'price': i['price'], 'qty': 1, 'total': i['price']}
            
    for name, data in item_summary.items():
        sanitized_name = name.encode('latin-1', 'replace').decode('latin-1')
        pdf.cell(100, 7, sanitized_name, 1)
        pdf.cell(30, 7, f"{data['price']:.2f}", 1, 0, 'C')
        pdf.cell(20, 7, str(data['qty']), 1, 0, 'C')
        pdf.cell(40, 7, f"{data['total']:.2f}", 1, 1, 'R')
        
    pdf.ln(5)
    pdf.set_font("Arial", '', 10)
    
    subtotal = total
    if tax_info and tax_info.get('tax_amount', 0) > 0:
        pdf.cell(150, 6, f"GST ({tax_info['tax_percent']}%)", 0, 0, 'R')
        pdf.cell(40, 6, f"{tax_info['tax_amount']:.2f}", 1, 1, 'R')

    pdf.set_font("Arial", 'B', 12)
    pdf.cell(150, 8, "NET TOTAL", 0, 0, 'R')
    pdf.cell(40, 8, f"Rs {total:.2f}", 1, 1, 'R')
    
    pdf.set_font("Arial", '', 9)
    pdf.ln(10)
    pdf.cell(0, 5, f"Payment Mode: {mode}", 0, 1, 'L')
    pdf.cell(0, 5, "Terms: Non-refundable. Goods once sold cannot be returned.", 0, 1, 'C')
    
    return pdf.output(dest='S').encode('latin-1')

def generate_upi_qr(vpa, name, amount, note):
    if not name: name = "Merchant"
    
    params = {
        "pa": vpa, 
        "pn": name, 
        "am": f"{amount:.2f}", 
        "cu": "INR", 
        "tn": note,
        "mc": "0000", 
        "mode": "02", 
        "orgid": "000000" 
    }
    url = f"upi://pay?{urllib.parse.urlencode(params)}"
    qr = qrcode.QRCode(box_size=10, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf)
    return buf.getvalue()

def validate_card(number, expiry, cvv):
    if not number.isdigit() or not (13 <= len(number) <= 19):
        return False, "Invalid Card Number Length (13-19 digits required)"
    
    if not cvv.isdigit() or not (3 <= len(cvv) <= 4):
        return False, "Invalid CVV (3-4 digits required)"
    
    try:
        if "/" not in expiry: return False, "Invalid Expiry Format (Use MM/YY)"
        exp_m, exp_y = map(int, expiry.split('/'))
        if not (1 <= exp_m <= 12): return False, "Invalid Month"
        current_year = int(datetime.now().strftime("%y"))
        if exp_y < current_year: return False, "Card Expired"
    except:
        return False, "Invalid Expiry Date"

    digits = [int(d) for d in number]
    checksum = digits.pop()
    digits.reverse()
    doubled = []
    for i, d in enumerate(digits):
        if i % 2 == 0:
            d *= 2
            if d > 9: d -= 9
        doubled.append(d)
    total = sum(doubled) + checksum
    
    if total % 10 == 0:
        return True, "Valid"
    else:
        return False, "Invalid Card Number (Luhn Check Failed)"
