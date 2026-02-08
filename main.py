import streamlit as st
import pandas as pd
import json
import time
import random
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime, timedelta
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

if 'theme' not in st.session_state:
    st.session_state['theme'] = 'dark'

styles.load_css(st.session_state['theme'])

# --- INITIALIZATION ---
if 'initialized' not in st.session_state:
    db.init_db()
    db.seed_advanced_demo_data() 
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
    st.session_state['redo_stack'] = []
    st.session_state['current_customer'] = None
    st.session_state['bill_mode'] = None
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

if 'product_trie' not in st.session_state:
    trie, df_p = refresh_trie()
    st.session_state['product_trie'] = trie
    st.session_state['df_products'] = df_p

# --- DOCUMENTATION MODULE ---
def render_docs():
    st.title("📘 System Documentation & Developer Guide")
    st.markdown("---")
    
    st.markdown("""
    ### 1️⃣ Program Execution Flow
    - **Entry Point**: `main.py` is the controller script.
    - **Lifecycle**: Streamlit reruns the script on every interaction. State is preserved in `st.session_state`.
    - **Authentication**: Checks `st.session_state['user']`. If None, renders `login_view()`.
    
    ### 2️⃣ Database Schema (SQLite)
    - **products**: Inventory data (ID, name, stock, price).
    - **sales**: Transaction history (JSON items, total, timestamps).
    - **customers**: CRM data (mobile, spend, visits, segments).
    - **logs**: Audit trail for all system actions.
    
    ### 3️⃣ POS Workflow
    1. **Cart**: Add items via Search (Trie/Linear) or Barcode.
    2. **Checkout**: Apply Coupons -> Redeem Points -> Calculate Tax.
    3. **Payment**: Select Mode (Cash/UPI/Card) -> Verify.
    4. **Finalize**: Atomic transaction (Stock -1, Sales +1, Receipt Gen).
    
    ### 4️⃣ Roles & Access Control
    - **Admin**: Full access to settings, users, and logs.
    - **Manager**: Analytics, Inventory, and Cancellations.
    - **Operator**: POS Terminal only.
    
    ### 5️⃣ Analytics Logic
    - **CLV (Customer Lifetime Value)**: Aggregates total spend per customer to segment them (New, Regular, High-Value).
    - **Forecasting**: Uses Weighted Moving Average on daily sales.
    """)

# --- AUTHENTICATION MODULE ---
def login_view():
    c_left, c_center, c_right = st.columns([1, 2, 1])
    
    with c_left:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown("### 🖥️ POS Status")
        st.caption("Live Terminal Availability")
        
        # Use new status function to show real-time locks
        terminals = db.get_all_terminals_status()
        
        for index, row in terminals.iterrows():
            is_locked = pd.notna(row['current_user']) and row['current_user'] != ''
            
            if row['status'] == 'Active':
                if is_locked:
                    status_color = "#f59e0b" # Yellow
                    status_icon = "🔒"
                    status_text = f"In Use ({row['current_user']})"
                else:
                    status_color = "#10b981" # Green
                    status_icon = "🟢"
                    status_text = "Online"
            elif row['status'] == 'Maintenance':
                status_color = "#f59e0b" 
                status_icon = "🟡"
                status_text = "Maintenance"
            else:
                status_color = "#ef4444" 
                status_icon = "🔴"
                status_text = "Disabled"
            
            st.markdown(f"""
            <div style="background: rgba(255,255,255,0.05); border-radius: 8px; padding: 12px; margin-bottom: 10px; border-left: 4px solid {status_color};">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <span style="font-weight: 600; font-size: 0.95rem;">{row['name']}</span>
                    <span style="font-size: 0.8rem; opacity:0.7;">{row['id']}</span>
                </div>
                <div style="font-size: 0.85rem; margin-top: 5px; color: {status_color}; font-weight:500;">
                    {status_icon} {status_text}
                </div>
            </div>
            """, unsafe_allow_html=True)

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
        
        active_ids = [t['id'] for _, t in terminals.iterrows() if t['status'] == 'Active']
        if "Office Dashboard" not in active_ids: active_ids.append("Office Dashboard")
        
        with st.form("login_frm"):
            user_in = st.text_input("Username", placeholder="e.g. ammar_admin").strip().lower()
            pass_in = st.text_input("Password", type="password", placeholder="••••••••")
            term_in = st.selectbox("Select Terminal", active_ids)
            
            st.markdown("<br>", unsafe_allow_html=True)
            submit = st.form_submit_button("🚀 Access System", type="primary", use_container_width=True)
            
            if submit:
                if not user_in or not pass_in:
                    st.error("Fields cannot be empty")
                    return
                
                try:
                    u_status = db.get_user_status(user_in)
                    if u_status != "Active":
                        st.error(f"❌ Account is {u_status}. Contact Admin.")
                        return
                except AttributeError:
                    pass

                t_status = db.check_terminal_status(term_in)
                if term_in != "Office Dashboard" and t_status != "Active":
                    st.error(f"⛔ Terminal {term_in} is currently {t_status}. Access Blocked.")
                    return

                occupied_by = db.is_pos_occupied(term_in)
                if occupied_by and occupied_by != user_in:
                    st.error(f"⛔ Terminal {term_in} is currently locked by '{occupied_by}'.")
                    st.warning("Ask Admin to force unlock if this is an error.")
                    return

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
                    st.markdown(utils.get_sound_html('success'), unsafe_allow_html=True)
                    st.success("Login Successful! Redirecting...")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.markdown(utils.get_sound_html('error'), unsafe_allow_html=True)
                    st.error("❌ Invalid Username or Password")
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        with st.expander("🔑 View Demo Credentials"):
            st.code("""
User: ammar_admin | Pass: admin123   (Admin)
User: manager_1   | Pass: manager123 (Manager)
User: inv_man     | Pass: inv123     (Inventory Manager)
User: pos_op_1    | Pass: pos123     (Operator)
            """, language="text")

def logout_user():
    user = st.session_state.get('user')
    if user:
        db.unlock_terminal(user)
        db.log_activity(user, "Logout", "Session Ended")
    
    st.session_state.clear()
    st.session_state['theme'] = 'dark' 
    st.rerun()

# --- MODULES ---

def pos_interface():
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
        remaining = end_time - utils.get_system_time()
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
        
        # --- FIX 8: MARKETING AWARENESS PANEL ---
        with st.sidebar:
            st.markdown("### 📢 Marketing & Offers")
            st.info("Available Coupons for Customers")
            active_coupons = db.get_all_coupons()
            
            # Show Generic Coupons
            generic_coupons = active_coupons[active_coupons['bound_mobile'].isna() | (active_coupons['bound_mobile'] == 'None')]
            if not generic_coupons.empty:
                st.dataframe(generic_coupons[['code', 'value', 'min_bill']], hide_index=True)
            else:
                st.caption("No Generic Coupons")
            
            # Show Customer Specific Coupons if customer selected
            if st.session_state.get('current_customer'):
                cust_mob = st.session_state['current_customer']['mobile']
                my_coupons = db.get_customer_coupons(cust_mob)
                if not my_coupons.empty:
                    st.success(f"🎟️ Coupons for {st.session_state['current_customer']['name']}")
                    st.dataframe(my_coupons[['code', 'value', 'min_bill']], hide_index=True)
                    st.caption("Copy code to apply")
            
            st.markdown("---")
            st.warning("🔥 Clearance / Expiry Deals")
            risk_sum, risk_df = utils.analyze_risk_inventory(df_p)
            if not risk_df.empty:
                clearance_items = risk_df[risk_df['Status'].isin(['Near Expiry', 'Expired'])]
                if not clearance_items.empty:
                    st.dataframe(clearance_items[['Name', 'Status']], hide_index=True)
                else:
                    st.caption("No Clearance Items")
        
        with st.expander("👤 Customer Details (Required for Bill)", expanded=st.session_state['current_customer'] is None):
            col_cc, col_mob, col_search = st.columns([1, 2, 1])
            
            with col_cc:
                country_code = st.selectbox("Code", ["+91 (IN)", "+1 (US)", "+44 (UK)", "+971 (UAE)"], key="cust_cc")
                cc_val = country_code.split(" ")[0]

            with col_mob:
                # Pre-fill logic: if customer is selected, strip CC for display if it matches
                default_val = ""
                if st.session_state.get('current_customer'):
                    full_num = st.session_state['current_customer']['mobile']
                    if full_num.startswith(cc_val):
                        default_val = full_num[len(cc_val):]
                    else:
                        default_val = full_num # Fallback
                
                mobile_input = st.text_input("Mobile Number", value=default_val, key="cust_mob_in", max_chars=15).strip()

            with col_search:
                st.write("")
                st.write("")
                search_clicked = st.button("🔎 Search / Add")

            # --- VALIDATION & SEARCH LOGIC ---
            if search_clicked:
                st.markdown(utils.get_sound_html('click'), unsafe_allow_html=True)
                
                # 2️⃣ MOBILE NUMBER VALIDATION
                is_valid = True
                err_msg = ""
                
                if not mobile_input:
                    is_valid = False
                    err_msg = "Please enter a mobile number."
                elif cc_val == "+91":
                    if not mobile_input.isdigit():
                        is_valid = False
                        err_msg = "Invalid mobile number. Please enter a valid Indian number (digits only)."
                    elif len(mobile_input) != 10:
                        is_valid = False
                        err_msg = "Invalid mobile number. Please enter a valid Indian number (10 digits)."
                    elif mobile_input[0] not in ['6', '7', '8', '9']:
                        is_valid = False
                        err_msg = "Invalid mobile number. Please enter a valid Indian number (start with 6-9)."
                
                if not is_valid:
                    # 4️⃣ USER FEEDBACK (Invalid)
                    st.error(f"❌ {err_msg}")
                else:
                    # Append Country Code
                    final_mobile = f"{cc_val}{mobile_input}"
                    
                    # 3️⃣ DUPLICATE PREVENTION (Existing Logic)
                    cust = db.get_customer(final_mobile)
                    if cust:
                        st.session_state['current_customer'] = cust
                        # 4️⃣ USER FEEDBACK (Valid)
                        st.success(f"✅ Customer verified successfully: {cust['name']}")
                        st.caption(f"Loyalty Points: {cust['loyalty_points']}")
                    else:
                        st.session_state['temp_new_customer'] = final_mobile
                        st.warning("New Customer! Please enter details below.")

            # Form for New Customer
            current_full_mobile = f"{cc_val}{mobile_input}"
            
            if st.session_state.get('temp_new_customer') == current_full_mobile and not st.session_state.get('current_customer'):
                with st.form("new_cust_form"):
                    st.write(f"Creating account for: **{current_full_mobile}**")
                    new_name = st.text_input("Full Name")
                    new_email = st.text_input("Email (Optional)")
                    if st.form_submit_button("Save Customer"):
                        if new_name:
                            # 5️⃣ DATA SAFETY: Save valid number
                            db.upsert_customer(current_full_mobile, new_name, new_email)
                            st.session_state['current_customer'] = db.get_customer(current_full_mobile)
                            st.session_state.pop('temp_new_customer', None)
                            st.markdown(utils.get_sound_html('success'), unsafe_allow_html=True)
                            st.success("✅ Customer Verified & Added!")
                            st.rerun()
                        else:
                            st.markdown(utils.get_sound_html('error'), unsafe_allow_html=True)
                            st.error("Name is required.")

        st.markdown("---")
        col_scan, col_manual = st.columns([1, 2])
        with col_scan:
            st.markdown("##### 📷 Scan QR")
            qr_input = st.text_input("Simulate Scan (PROD:ID)", key="qr_scan_input", help="Simulate scanner input here")
            
            # --- FIX: DISABLE CAMERA FOR EXAM DEPLOYMENT ---
            if st.button("🎥 Start Live Scanner", disabled=True, help="Disabled for exam deployment"):
                 st.warning("Camera scanning disabled for exam-ready deployment.")

            scanned_pid = None
            if qr_input:
                scanned_pid = utils.parse_qr_input(qr_input)

            if scanned_pid:
                prod = db.get_product_by_id(scanned_pid)
                if prod:
                    cart_qty = sum(1 for x in st.session_state['cart'] if x['id'] == scanned_pid)
                    if prod['stock'] > cart_qty:
                        st.session_state['cart'].append(prod)
                        st.markdown(utils.get_sound_html('success'), unsafe_allow_html=True)
                        st.toast(f"Scanned: {prod['name']}")
                    else:
                        st.markdown(utils.get_sound_html('error'), unsafe_allow_html=True)
                        st.error("Out of Stock!")
                else:
                    st.markdown(utils.get_sound_html('error'), unsafe_allow_html=True)
                    st.error("Product Not Found")

        with col_manual:
            st.markdown("##### ⌨️ Manual Search")
            c_search, c_algo = st.columns([3, 1])
            with c_search:
                query = st.text_input("Search Product", key="pos_search")
            with c_algo:
                algo = st.selectbox("Search Algo", ["Trie (O(L))", "Linear (O(N))"])
                if algo.startswith("Trie"):
                    st.caption("ℹ️ **Trie**: Fast prefix search. Efficient for autocomplete.")
                else:
                    st.caption("ℹ️ **Linear**: Checks every item. Simple but slower for large data.")

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
                    st.markdown(styles.product_card_html(
                        item['name'], item['price'], item['stock'], item['category'], currency, item.get('image_data')
                    ), unsafe_allow_html=True)
                    
                    cart_qty = sum(1 for x in st.session_state['cart'] if x['id'] == item['id'])
                    
                    if item['stock'] > cart_qty:
                        if st.button("Add ➕", key=f"add_{item['id']}"):
                            st.session_state['cart'].append(item)
                            st.markdown(utils.get_sound_html('click'), unsafe_allow_html=True)
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
                
                st.markdown("##### 🎟️ Coupons & Loyalty")
                c_code = st.text_input("Enter Coupon Code")
                if st.button("Apply Coupon"):
                    try:
                        # FIX 5: Validate Bound Mobile
                        cust_mobile = st.session_state['current_customer']['mobile'] if st.session_state.get('current_customer') else None
                        cpn, msg = db.get_coupon(c_code, customer_mobile=cust_mobile)
                        if cpn:
                            if raw_total >= cpn['min_bill']:
                                st.session_state['applied_coupon'] = cpn
                                st.markdown(utils.get_sound_html('success'), unsafe_allow_html=True)
                                st.success(f"Coupon Applied: {msg}")
                            else:
                                st.markdown(utils.get_sound_html('error'), unsafe_allow_html=True)
                                st.error(f"Min bill required: {cpn['min_bill']}")
                        else:
                            st.markdown(utils.get_sound_html('error'), unsafe_allow_html=True)
                            st.error(msg)
                    except Exception as e:
                        st.error(f"Error applying coupon: {str(e)}")
                
                cust = st.session_state.get('current_customer')
                if cust and cust['loyalty_points'] > 0:
                    use_points = st.checkbox(f"Redeem Points (Bal: {cust['loyalty_points']})")
                    if use_points:
                        max_redeem = min(cust['loyalty_points'], int(raw_total))
                        st.session_state['points_to_redeem'] = max_redeem
                    else:
                        st.session_state['points_to_redeem'] = 0
                else:
                    st.session_state['points_to_redeem'] = 0

                discount = 0
                if st.session_state.get('applied_coupon'):
                    cp = st.session_state['applied_coupon']
                    if cp['type'] == 'Flat': discount = cp['value']
                    elif cp['type'] == '%': discount = raw_total * (cp['value']/100)
                
                loss_discount, loss_msgs = utils.calculate_advanced_loss_prevention(st.session_state['cart'])
                if loss_discount > 0:
                    st.warning(f"⚠️ Loss Prevention Discount: {currency}{loss_discount:.2f}")
                    for msg in loss_msgs: st.caption(f"• {msg}")

                fest_disc = 0
                fest_sales = active_campaigns[active_campaigns['type'] == 'Festival Offer']
                if not fest_sales.empty:
                    fest_disc = raw_total * 0.05
                    st.caption(f"🎉 Festival Offer Applied (-{currency}{fest_disc:.2f})")

                total_after_disc = max(0, raw_total - discount - fest_disc - st.session_state['points_to_redeem'] - loss_discount)
                
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
                    <div style='display:flex; justify-content:space-between; color:var(--success-color)'><span>Discount:</span><span>-{currency}{discount+fest_disc+loss_discount:.2f}</span></div>
                    <div style='display:flex; justify-content:space-between; font-weight:bold; font-size:1.2em; margin-top:5px; border-top:1px solid var(--border-color); padding-top:5px;'>
                        <span>Total:</span><span>{currency}{final_total:,.2f}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                st.markdown("---")
                c_clear, c_pay = st.columns([1, 2])
                
                with c_clear:
                    if st.button("🗑️ Clear Cart", use_container_width=True):
                        st.session_state['cart'] = []
                        st.session_state['applied_coupon'] = None
                        st.session_state['points_to_redeem'] = 0
                        st.markdown(utils.get_sound_html('click'), unsafe_allow_html=True)
                        st.rerun()
                
                with c_pay:
                    if st.button("💳 Proceed to Pay", type="primary", use_container_width=True):
                        if not st.session_state['current_customer']:
                            st.markdown(utils.get_sound_html('error'), unsafe_allow_html=True)
                            st.error("Please add Customer Details first!")
                        else:
                            st.markdown(utils.get_sound_html('click'), unsafe_allow_html=True)
                            st.session_state['final_calc'] = {
                                "total": final_total, 
                                "tax": tax_amount, 
                                "discount": discount + fest_disc + loss_discount,
                                "points": st.session_state['points_to_redeem']
                            }
                            st.session_state['checkout_stage'] = 'payment_method'
                            st.rerun()
            else:
                st.info("Cart is empty")
                st.button("Proceed to Pay", disabled=True)
            st.markdown("</div>", unsafe_allow_html=True)

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
                st.markdown(utils.get_sound_html('click'), unsafe_allow_html=True)
                st.rerun()
        with c2:
            st.markdown("#### 📱 UPI / QR")
            if st.button("Select UPI", use_container_width=True):
                st.session_state['selected_payment_mode'] = 'UPI'
                st.session_state['checkout_stage'] = 'payment_process'
                st.session_state['qr_expiry'] = None 
                st.session_state.pop('upi_txn_ref', None) 
                st.markdown(utils.get_sound_html('click'), unsafe_allow_html=True)
                st.rerun()
        with c3:
            st.markdown("#### 💳 Card")
            if st.button("Select Card", use_container_width=True):
                st.session_state['selected_payment_mode'] = 'Card'
                st.session_state['checkout_stage'] = 'payment_process'
                st.markdown(utils.get_sound_html('click'), unsafe_allow_html=True)
                st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    elif st.session_state['checkout_stage'] == 'payment_process':
        st.markdown("<div class='card-container'>", unsafe_allow_html=True)
        
        # --- FIX: INSTANT PAYMENT METHOD SWITCHING ---
        col_back, col_switch = st.columns([1, 4])
        with col_back:
            st.button("⬅ Cancel", on_click=lambda: st.session_state.update({'checkout_stage': 'payment_method'}))
        with col_switch:
            modes = ["Cash", "UPI", "Card"]
            curr_mode = st.session_state['selected_payment_mode']
            new_mode = st.radio("Switch Payment Mode", modes, index=modes.index(curr_mode), horizontal=True, label_visibility="collapsed")
            if new_mode != curr_mode:
                st.session_state['selected_payment_mode'] = new_mode
                st.session_state['qr_expiry'] = None
                st.session_state.pop('upi_txn_ref', None)
                st.rerun()

        calc = st.session_state['final_calc']
        total = calc['total']
        mode = st.session_state['selected_payment_mode']
        
        st.subheader(f"Processing {mode} Payment - Amount: {currency}{total:,.2f}")
        
        if mode == 'Cash':
            # FIX: Use safe_float for large inputs or manual override
            tendered = st.number_input("Amount Received from Customer", min_value=0.0, step=100.0, format="%.2f")
            
            if tendered > 0:
                change = tendered - total
                if change >= 0:
                    st.success(f"✅ Sufficient Amount. Change to return: {currency}{change:,.2f}")
                    if st.button("Confirm Cash Payment", type="primary"):
                        st.markdown(utils.get_sound_html('success'), unsafe_allow_html=True)
                        finalize_sale(total, "Cash")
                else:
                    st.error(f"❌ Insufficient Cash. Short by: {currency}{abs(change):,.2f}")
            else:
                st.info("Enter amount received to calculate change.")

        elif mode == 'UPI':
            if st.session_state['qr_expiry'] is None:
                st.session_state['qr_expiry'] = time.time() + 240 
            
            if 'upi_txn_ref' not in st.session_state:
                st.session_state['upi_txn_ref'] = f"INV-{random.randint(1000,9999)}"
            
            remaining = int(st.session_state['qr_expiry'] - time.time())
            
            c_qr, c_info = st.columns([1, 1])
            with c_qr:
                upi_id = db.get_setting("upi_id")
                txn_ref = st.session_state['upi_txn_ref']
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
                            st.markdown(utils.get_sound_html('success'), unsafe_allow_html=True)
                            finalize_sale(total, "UPI")
                        else:
                            st.markdown(utils.get_sound_html('error'), unsafe_allow_html=True)
                            st.error("Invalid Transaction ID")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("⏰ QR Code Expired")
                    if st.button("🔄 Regenerate"):
                        st.session_state['qr_expiry'] = None
                        st.session_state.pop('upi_txn_ref', None)
                        st.rerun()

        elif mode == 'Card':
            st.info("💳 Card Payment Simulation")
            col_cc1, col_cc2 = st.columns(2)
            with col_cc1:
                cc_name = st.text_input("Card Holder Name")
                cc_num = st.text_input("Card Number (Last 4 digits or Full)", max_chars=16)
            with col_cc2:
                cc_exp = st.text_input("Expiry (MM/YY)")
                cc_cvv = st.text_input("CVV", type="password", max_chars=4)
            
            if st.button("Process Transaction"):
                valid, msg = utils.validate_card(cc_num, cc_exp, cc_cvv)
                if valid:
                    with st.spinner("Contacting Bank Gateway..."):
                        time.sleep(2) 
                        with st.spinner("Verifying Credentials..."):
                            time.sleep(1.5)
                        st.markdown(utils.get_sound_html('success'), unsafe_allow_html=True)
                        finalize_sale(total, "Card")
                else:
                    st.markdown(utils.get_sound_html('error'), unsafe_allow_html=True)
                    st.error(f"Transaction Failed: {msg}")

        st.markdown("</div>", unsafe_allow_html=True)

    elif st.session_state['checkout_stage'] == 'receipt':
        st.markdown(utils.get_sound_html('success'), unsafe_allow_html=True)
        st.markdown("<div class='card-container' style='text-align:center'>", unsafe_allow_html=True)
        st.title("✅ Payment Successful")
        st.caption("Transaction has been recorded.")
        
        # FIX 9: SHOW GENERATED COUPON
        if 'new_coupon_code' in st.session_state and st.session_state['new_coupon_code']:
            st.markdown("---")
            st.success("🎉 Special Gift for the Customer!")
            st.markdown(f"**Generated Coupon:** `{st.session_state['new_coupon_code']}`")
            st.caption("Valid for 10% OFF on next visit (30 days)")
            st.markdown("---")
            
        c_rec1, c_rec2 = st.columns(2)
        with c_rec1:
            if 'last_receipt' in st.session_state:
                st.markdown("""<style>.box-btn{border:1px solid #444; padding:15px; border-radius:10px; text-align:center; display:block; text-decoration:none; color:inherit; background:#222; margin:10px;}</style>""", unsafe_allow_html=True)
                
                # --- FIX: DYNAMIC RECEIPT NAME ---
                cust_name = "Guest"
                if st.session_state.get('current_customer'):
                    cust_name = st.session_state['current_customer']['name'].replace(" ", "")
                
                # Get sale ID from database (it's the last one)
                # But here we don't have it directly. We can use a timestamp or a generic name if ID isn't in session.
                # In finalize_sale we actually know the ID, but it returns. 
                # Let's use a timestamp based name.
                ist_now = utils.get_system_time()
                file_ts = ist_now.strftime("%Y-%m-%d")
                
                fname = f"{file_ts}_Sale_{cust_name}.pdf"
                
                st.download_button(
                    "📄 Download Receipt PDF", 
                    st.session_state['last_receipt'], 
                    fname, 
                    "application/pdf", 
                    use_container_width=True
                )
        
        with c_rec2:
            if st.button("🛒 Start New Sale", type="primary", use_container_width=True):
                st.session_state['cart'] = []
                st.session_state['current_customer'] = None
                st.session_state['checkout_stage'] = 'cart'
                st.session_state['applied_coupon'] = None
                st.session_state['points_to_redeem'] = 0
                st.session_state.pop('upi_txn_ref', None)
                st.session_state.pop('new_coupon_code', None) # Clear coupon
                st.session_state.pop('new_coupon_details', None) # Clear coupon details
                st.markdown(utils.get_sound_html('click'), unsafe_allow_html=True)
                st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

def finalize_sale(total, mode):
    # --- REAL-TIME SIMULATION FIX ---
    with st.spinner(f"Processing {mode} Transaction..."):
        time.sleep(1.5)

    calc = st.session_state['final_calc']
    # FIX: Use IST Time
    txn_time = utils.get_system_time().strftime("%Y-%m-%d %H:%M:%S")
    operator = st.session_state['full_name']
    customer = st.session_state['current_customer']
    customer_mobile = customer['mobile'] if customer else None
    
    points_earned = 0
    if customer:
        points_earned = utils.calculate_loyalty_points(total)
    
    items_json = json.dumps([i['id'] for i in st.session_state['cart']])
    integrity_hash = utils.generate_integrity_hash((txn_time, total, items_json, operator))
    
    coupon_code = None
    if st.session_state.get('applied_coupon'):
         coupon_code = st.session_state['applied_coupon']['code']
    
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
            30 
        )
        
        st.session_state['undo_stack'].append(sale_id)
        st.session_state['redo_stack'] = []
        
        db.log_activity(operator, "Sale Completed", f"Sale #{sale_id} for {currency}{total:.2f}")
        
        # FIX 9: GENERATE COUPON
        new_coupon_details = None
        if customer_mobile:
            new_code = db.generate_auto_coupon(customer_mobile)
            if new_code:
                st.session_state['new_coupon_code'] = new_code
                # Retreive full details to pass to PDF
                cpn, msg = db.get_coupon(new_code, customer_mobile)
                if cpn:
                    new_coupon_details = cpn
                    st.session_state['new_coupon_details'] = cpn
        
        tax_info = {"tax_amount": calc['tax'], "tax_percent": 18}
        
        # FIX 4: Pass new_coupon details to PDF generator
        pdf = utils.generate_receipt_pdf(store_name, sale_id, txn_time, st.session_state['cart'], total, operator, mode, st.session_state['pos_id'], customer, tax_info, new_coupon=new_coupon_details)
        
        st.session_state['last_receipt'] = pdf
        st.session_state['checkout_stage'] = 'receipt'
        st.session_state['qr_expiry'] = None
        st.rerun()
        
    except Exception as e:
        st.markdown(utils.get_sound_html('error'), unsafe_allow_html=True)
        st.error(f"Transaction Failed: {str(e)}")

def analytics_dashboard():
    st.title("📈 Enterprise Analytics")
    df_sales = db.get_sales_data()
    
    # FIX 3: Filter out cancelled transactions for charts
    if 'status' in df_sales.columns:
        active_sales = df_sales[df_sales['status'] != 'Cancelled']
    else:
        active_sales = df_sales

    conn = db.get_connection()
    df_prods = pd.read_sql("SELECT * FROM products", conn)
    conn.close()
    
    try:
        active_sales['date'] = pd.to_datetime(active_sales['timestamp'], format='mixed', dayfirst=False, errors='coerce')
        active_sales = active_sales.dropna(subset=['date'])
    except:
        st.error("Date parsing failed. Check DB format.")
        return
    total_rev = active_sales['total_amount'].sum()
    total_txns = len(active_sales)
    
    m1, m2, m3 = st.columns(3)
    with m1: st.markdown(f"<div class='kpi-card'><div class='kpi-title'>Total Revenue</div><div class='kpi-value'>{currency}{total_rev:,.0f}</div></div>", unsafe_allow_html=True)
    with m2: st.markdown(f"<div class='kpi-card'><div class='kpi-title'>Active Sales</div><div class='kpi-value'>{total_txns}</div></div>", unsafe_allow_html=True)
    val = total_rev/total_txns if total_txns > 0 else 0
    with m3: st.markdown(f"<div class='kpi-card'><div class='kpi-title'>Avg Order Value</div><div class='kpi-value'>{currency}{val:.0f}</div></div>", unsafe_allow_html=True)

    t1, t2, t3, t4, t5, t6, t7, t8, t9 = st.tabs([
        "💰 Financials & P&L", "⚠️ Risk & Loss Prevention", "Sales Trends", "Staff Performance", 
        "Demand Forecast", "Algorithm Showcase", "🏆 Rankings", "📊 Category Analysis", "💎 Customer Value (CLV)"
    ])
    
    with t1:
        st.markdown("<div class='card-container'>", unsafe_allow_html=True)
        
        # --- POS WISE COLLECTION SUMMARY ---
        st.subheader("🏦 POS-wise Collection Summary")
        pos_summ = db.get_pos_collection_stats()
        if not pos_summ.empty:
            st.dataframe(pos_summ, use_container_width=True)
            
            # Pivot for better view
            try:
                pivot_pos = pos_summ.pivot(index='pos_id', columns='payment_mode', values='total').fillna(0)
                st.bar_chart(pivot_pos)
            except:
                st.info("Insufficient data for pivot chart.")
        else:
            st.info("No sales data available for breakdown.")

        st.markdown("---")
        st.subheader("💰 Profit & Loss Statement")
        pl_summary, pl_df = utils.calculate_profit_loss(df_sales, df_prods) # Function handles filtering
        ratios = utils.calculate_financial_ratios(df_sales, df_prods)
        
        c_pl1, c_pl2, c_pl3, c_pl4 = st.columns(4)
        c_pl1.metric("Net Profit", f"{currency}{pl_summary['net_profit']:,.2f}", delta=f"{pl_summary['margin_percent']:.1f}% Margin")
        c_pl2.metric("Total COGS", f"{currency}{pl_summary['total_cost']:,.2f}", help="Cost of Goods Sold")
        c_pl3.metric("Inventory Turnover", f"{ratios['inventory_turnover_ratio']}x", help="Higher is better")
        c_pl4.metric("Inventory Valuation", f"{currency}{ratios['inventory_valuation']:,.0f}")
        
        st.markdown("#### Category-wise Profitability")
        if not pl_df.empty:
            st.bar_chart(pl_df.set_index('Category')['Profit'])
            st.dataframe(pl_df.style.format({"Revenue": "{:,.2f}", "Cost": "{:,.2f}", "Profit": "{:,.2f}", "Margin %": "{:.1f}%"}), use_container_width=True)
            st.markdown("#### 💹 Profit vs Revenue")
            st.bar_chart(pl_df.set_index('Category')[['Revenue', 'Profit']])
        else:
            st.info("No data available")
        st.markdown("</div>", unsafe_allow_html=True)

    with t2:
        st.markdown("<div class='card-container'>", unsafe_allow_html=True)
        st.subheader("⚠️ Inventory Risk Assessment")
        risk_summary, risk_df = utils.analyze_risk_inventory(df_prods)
        
        c_r1, c_r2, c_r3 = st.columns(3)
        c_r1.metric("Dead Stock Value", f"{currency}{risk_summary['dead_stock_value']:,.2f}", delta_color="inverse")
        c_r2.metric("Expired Stock Loss", f"{currency}{risk_summary['expired_loss']:,.2f}", delta_color="inverse")
        c_r3.metric("Near Expiry Risk", f"{currency}{risk_summary['near_expiry_risk']:,.2f}", help="Capital at risk of expiration")
        
        st.markdown("---")
        
        col_risk_viz, col_risk_act = st.columns([2, 1])
        with col_risk_viz:
            st.markdown("#### Stock Health Breakdown")
            if not risk_df.empty:
                risk_counts = risk_df['Status'].value_counts()
                st.bar_chart(risk_counts)
                st.dataframe(risk_df[risk_df['Status'] != 'Safe'], use_container_width=True)
        
        with col_risk_act:
            st.info("📉 Loss Minimization Strategy")
            st.markdown("""
            **For Near-Expiry Products:**
            1. Apply **30-50% Discount** immediately.
            2. Bundle with High-Selling items.
            3. Aim to recover **Cost Price**.
            
            **For Dead Stock:**
            1. Return to vendor if possible.
            2. Liquidation Sale (Buy 1 Get 1).
            """)
        st.markdown("</div>", unsafe_allow_html=True)

    with t3:
        st.markdown("<div class='card-container'>", unsafe_allow_html=True)
        c_trend1, c_trend2 = st.columns(2)
        
        daily = active_sales.groupby(active_sales['date'].dt.date)['total_amount'].sum().reset_index()
        trend_dir = utils.analyze_trend_slope(daily['total_amount'].values)
        st.info(f"Market Trend (Algo #32): {trend_dir}")
        
        with c_trend1:
            st.markdown("#### 📅 Daily Sales Trend")
            st.line_chart(daily.set_index('date')['total_amount'])
            
        with c_trend2:
            st.markdown("#### 💳 Payment Method Usage")
            pay_dist = active_sales['payment_mode'].value_counts()
            fig, ax = plt.subplots()
            ax.pie(pay_dist, labels=pay_dist.index, autopct='%1.1f%%', startangle=90, colors=['#6366f1', '#10b981', '#f59e0b'])
            ax.axis('equal') 
            st.pyplot(fig)
            
        st.markdown("#### 📆 Monthly Sales Trend")
        active_sales['month'] = active_sales['date'].dt.to_period('M').astype(str)
        monthly = active_sales.groupby('month')['total_amount'].sum()
        st.bar_chart(monthly)

        st.markdown("</div>", unsafe_allow_html=True)
    with t4:
        st.markdown("<div class='card-container'>", unsafe_allow_html=True)
        st.subheader("👥 Employee Efficiency & Performance")
        
        # New Performance Metrics
        perf_stats = db.get_employee_performance_stats()
        if not perf_stats.empty:
            perf_stats['efficiency_score'] = (perf_stats['total_revenue'] * 0.001) + (perf_stats['txn_count'] * 2) - (perf_stats['avg_speed'] * 0.1)
            perf_stats = perf_stats.sort_values('efficiency_score', ascending=False)
            
            st.dataframe(perf_stats, use_container_width=True)
            
            c1, c2 = st.columns(2)
            c1.bar_chart(perf_stats.set_index('operator')['total_revenue'])
            c2.bar_chart(perf_stats.set_index('operator')['avg_speed'])
        else:
            st.info("No performance data available.")
            
        st.markdown("</div>", unsafe_allow_html=True)
    with t5:
        st.markdown("<div class='card-container'>", unsafe_allow_html=True)
        if not active_sales.empty:
            daily = active_sales.groupby(active_sales['date'].dt.date)['total_amount'].sum().reset_index()
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
    with t6:
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
    with t7:
        st.markdown("<div class='card-container'>", unsafe_allow_html=True)
        st.subheader("🥇 Top Performers (Rankings)")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("#### 🏆 Best POS Operators")
            staff_rank = active_sales.groupby('operator')['total_amount'].sum().reset_index().sort_values('total_amount', ascending=False)
            st.dataframe(staff_rank.style.highlight_max(axis=0), use_container_width=True)
        with c2:
            st.markdown("#### ⚡ Fastest Checkouts")
            fast_op = active_sales.groupby('operator')['time_taken'].mean().reset_index().sort_values('time_taken')
            st.dataframe(fast_op, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)
    with t8:
        st.markdown("<div class='card-container'>", unsafe_allow_html=True)
        st.subheader("📊 Category Performance Analysis")
        cat_perf = db.get_category_performance()
        if not cat_perf.empty:
            c1, c2 = st.columns([2, 1])
            with c1:
                # FIX 2: Pie Chart Improvements
                fig, ax = plt.subplots(figsize=(6, 6))
                
                wedges, texts, autotexts = ax.pie(
                    cat_perf['Revenue'], 
                    labels=cat_perf['Category'], 
                    autopct='%1.1f%%', 
                    startangle=90, 
                    pctdistance=0.85,
                    wedgeprops=dict(width=0.4, edgecolor='w') 
                )
                
                plt.setp(texts, size=9)
                plt.setp(autotexts, size=8, weight="bold", color="white")
                ax.legend(wedges, cat_perf['Category'], title="Categories", loc="center left", bbox_to_anchor=(1, 0, 0.5, 1))
                ax.axis('equal')
                st.pyplot(fig)
            with c2:
                st.dataframe(cat_perf, use_container_width=True)
        else:
            st.info("No category data available yet.")
        st.markdown("</div>", unsafe_allow_html=True)
        
    with t9:
        st.markdown("<div class='card-container'>", unsafe_allow_html=True)
        st.subheader("💎 Customer Lifetime Value (CLV)")
        clv_df = db.get_customer_clv_stats()
        if not clv_df.empty:
            # Top 10 Customers
            st.markdown("#### 🌟 Top 10 High-Value Customers")
            st.bar_chart(clv_df.head(10).set_index('name')['total_spend'])
            
            # Segment Distribution
            st.markdown("#### 🥧 Customer Segmentation")
            seg_counts = clv_df['segment'].value_counts()
            fig, ax = plt.subplots(figsize=(6, 3))
            seg_counts.plot(kind='barh', ax=ax, color=['#10b981', '#6366f1', '#f59e0b'])
            st.pyplot(fig)
            
            st.dataframe(clv_df, use_container_width=True)
        else:
            st.info("No customer data available.")
        st.markdown("</div>", unsafe_allow_html=True)

# --- MAIN CONTROLLER ---
def main():
    if not st.session_state.get('user'):
        login_view()
    else:
        with st.sidebar:
            st.markdown(f"""
            <div style="padding: 15px; background: rgba(255,255,255,0.05); border-radius: 12px; margin-bottom: 20px; border: 1px solid rgba(255,255,255,0.1);">
                <div style="font-size: 0.8rem; opacity: 0.7; letter-spacing: 1px;">CURRENT USER</div>
                <div style="font-weight: 600; font-size: 1.1rem; margin-top: 5px;">{st.session_state['user']}</div>
                <div style="font-size: 0.85rem; color: #6366f1; margin-top: 2px;">{st.session_state['role']}</div>
            </div>
            """, unsafe_allow_html=True)
            
            c_theme, c_lbl = st.columns([1, 4])
            with c_theme:
                current = st.session_state['theme']
                if st.button("🎨", help="Switch Theme"):
                    if current == 'dark': st.session_state['theme'] = 'light'
                    elif current == 'light': st.session_state['theme'] = 'adaptive'
                    else: st.session_state['theme'] = 'dark'
                    st.rerun()
            with c_lbl: st.caption(f"Theme: {st.session_state['theme'].capitalize()}")

            st.markdown("---")
            
            role = st.session_state['role']
            nav_opts = ["POS Terminal", "My Profile", "Documentation"]
            if role in ["Admin", "Manager"]: nav_opts = ["POS Terminal", "Inventory", "Analytics", "Admin Panel", "My Profile", "Documentation"]
            elif role == "Inventory Manager": nav_opts = ["Inventory", "My Profile", "Documentation"]
            
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
        elif choice == "Documentation": render_docs()

if __name__ == "__main__":
    main()
