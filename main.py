import streamlit as st
import pandas as pd
import json
import time
import random
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime
import os

# Internal modules
import database as db
import utils
import styles

# --- APP CONFIGURATION ---
st.set_page_config(
    page_title="SmartInventory ERP", 
    layout="wide", 
    page_icon="🏢",
    initial_sidebar_state="expanded"
)

# UI/UX ADDITION: Theme Management
if 'theme' not in st.session_state:
    st.session_state['theme'] = 'dark'

styles.load_css(st.session_state['theme'])

# --- INITIALIZATION ---
if 'initialized' not in st.session_state:
    db.init_db()
    db.seed_advanced_demo_data() # Updated to use advanced seeding
    st.session_state['initialized'] = True
    st.session_state['cart'] = []
    st.session_state['user'] = None
    st.session_state['role'] = None
    st.session_state['full_name'] = None
    st.session_state['pos_id'] = None
    st.session_state['checkout_stage'] = 'cart'
    st.session_state['txn_start_time'] = None
    st.session_state['qr_expiry'] = None
    st.session_state['selected_payment_mode'] = None
    st.session_state['undo_stack'] = []
    # Feature #1: Customer Session
    st.session_state['current_customer'] = None
    st.session_state['bill_mode'] = None
    # Feature 2: Coupons
    st.session_state['applied_coupon'] = None
    st.session_state['points_to_redeem'] = 0

# Load Configs
currency = db.get_setting("currency_symbol")
store_name = db.get_setting("store_name")

# --- HELPER FUNCTIONS ---
def refresh_trie():
    conn = db.get_connection()
    df = pd.read_sql("SELECT * FROM products", conn)
    conn.close()
    t = utils.Trie()
    for _, row in df.iterrows():
        t.insert(row['name'], row.to_dict())
    return t, df

# Cache Trie for performance
if 'product_trie' not in st.session_state:
    trie, df_p = refresh_trie()
    st.session_state['product_trie'] = trie
    st.session_state['df_products'] = df_p

# --- AUTHENTICATION MODULE ---
def login_view():
    # UI/UX ADDITION: Centered Container Layout
    c_left, c_center, c_right = st.columns([1, 2, 1])
    
    with c_center:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown(f"""
        <div style="text-align: center; margin-bottom: 30px;">
            <div style="font-size: 4rem; margin-bottom: 10px;">💠</div>
            <h1 style="margin-bottom: 0; font-size: 2.5rem;">{store_name}</h1>
            <p style="opacity: 0.6; font-size: 1.1rem; letter-spacing: 1px;">NEXT-GEN ERP & POS SYSTEM</p>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("<div class='login-box' style='margin: 0 auto;'>", unsafe_allow_html=True)
        st.subheader("🔐 Secure Access")
        
        # Get terminals for dropdown
        terminals = db.get_all_terminals()
        active_ids = [t['id'] for _, t in terminals.iterrows() if t['status'] == 'Active']
        if "Office Dashboard" not in active_ids: active_ids.append("Office Dashboard")
        
        with st.form("login_frm"):
            user_in = st.text_input("Username", placeholder="e.g. ammar_admin").strip().lower()
            pass_in = st.text_input("Password", type="password", placeholder="••••••••")
            term_in = st.selectbox("Select Terminal", active_ids)
            
            st.markdown("<br>", unsafe_allow_html=True)
            submit = st.form_submit_button("🚀 Access System", type="primary", use_container_width=True)
            
            if submit:
                # 1. Validation
                if not user_in or not pass_in:
                    st.error("Fields cannot be empty")
                    return
                
                # Check User Status (Feature 1)
                try:
                    u_status = db.get_user_status(user_in)
                    if u_status != "Active":
                        st.error(f"❌ Account is {u_status}. Contact Admin.")
                        return
                except AttributeError:
                    # Fail safe if db not updated
                    pass

                # Check Terminal Status
                t_status = db.check_terminal_status(term_in)
                if term_in != "Office Dashboard" and t_status != "Active":
                    st.error(f"⛔ Terminal {term_in} is {t_status}. Login blocked.")
                    return

                # 2. Concurrency Check
                occupied_by = db.is_pos_occupied(term_in)
                if occupied_by and occupied_by != user_in:
                    st.error(f"⛔ Terminal {term_in} is currently locked by '{occupied_by}'.")
                    st.warning("Ask Admin to force unlock if this is an error.")
                    return

                # 3. DB Check
                h = utils.generate_hash(pass_in)
                conn = db.get_connection()
                c = conn.cursor()
                c.execute("SELECT role, full_name FROM users WHERE username=? AND password_hash=?", (user_in, h))
                res = c.fetchone()
                conn.close()
                
                if res:
                    role, fname = res
                    db.lock_terminal(term_in, user_in, role)
                    
                    st.session_state['user'] = user_in
                    st.session_state['role'] = role
                    st.session_state['full_name'] = fname
                    st.session_state['pos_id'] = term_in
                    
                    db.log_activity(user_in, "Login", f"Accessed {term_in}")
                    st.success("Login Successful! Redirecting...")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error("❌ Invalid Username or Password")
        st.markdown("</div>", unsafe_allow_html=True)

        # Demo Credentials
        st.markdown("<br>", unsafe_allow_html=True)
        with st.expander("🔑 View Demo Credentials"):
            st.code("""
User: ammar_admin | Pass: admin123   (Admin)
User: manager_1   | Pass: manager123 (Manager)
User: pos_op_1    | Pass: pos123     (Operator)
            """, language="text")

def logout_user():
    user = st.session_state.get('user')
    if user:
        db.unlock_terminal(user)
        db.log_activity(user, "Logout", "Session Ended")
    
    st.session_state.clear()
    st.session_state['theme'] = 'dark' # Keep preference
    st.rerun()

# --- MODULES ---

def pos_interface():
    # --- POS HEADER & CAMPAIGNS ---
    st.markdown("<div class='card-container'>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([3, 1, 1])
    with c1:
        st.title(f"🛒 {st.session_state['pos_id']}")
        st.caption("Point of Sale Terminal • v2.0 • Live Connection")
    with c3:
        st.markdown(f"<div style='text-align:right'><b>{st.session_state['full_name']}</b><br><span style='font-size:0.8em;opacity:0.7'>Operator</span></div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)
        
    trie, df_p = refresh_trie()
    
    # FEATURE 8: FLASH SALE TIMER
    active_campaigns = db.get_active_campaigns()
    flash_sales = active_campaigns[active_campaigns['type'] == 'Flash Sale']
    if not flash_sales.empty:
        fs = flash_sales.iloc[0]
        end_time = datetime.strptime(fs['end_time'], "%Y-%m-%d %H:%M:%S")
        remaining = end_time - datetime.now()
        if remaining.total_seconds() > 0:
            mins, secs = divmod(int(remaining.total_seconds()), 60)
            hours, mins = divmod(mins, 60)
            st.warning(f"⚡ FLASH SALE ACTIVE: {fs['name']} ends in {hours:02}:{mins:02}:{secs:02}")
    
    # FEATURE 7: PERSONALIZED BANNER
    if st.session_state.get('current_customer'):
        rec_msg = utils.get_personalized_offer(st.session_state['current_customer'], df_p)
        st.info(rec_msg, icon="🎁")

    # --- STATE MACHINE: CART VIEW ---
    if st.session_state['checkout_stage'] == 'cart':
        # Feature #1: Customer Identification Panel
        with st.expander("👤 Customer Details (Required for Bill)", expanded=st.session_state['current_customer'] is None):
            col_c1, col_c2 = st.columns([2, 1])
            with col_c1:
                cust_phone = st.text_input("Customer Mobile", value=st.session_state['current_customer']['mobile'] if st.session_state['current_customer'] else "")
            with col_c2:
                st.write("")
                st.write("")
                if st.button("🔎 Search / Add"):
                    if cust_phone:
                        cust = db.get_customer(cust_phone)
                        if cust:
                            st.session_state['current_customer'] = cust
                            st.success(f"Welcome back, {cust['name']} ({cust['segment']} Member)")
                            st.caption(f"Loyalty Points: {cust['loyalty_points']}")
                        else:
                            st.session_state['temp_new_customer'] = cust_phone
                            st.warning("New Customer! Please enter details below.")
            
            if st.session_state.get('temp_new_customer') == cust_phone and not st.session_state['current_customer']:
                with st.form("new_cust_form"):
                    new_name = st.text_input("Full Name")
                    new_email = st.text_input("Email (Optional)")
                    if st.form_submit_button("Save Customer"):
                        if new_name:
                            db.upsert_customer(cust_phone, new_name, new_email)
                            st.session_state['current_customer'] = db.get_customer(cust_phone)
                            st.session_state.pop('temp_new_customer', None)
                            st.success("Customer Added!")
                            st.rerun()
                        else:
                            st.error("Name is required.")

        st.markdown("---")
        # FEATURE 6: QR SCAN INPUT
        col_scan, col_manual = st.columns([1, 2])
        with col_scan:
            st.markdown("##### 📷 Scan QR")
            qr_input = st.text_input("Scan Product QR (PROD:ID)", key="qr_scan_input", help="Simulate scanner input here")
            if qr_input:
                pid = utils.parse_qr_input(qr_input)
                if pid:
                    prod = db.get_product_by_id(pid)
                    if prod:
                        cart_qty = sum(1 for x in st.session_state['cart'] if x['id'] == pid)
                        if prod['stock'] > cart_qty:
                            st.session_state['cart'].append(prod)
                            st.toast(f"Scanned: {prod['name']}")
                        else:
                            st.error("Out of Stock!")
                    else:
                        st.error("Product Not Found")

        with col_manual:
            st.markdown("##### ⌨️ Manual Search")
            c_search, c_algo = st.columns([3, 1])
            with c_search:
                query = st.text_input("Search Product", key="pos_search")
            with c_algo:
                algo = st.selectbox("Search Algo", ["Trie (O(L))", "Linear (O(N))"])

        left_panel, right_panel = st.columns([2, 1])

        with left_panel:
            results = []
            if query:
                if algo.startswith("Trie"):
                    results = trie.search_prefix(query)
                else:
                    results = df_p[df_p['name'].str.contains(query, case=False)].to_dict('records')
            else:
                results = df_p.to_dict('records')
            
            page_size = 6
            if 'page' not in st.session_state: st.session_state.page = 0
            start_idx = st.session_state.page * page_size
            end_idx = start_idx + page_size
            visible_items = results[start_idx:end_idx]
            
            cols = st.columns(3)
            for i, item in enumerate(visible_items):
                with cols[i % 3]:
                    st.markdown(styles.product_card_html(item['name'], item['price'], item['stock'], item['category'], currency), unsafe_allow_html=True)
                    
                    cart_qty = sum(1 for x in st.session_state['cart'] if x['id'] == item['id'])
                    
                    if item['stock'] > cart_qty:
                        if st.button("Add ➕", key=f"add_{item['id']}"):
                            st.session_state['cart'].append(item)
                            st.toast(f"Added {item['name']}")
                            st.rerun()
                    else:
                        st.button("🚫 Out of Stock", disabled=True, key=f"no_{item['id']}")
            
            c_prev, c_next = st.columns([1,1])
            if c_prev.button("Previous") and st.session_state.page > 0:
                st.session_state.page -= 1
                st.rerun()
            if c_next.button("Next") and end_idx < len(results):
                st.session_state.page += 1
                st.rerun()

        with right_panel:
            st.markdown("<div class='card-container'>", unsafe_allow_html=True)
            st.markdown("### 🛍️ Cart Summary")
            if st.session_state['cart']:
                cart_df = pd.DataFrame(st.session_state['cart'])
                summary = cart_df.groupby('name').agg({'price': 'first', 'id': 'count'}).rename(columns={'id': 'Qty'})
                summary['Total'] = summary['price'] * summary['Qty']
                st.dataframe(summary[['Qty', 'Total']], use_container_width=True)
                
                raw_total = summary['Total'].sum()
                
                # FEATURE 2: COUPONS
                st.markdown("##### 🎟️ Coupons & Loyalty")
                c_code = st.text_input("Enter Coupon Code")
                if st.button("Apply Coupon"):
                    cpn, msg = db.get_coupon(c_code)
                    if cpn:
                        if raw_total >= cpn['min_bill']:
                            st.session_state['applied_coupon'] = cpn
                            st.success(f"Coupon Applied: {msg}")
                        else:
                            st.error(f"Min bill required: {cpn['min_bill']}")
                    else:
                        st.error(msg)
                
                # FEATURE 5: LOYALTY REDEMPTION
                cust = st.session_state.get('current_customer')
                if cust and cust['loyalty_points'] > 0:
                    use_points = st.checkbox(f"Redeem Points (Bal: {cust['loyalty_points']})")
                    if use_points:
                        # 1 pt = 1 Rs (Simplification)
                        max_redeem = min(cust['loyalty_points'], int(raw_total))
                        st.session_state['points_to_redeem'] = max_redeem
                    else:
                        st.session_state['points_to_redeem'] = 0
                else:
                    st.session_state['points_to_redeem'] = 0

                # Calc Totals
                discount = 0
                if st.session_state.get('applied_coupon'):
                    cp = st.session_state['applied_coupon']
                    if cp['type'] == 'Flat': discount = cp['value']
                    elif cp['type'] == '%': discount = raw_total * (cp['value']/100)
                
                # Campaign Discount (Auto)
                fest_disc = 0
                fest_sales = active_campaigns[active_campaigns['type'] == 'Festival Offer']
                if not fest_sales.empty:
                    # Simple flat discount for demo of festival
                    fest_disc = raw_total * 0.05
                    st.caption(f"🎉 Festival Offer Applied (-{currency}{fest_disc:.2f})")

                total_after_disc = raw_total - discount - fest_disc - st.session_state['points_to_redeem']
                
                # Tax
                gst_enabled = db.get_setting("gst_enabled") == 'True'
                tax_amount = 0.0
                if gst_enabled:
                    tax_rate = float(db.get_setting("tax_rate"))
                    tax_amount = total_after_disc * (tax_rate / 100)
                    st.write(f"GST ({tax_rate}%): {currency}{tax_amount:,.2f}")
                
                final_total = total_after_disc + tax_amount
                
                st.markdown(f"""
                <div style='background:var(--secondary-bg); padding:10px; border-radius:8px; margin-top:10px;'>
                    <div style='display:flex; justify-content:space-between'><span>Subtotal:</span><span>{currency}{raw_total:.2f}</span></div>
                    <div style='display:flex; justify-content:space-between; color:var(--success-color)'><span>Discount:</span><span>-{currency}{discount+fest_disc:.2f}</span></div>
                    <div style='display:flex; justify-content:space-between; font-weight:bold; font-size:1.2em; margin-top:5px; border-top:1px solid var(--border-color); padding-top:5px;'>
                        <span>Total:</span><span>{currency}{final_total:,.2f}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                c_clear, c_pay = st.columns(2)
                if c_clear.button("🗑️ Clear Cart", use_container_width=True):
                    st.session_state['cart'] = []
                    st.session_state['applied_coupon'] = None
                    st.session_state['points_to_redeem'] = 0
                    st.rerun()
                if c_pay.button("💳 Proceed to Pay", type="primary", use_container_width=True):
                    if not st.session_state['current_customer']:
                        st.error("Please add Customer Details first!")
                    else:
                        st.session_state['final_calc'] = {
                            "total": final_total, 
                            "tax": tax_amount, 
                            "discount": discount + fest_disc,
                            "points": st.session_state['points_to_redeem']
                        }
                        st.session_state['checkout_stage'] = 'payment_method'
                        st.rerun()
            else:
                st.info("Cart is empty")
                st.button("Proceed to Pay", disabled=True)
            st.markdown("</div>", unsafe_allow_html=True)

    # --- STATE MACHINE: PAYMENT METHOD SELECTION ---
    elif st.session_state['checkout_stage'] == 'payment_method':
        st.markdown("<div class='card-container'>", unsafe_allow_html=True)
        st.button("⬅ Back to Cart", on_click=lambda: st.session_state.update({'checkout_stage': 'cart'}))
        
        st.markdown("<h2 style='text-align: center;'>Select Payment Method</h2>", unsafe_allow_html=True)
        
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("#### 💵 Cash")
            if st.button("Select Cash", use_container_width=True):
                st.session_state['selected_payment_mode'] = 'Cash'
                st.session_state['checkout_stage'] = 'payment_process'
                st.rerun()
        with c2:
            st.markdown("#### 📱 UPI / QR")
            if st.button("Select UPI", use_container_width=True):
                st.session_state['selected_payment_mode'] = 'UPI'
                st.session_state['checkout_stage'] = 'payment_process'
                st.session_state['qr_expiry'] = None # Reset Timer
                st.rerun()
        with c3:
            st.markdown("#### 💳 Card")
            if st.button("Select Card", use_container_width=True):
                st.session_state['selected_payment_mode'] = 'Card'
                st.session_state['checkout_stage'] = 'payment_process'
                st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    # --- STATE MACHINE: PAYMENT PROCESSING ---
    elif st.session_state['checkout_stage'] == 'payment_process':
        st.markdown("<div class='card-container'>", unsafe_allow_html=True)
        c_back, c_title = st.columns([1, 5])
        c_back.button("⬅ Cancel", on_click=lambda: st.session_state.update({'checkout_stage': 'payment_method'}))
        
        calc = st.session_state['final_calc']
        total = calc['total']
        mode = st.session_state['selected_payment_mode']
        
        st.subheader(f"Processing {mode} Payment - Amount: {currency}{total:,.2f}")
        
        # LOGIC FOR CASH
        if mode == 'Cash':
            tendered = st.number_input("Amount Received from Customer", min_value=0.0, step=10.0)
            if tendered > 0:
                change = tendered - total
                if change >= 0:
                    st.success(f"✅ Sufficient Amount. Change to return: {currency}{change:,.2f}")
                    if st.button("Confirm Cash Payment", type="primary"):
                        finalize_sale(total, "Cash")
                else:
                    st.error(f"❌ Insufficient Cash. Short by: {currency}{abs(change):,.2f}")
            else:
                st.info("Enter amount received to calculate change.")

        # LOGIC FOR UPI
        elif mode == 'UPI':
            if st.session_state['qr_expiry'] is None:
                st.session_state['qr_expiry'] = time.time() + 240 # 4 mins
            
            remaining = int(st.session_state['qr_expiry'] - time.time())
            
            c_qr, c_info = st.columns([1, 1])
            with c_qr:
                upi_id = db.get_setting("upi_id")
                txn_ref = f"INV-{random.randint(1000,9999)}"
                qr_img = utils.generate_upi_qr(upi_id, store_name, total, txn_ref)
                st.image(qr_img, width=250, caption=f"Scan to Pay: {currency}{total:.2f}")
            
            with c_info:
                if remaining > 0:
                    mins, secs = divmod(remaining, 60)
                    style_cls = "timer-box-alert" if remaining < 30 else "timer-box-normal"
                    st.markdown(f"<div class='{style_cls}'>Expires in: {mins:02d}:{secs:02d}</div>", unsafe_allow_html=True)
                    
                    st.markdown("### Verification (Demo)")
                    upi_ref = st.text_input("Enter UPI Transaction ID (UT / Ref No)")
                    if st.button("Verify & Print Bill"):
                        if len(upi_ref) > 6:
                            finalize_sale(total, "UPI")
                        else:
                            st.error("Invalid Transaction ID")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("⏰ QR Code Expired")
                    if st.button("🔄 Regenerate"):
                        st.session_state['qr_expiry'] = None
                        st.rerun()

        # LOGIC FOR CARD
        elif mode == 'Card':
            st.info("💳 Card Payment Simulation")
            col_cc1, col_cc2 = st.columns(2)
            with col_cc1:
                st.text_input("Card Holder Name")
                st.text_input("Card Number (Last 4 digits)", max_chars=4)
            with col_cc2:
                st.text_input("Expiry (MM/YY)")
                st.text_input("CVV", type="password", max_chars=3)
            
            if st.button("Process Transaction"):
                with st.spinner("Contacting Bank Gateway..."):
                    time.sleep(2.5) # Artificial Delay
                    finalize_sale(total, "Card")
        st.markdown("</div>", unsafe_allow_html=True)

    # --- STATE MACHINE: RECEIPT ---
    elif st.session_state['checkout_stage'] == 'receipt':
        st.markdown(utils.get_sound_html('success'), unsafe_allow_html=True)
        st.markdown("<div class='card-container' style='text-align:center'>", unsafe_allow_html=True)
        st.title("✅ Payment Successful")
        st.caption("Transaction has been recorded.")
        
        c_rec1, c_rec2 = st.columns(2)
        with c_rec1:
            if 'last_receipt' in st.session_state:
                st.download_button("📥 Download Receipt PDF", st.session_state['last_receipt'], "receipt.pdf", "application/pdf", use_container_width=True)
        
        with c_rec2:
            if st.button("🛒 Start New Sale", type="primary", use_container_width=True):
                st.session_state['cart'] = []
                st.session_state['current_customer'] = None
                st.session_state['checkout_stage'] = 'cart'
                st.session_state['applied_coupon'] = None
                st.session_state['points_to_redeem'] = 0
                st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

def finalize_sale(total, mode):
    calc = st.session_state['final_calc']
    
    # Gather Data
    txn_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    operator = st.session_state['full_name']
    customer = st.session_state['current_customer']
    customer_mobile = customer['mobile'] if customer else None
    
    # Calculate Points Earned
    points_earned = 0
    if customer:
        points_earned = utils.calculate_loyalty_points(total)
    
    # Generate Hash
    items_json = json.dumps([i['id'] for i in st.session_state['cart']])
    integrity_hash = utils.generate_integrity_hash((txn_time, total, items_json, operator))
    
    coupon_code = st.session_state['applied_coupon']['code'] if st.session_state.get('applied_coupon') else None
    
    # EXECUTE ATOMIC TRANSACTION (Resolves Locking)
    try:
        sale_id = db.process_sale_transaction(
            st.session_state['cart'],
            total,
            mode,
            operator,
            st.session_state['pos_id'],
            customer_mobile,
            calc['tax'],
            calc['discount'],
            coupon_code,
            calc['points'],
            points_earned,
            integrity_hash,
            30 # Estimated Time Taken
        )
        
        st.session_state['undo_stack'].append(sale_id)
        
        tax_info = {"tax_amount": calc['tax'], "tax_percent": 18}
        pdf = utils.generate_receipt_pdf(store_name, sale_id, datetime.now().strftime("%Y-%m-%d %H:%M"), st.session_state['cart'], total, st.session_state['full_name'], mode, st.session_state['pos_id'], customer, tax_info)
        
        st.session_state['last_receipt'] = pdf
        st.session_state['checkout_stage'] = 'receipt'
        st.session_state['qr_expiry'] = None
        st.rerun()
        
    except Exception as e:
        st.error(f"Transaction Failed: {str(e)}")

def inventory_manager():
    st.title("📦 Master Inventory Management")
    # PRESERVING ORIGINAL 6 TABS
    tab_view, tab_add, tab_restock, tab_reqs, tab_metrics, tab_abc = st.tabs(["View & Edit", "Add New Product", "➕ Restock (Manual/QR)", "📋 Stock Requests", "Stock Metrics", "ABC Analysis"])
    
    conn = db.get_connection()
    df = pd.read_sql("SELECT * FROM products", conn)
    conn.close()
    
    with tab_view:
        st.markdown("<div class='card-container'>", unsafe_allow_html=True)
        st.markdown("### Product Database")
        col_f1, col_f2 = st.columns(2)
        cat_filter = col_f1.selectbox("Filter Category", ["All"] + db.get_categories_list())
        search_txt = col_f2.text_input("Search Name")
        df_filtered = df
        if cat_filter != "All": df_filtered = df[df['category'] == cat_filter]
        if search_txt: df_filtered = df_filtered[df_filtered['name'].str.contains(search_txt, case=False)]
        st.dataframe(df_filtered[['id', 'name', 'category', 'price', 'stock']], use_container_width=True)
        st.markdown("##### Generate QR Code for Product")
        sel_prod_id = st.number_input("Enter Product ID to Generate QR", min_value=1, step=1)
        if st.button("Generate QR"):
            p_data = db.get_product_by_id(sel_prod_id)
            if p_data:
                qr_bytes = utils.generate_product_qr_image(p_data['id'], p_data['name'])
                st.image(qr_bytes, caption=f"QR for {p_data['name']}")
            else:
                st.error("Product ID not found")
        st.markdown("</div>", unsafe_allow_html=True)

    with tab_add:
        st.markdown("<div class='card-container'>", unsafe_allow_html=True)
        with st.form("new_prod"):
            n = st.text_input("Product Name")
            c = st.selectbox("Category", db.get_categories_list())
            p = st.number_input("Selling Price", min_value=0.0)
            cp = st.number_input("Cost Price", min_value=0.0)
            s = st.number_input("Initial Stock", min_value=0)
            if st.form_submit_button("Add Product"):
                if db.add_product(n, c, p, s, cp):
                    st.success(f"Added {n}")
                    st.rerun()
                else: st.error("Error adding product")
        st.markdown("</div>", unsafe_allow_html=True)
                    
    with tab_restock:
        st.markdown("<div class='card-container'>", unsafe_allow_html=True)
        col_qr_re, col_man_re = st.columns(2)
        with col_qr_re:
            re_qr = st.text_input("Scan QR (PROD:ID)", key="restock_qr")
            if re_qr:
                pid = utils.parse_qr_input(re_qr)
                if pid: st.session_state['restock_selected_id'] = pid
        with col_man_re:
            if not df.empty:
                prod_opts = {f"{row['name']} (ID: {row['id']})": row['id'] for idx, row in df.iterrows()}
                sel = st.selectbox("Select Product", list(prod_opts.keys()))
                if sel: st.session_state['restock_selected_id'] = prod_opts[sel]
        if 'restock_selected_id' in st.session_state:
            pid = st.session_state['restock_selected_id']
            p_curr = db.get_product_by_id(pid)
            if p_curr:
                st.divider()
                st.write(f"**Selected:** {p_curr['name']} | **Current Stock:** {p_curr['stock']}")
                qty = st.number_input("Add Quantity", min_value=1, value=10)
                if st.button("Confirm Restock"):
                    db.restock_product(pid, qty)
                    st.success("Stock Updated!")
                    time.sleep(1)
                    st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    with tab_reqs:
        st.markdown("<div class='card-container'>", unsafe_allow_html=True)
        with st.form("req_form"):
            r_pid = st.number_input("Product ID", min_value=1)
            r_qty = st.number_input("Required Qty", min_value=1)
            r_note = st.text_input("Reason / Notes")
            if st.form_submit_button("Submit Request"):
                prod = db.get_product_by_id(r_pid)
                if prod:
                    db.create_stock_request(r_pid, prod['name'], r_qty, r_note, st.session_state['user'])
                    st.success("Request Submitted")
                else: st.error("Invalid Product ID")
        st.divider()
        st.dataframe(db.get_stock_requests(), use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with tab_metrics:
        st.markdown("<div class='card-container'>", unsafe_allow_html=True)
        sales_df = db.get_sales_data()
        metrics_df = utils.calculate_inventory_metrics(sales_df, df)
        st.dataframe(metrics_df, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)
        
    with tab_abc:
        st.markdown("<div class='card-container'>", unsafe_allow_html=True)
        abc_df = utils.calculate_abc_analysis(df)
        st.dataframe(abc_df[['name', 'stock', 'inventory_value', 'abc_class']], use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

def analytics_dashboard():
    st.title("📈 Enterprise Analytics")
    df_sales = db.get_sales_data()
    try:
        df_sales['date'] = pd.to_datetime(df_sales['timestamp'], format='mixed', dayfirst=False, errors='coerce')
        df_sales = df_sales.dropna(subset=['date'])
    except:
        st.error("Date parsing failed. Check DB format.")
        return
    total_rev = df_sales['total_amount'].sum()
    total_txns = len(df_sales)
    
    # UI/UX ADDITION: Styled KPI Cards
    m1, m2, m3 = st.columns(3)
    with m1: st.markdown(f"<div class='kpi-card'><div class='kpi-title'>Total Revenue</div><div class='kpi-value'>{currency}{total_rev:,.0f}</div></div>", unsafe_allow_html=True)
    with m2: st.markdown(f"<div class='kpi-card'><div class='kpi-title'>Transactions</div><div class='kpi-value'>{total_txns}</div></div>", unsafe_allow_html=True)
    with m3: st.markdown(f"<div class='kpi-card'><div class='kpi-title'>Avg Order Value</div><div class='kpi-value'>{currency}{total_rev/total_txns:.0f}</div></div>", unsafe_allow_html=True)

    # PRESERVING ALL 6 ANALYTICS TABS
    t1, t2, t3, t4, t5, t6 = st.tabs(["Sales Trends", "Staff Performance", "Demand Forecast", "Algorithm Showcase", "🏆 Rankings", "📊 Category Analysis"])
    with t1:
        st.markdown("<div class='card-container'>", unsafe_allow_html=True)
        daily = df_sales.groupby(df_sales['date'].dt.date)['total_amount'].sum().reset_index()
        trend_dir = utils.analyze_trend_slope(daily['total_amount'].values)
        st.info(f"Market Trend (Algo #32): {trend_dir}")
        st.line_chart(daily.set_index('date')['total_amount'])
        st.markdown("</div>", unsafe_allow_html=True)
    with t2:
        st.markdown("<div class='card-container'>", unsafe_allow_html=True)
        staff_stats = df_sales.groupby('operator').agg({'total_amount':'sum', 'id':'count', 'time_taken': 'mean'}).reset_index()
        staff_stats.columns = ['Name', 'Revenue', 'Sales Count', 'Avg Time (s)']
        staff_stats['Performance Score'] = (staff_stats['Revenue'] * 0.01) + (staff_stats['Sales Count'] * 10) - (staff_stats['Avg Time (s)'] * 0.5)
        staff_stats = staff_stats.sort_values('Performance Score', ascending=False)
        st.dataframe(staff_stats, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)
    with t3:
        st.markdown("<div class='card-container'>", unsafe_allow_html=True)
        if not df_sales.empty:
            daily = df_sales.groupby(df_sales['date'].dt.date)['total_amount'].sum().reset_index()
            daily_vals = daily['total_amount'].values
            prediction = utils.forecast_next_period(daily_vals)
            c1, c2 = st.columns(2)
            c1.metric("Predicted Next Day Sales", f"{currency}{prediction:.2f}")
            c2.info("Algorithm: Weighted Moving Average (Window=5)")
            if len(daily) > 2:
                hist_dates = [str(d) for d in daily['date']]
                hist_vals = list(daily['total_amount'])
                hist_dates.append("FORECAST")
                hist_vals.append(prediction)
                chart_data = pd.DataFrame({"Sales": hist_vals}, index=hist_dates)
                st.bar_chart(chart_data)
        else: st.info("Insufficient data for forecasting.")
        st.markdown("</div>", unsafe_allow_html=True)
    with t4:
        st.markdown("<div class='card-container'>", unsafe_allow_html=True)
        col_algo1, col_algo2 = st.columns(2)
        with col_algo1:
            conn = db.get_connection()
            all_prods = pd.read_sql("SELECT * FROM products", conn).to_dict('records')
            conn.close()
            search_key = "id"
            target_val = all_prods[-1]['id'] if all_prods else 0
            t0 = time.perf_counter()
            utils.linear_search(all_prods, search_key, target_val)
            t_linear = (time.perf_counter() - t0) * 1000
            t0 = time.perf_counter()
            sorted_prods = sorted(all_prods, key=lambda x: x[search_key])
            utils.binary_search(sorted_prods, search_key, target_val)
            t_binary = (time.perf_counter() - t0) * 1000
            bench_df = pd.DataFrame({
                "Algorithm": ["Linear Search O(n)", "Binary Search O(log n)"],
                "Time (ms)": [t_linear, t_binary],
                "Data Size": [len(all_prods), len(all_prods)]
            })
            st.table(bench_df)
        with col_algo2:
            conn = db.get_connection()
            df_p = pd.read_sql("SELECT * FROM products", conn)
            conn.close()
            rank_df = utils.rank_products(df_sales, df_p)
            if not rank_df.empty: st.dataframe(rank_df[['rank', 'name', 'qty_sold', 'score']], hide_index=True)
            else: st.info("No sales data for ranking.")
        st.markdown("</div>", unsafe_allow_html=True)
    with t5:
        st.markdown("<div class='card-container'>", unsafe_allow_html=True)
        st.subheader("🥇 Top Performers (Rankings)")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("#### 🏆 Best POS Operators")
            staff_rank = df_sales.groupby('operator')['total_amount'].sum().reset_index().sort_values('total_amount', ascending=False)
            st.dataframe(staff_rank.style.highlight_max(axis=0), use_container_width=True)
        with c2:
            st.markdown("#### ⚡ Fastest Checkouts")
            fast_op = df_sales.groupby('operator')['time_taken'].mean().reset_index().sort_values('time_taken')
            st.dataframe(fast_op, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)
    with t6:
        st.markdown("<div class='card-container'>", unsafe_allow_html=True)
        st.subheader("📊 Category Performance Analysis")
        cat_perf = db.get_category_performance()
        if not cat_perf.empty:
            c1, c2 = st.columns([2, 1])
            with c1:
                st.bar_chart(cat_perf.set_index('Category'))
            with c2:
                st.dataframe(cat_perf, use_container_width=True)
        else:
            st.info("No category data available yet.")
        st.markdown("</div>", unsafe_allow_html=True)

def admin_panel():
    st.title("🛡️ Admin Console")
    # PRESERVING ALL 10 ADMIN TABS
    tab_dash, tab_cats, tab_settings, tab_cust, tab_term, tab_users, tab_req_app, tab_market, tab_txns, tab_logs = st.tabs(["Controls", "Category", "⚙️ Settings", "👥 Customers", "🖥️ Terminals", "👤 Users", "📝 Stock Reqs", "🚀 Marketing", "📜 Transactions", "📝 Logs"])
    
    with tab_dash:
        st.markdown("<div class='card-container'>", unsafe_allow_html=True)
        if st.button("🔓 Force Unlock All Terminals"):
            db.force_clear_all_sessions()
            st.success("All session locks cleared.")
        st.markdown("---")
        if st.session_state['undo_stack']:
            last_sale_id = st.session_state['undo_stack'][-1]
            st.warning(f"Ready to undo Sale ID: #{last_sale_id}")
            if st.button("Undo Last Sale"):
                st.session_state['undo_stack'].pop()
                st.success(f"Sale #{last_sale_id} rolled back! (Simulation)")
        else: st.info("No recent transactions to undo.")
        st.markdown("---")
        if st.button("Create System Backup (Algo #28)"):
            path = utils.backup_system()
            if path: st.success(f"Backup: {path}")
        st.markdown("</div>", unsafe_allow_html=True)

    with tab_cats:
        st.markdown("<div class='card-container'>", unsafe_allow_html=True)
        new_cat = st.text_input("New Category Name")
        if st.button("Add Category"):
            if db.add_category(new_cat): st.success("Category Added")
            else: st.error("Failed")
        st.markdown("</div>", unsafe_allow_html=True)

    with tab_settings:
        st.markdown("<div class='card-container'>", unsafe_allow_html=True)
        with st.form("settings_form"):
            s_name = st.text_input("Store Name", value=db.get_setting("store_name"))
            s_upi = st.text_input("UPI ID (for QR)", value=db.get_setting("upi_id"))
            col_s1, col_s2 = st.columns(2)
            with col_s1: s_tax = st.number_input("GST Percentage (%)", value=float(db.get_setting("tax_rate")))
            with col_s2: s_gst_enable = st.checkbox("Enable GST Billing", value=(db.get_setting("gst_enabled") == 'True'))
            s_mode = st.selectbox("Default Bill Mode", ["GST Bill", "Non-GST Bill"], index=0 if db.get_setting("default_bill_mode") == "GST Bill" else 1)
            uploaded_logo = st.file_uploader("Store Logo (PNG/JPG)", type=['png', 'jpg', 'jpeg'])
            if st.form_submit_button("Save Settings"):
                db.set_setting("store_name", s_name)
                db.set_setting("upi_id", s_upi)
                db.set_setting("tax_rate", str(s_tax))
                db.set_setting("gst_enabled", str(s_gst_enable))
                db.set_setting("default_bill_mode", s_mode)
                if uploaded_logo:
                    with open("logo.png", "wb") as f: f.write(uploaded_logo.getbuffer())
                st.success("Settings Saved!")
                time.sleep(1)
                st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    with tab_cust:
        st.markdown("<div class='card-container'>", unsafe_allow_html=True)
        cust_df = db.get_all_customers()
        st.dataframe(cust_df, use_container_width=True)
        if not cust_df.empty:
            c1, c2 = st.columns(2)
            c1.metric("Total Customers", len(cust_df))
            c2.metric("Total Customer Spend", f"{currency}{cust_df['total_spend'].sum():,.2f}")
        st.markdown("</div>", unsafe_allow_html=True)

    with tab_term:
        st.markdown("<div class='card-container'>", unsafe_allow_html=True)
        with st.expander("Add New Terminal"):
            with st.form("add_term"):
                nt_id = st.text_input("Terminal ID (e.g., POS-3)")
                nt_name = st.text_input("Name (e.g., Upstairs)")
                nt_loc = st.text_input("Location")
                if st.form_submit_button("Create Terminal"):
                    if db.add_terminal(nt_id, nt_name, nt_loc): st.success("Terminal Added"); st.rerun()
                    else: st.error("Error creating terminal")
        terms = db.get_all_terminals()
        for _, t in terms.iterrows():
            with st.container():
                c1, c2, c3 = st.columns([3, 1, 1])
                c1.write(f"**{t['name']}** ({t['id']}) - {t['location']}")
                new_status = c2.selectbox("Status", ["Active", "Maintenance", "Error"], index=["Active", "Maintenance", "Error"].index(t['status']), key=f"status_{t['id']}")
                if new_status != t['status']:
                    db.update_terminal_status(t['id'], new_status)
                    st.toast("Status Updated")
                    time.sleep(0.5)
                    st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    with tab_users:
        st.markdown("<div class='card-container'>", unsafe_allow_html=True)
        with st.expander("Create New User"):
            with st.form("new_user_form"):
                nu_user = st.text_input("Username")
                nu_pass = st.text_input("Password", type="password")
                nu_name = st.text_input("Full Name")
                nu_role = st.selectbox("Role", ["Operator", "Manager", "Inventory Manager"])
                if st.form_submit_button("Create User"):
                    if db.create_user(nu_user, nu_pass, nu_role, nu_name): st.success("User Created"); st.rerun()
                    else: st.error("Error")
        
        st.subheader("Manage User Status (Feature #1)")
        users = db.get_all_users()
        for _, u in users.iterrows():
            with st.container():
                c1, c2 = st.columns([4, 1])
                c1.write(f"**{u['username']}** ({u['role']}) - {u['status']}")
                
                # Prevent disabling self
                if u['username'] != st.session_state['user']:
                    new_stat = c2.selectbox("Status", ["Active", "Disabled"], index=0 if u['status'] == 'Active' else 1, key=f"u_stat_{u['username']}")
                    if new_stat != u['status']:
                        db.update_user_status(u['username'], new_stat)
                        st.toast(f"User {u['username']} updated to {new_stat}")
                        time.sleep(0.5)
                        st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    with tab_req_app:
        st.markdown("<div class='card-container'>", unsafe_allow_html=True)
        reqs = db.get_stock_requests()
        pending = reqs[reqs['status'] == 'Pending']
        if not pending.empty:
            for _, r in pending.iterrows():
                with st.expander(f"{r['product_name']} - Qty: {r['quantity']}"):
                    st.write(f"**Requested By:** {r['requested_by']}")
                    st.write(f"**Notes:** {r['notes']}")
                    c1, c2 = st.columns(2)
                    if c1.button("✅ Approve", key=f"app_{r['id']}"):
                        db.update_request_status(r['id'], "Approved"); st.success("Approved"); st.rerun()
                    if c2.button("❌ Reject", key=f"rej_{r['id']}"):
                        db.update_request_status(r['id'], "Rejected"); st.error("Rejected"); st.rerun()
        else: st.info("No Pending Requests")
        st.dataframe(reqs, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with tab_market:
        st.subheader("🚀 Retail Marketing Hub")
        st.markdown("<div class='card-container'>", unsafe_allow_html=True)
        
        # FEATURE 2: CREATE COUPON
        with st.expander("🎟️ Create Discount Coupon"):
            with st.form("new_coupon"):
                cc_code = st.text_input("Coupon Code (e.g., SUMMER10)")
                cc_type = st.selectbox("Type", ["Flat", "%"])
                cc_val = st.number_input("Value", min_value=1.0)
                cc_min = st.number_input("Min Bill Amount", min_value=0.0)
                cc_days = st.number_input("Validity (Days)", min_value=1, value=30)
                cc_lim = st.number_input("Total Usage Limit", min_value=1, value=100)
                if st.form_submit_button("Create Coupon"):
                    if db.create_coupon(cc_code, cc_type, cc_val, cc_min, cc_days, cc_lim):
                        st.success("Coupon Created!")
                    else:
                        st.error("Error creating coupon (Code might exist)")
        
        st.markdown("##### Active Coupons")
        st.dataframe(db.get_all_coupons(), use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)
        
        st.markdown("<div class='card-container'>", unsafe_allow_html=True)
        # FEATURE 4: LUCKY DRAW
        st.subheader("🎲 Lucky Draw System")
        c1, c2 = st.columns(2)
        with c1:
            ld_days = st.number_input("Sales Lookback (Days)", min_value=1, value=7)
        with c2:
            ld_min = st.number_input("Min Spend Eligibility", min_value=100, value=1000)
        
        if st.button("🎰 Run Lucky Draw"):
            winner = db.pick_lucky_winner(ld_days, ld_min)
            if winner:
                st.balloons()
                st.success(f"🎉 WINNER: {winner['name']} ({winner['mobile']})")
            else:
                st.warning("No eligible customers found for this criteria.")
        
        st.dataframe(db.get_lucky_draw_history(), use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("<div class='card-container'>", unsafe_allow_html=True)
        # FEATURE 3 & 8: CAMPAIGNS
        st.subheader("📢 Campaigns (Flash Sale / Festival)")
        with st.form("new_campaign"):
            cp_name = st.text_input("Campaign Name (e.g., Midnight Flash Sale)")
            cp_type = st.selectbox("Type", ["Flash Sale", "Festival Offer"])
            cp_start = st.text_input("Start Time (YYYY-MM-DD HH:MM:SS)", value=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            cp_end = st.text_input("End Time (YYYY-MM-DD HH:MM:SS)", value=(datetime.now() + pd.Timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S"))
            if st.form_submit_button("Launch Campaign"):
                db.create_campaign(cp_name, cp_type, cp_start, cp_end, {})
                st.success("Campaign Launched!")
        
        st.dataframe(db.get_active_campaigns(), use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with tab_txns:
        st.markdown("<div class='card-container'>", unsafe_allow_html=True)
        st.subheader("📜 Transaction History (Feature #4)")
        with st.expander("🔍 Search & Filters"):
            col_t1, col_t2, col_t3 = st.columns(3)
            f_bill = col_t1.number_input("Search Bill ID", min_value=0, value=0)
            f_op = col_t2.text_input("Filter by Operator")
            f_date = col_t3.text_input("Filter Date (YYYY-MM-DD)")
        
        filters = {}
        if f_bill > 0: filters['bill_no'] = f_bill
        if f_op: filters['operator'] = f_op
        if f_date: filters['date'] = f_date
        
        txns = db.get_transaction_history(filters)
        st.dataframe(txns, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)
        
    with tab_logs:
        st.markdown("<div class='card-container'>", unsafe_allow_html=True)
        st.subheader("📝 System Audit Logs (Feature #5)")
        logs = db.get_full_logs()
        st.dataframe(logs, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

def user_profile_page():
    st.title("👤 My Profile")
    st.markdown("<div class='card-container'>", unsafe_allow_html=True)
    with st.form("profile_upd"):
        new_name = st.text_input("Full Name", value=st.session_state['full_name'])
        if st.form_submit_button("Update Profile"):
            db.update_fullname(st.session_state['user'], new_name)
            st.session_state['full_name'] = new_name
            st.success("Updated")
    st.divider()
    st.subheader("Change Password")
    with st.form("pass_chg"):
        old_p = st.text_input("Old Password", type="password")
        new_p = st.text_input("New Password", type="password")
        if st.form_submit_button("Change Password"):
            if db.verify_password(st.session_state['user'], old_p):
                db.update_password(st.session_state['user'], new_p)
                st.success("Password Changed Successfully")
            else: st.error("Incorrect Old Password")
    st.markdown("</div>", unsafe_allow_html=True)

# --- MAIN CONTROLLER ---
def main():
    if not st.session_state.get('user'):
        login_view()
    else:
        with st.sidebar:
            # UI/UX ADDITION: Styled User Info
            st.markdown(f"""
            <div style="padding: 15px; background: rgba(255,255,255,0.05); border-radius: 12px; margin-bottom: 20px; border: 1px solid rgba(255,255,255,0.1);">
                <div style="font-size: 0.8rem; opacity: 0.7; letter-spacing: 1px;">CURRENT USER</div>
                <div style="font-weight: 600; font-size: 1.1rem; margin-top: 5px;">{st.session_state['user']}</div>
                <div style="font-size: 0.85rem; color: #6366f1; margin-top: 2px;">{st.session_state['role']}</div>
            </div>
            """, unsafe_allow_html=True)
            
            # Theme Toggle
            c_theme, c_lbl = st.columns([1, 4])
            with c_theme:
                is_dark = st.session_state['theme'] == 'dark'
                if st.checkbox("🌑", value=is_dark, label_visibility="collapsed"):
                    if st.session_state['theme'] != 'dark':
                        st.session_state['theme'] = 'dark'
                        st.rerun()
                elif st.session_state['theme'] == 'dark':
                     st.session_state['theme'] = 'light'
                     st.rerun()
            with c_lbl: st.caption("Dark Mode")

            st.markdown("---")
            
            # Navigation
            role = st.session_state['role']
            nav_opts = ["POS Terminal", "My Profile"]
            if role in ["Admin", "Manager"]: nav_opts = ["POS Terminal", "Inventory", "Analytics", "Admin Panel", "My Profile"]
            elif role == "Inventory Manager": nav_opts = ["Inventory", "My Profile"]
            
            choice = st.radio("Navigate", nav_opts, label_visibility="collapsed")
            
            st.markdown("---")
            if st.button("🚪 Log Out", use_container_width=True): logout_user()
        
        if choice == "POS Terminal": 
            if role == "Inventory Manager": st.error("Access Denied")
            else: pos_interface()
        elif choice == "Inventory": inventory_manager()
        elif choice == "Analytics": analytics_dashboard()
        elif choice == "Admin Panel": admin_panel()
        elif choice == "My Profile": user_profile_page()

if __name__ == "__main__":
    main()
