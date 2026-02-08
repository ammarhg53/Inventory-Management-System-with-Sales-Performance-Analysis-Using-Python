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
            col_c1, col_c2 = st.columns([2, 1])
            with col_c1:
                cust_phone = st.text_input("Customer Mobile", value=st.session_state['current_customer']['mobile'] if st.session_state['current_customer'] else "").strip()
            with col_c2:
                st.write("")
                st.write("")
                if st.button("🔎 Search / Add"):
                    st.markdown(utils.get_sound_html('click'), unsafe_allow_html=True)
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
                            st.markdown(utils.get_sound_html('success'), unsafe_allow_html=True)
                            st.success("Customer Added!")
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
            tendered = st.number_input("Amount Received from Customer", min_value=0.0, step=10.0)
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
                st.download_button("📄 Download Receipt PDF", st.session_state['last_receipt'], "receipt.pdf", "application/pdf", use_container_width=True)
        
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

def inventory_manager():
    st.title("📦 Master Inventory Management")
    tab_view, tab_add, tab_restock, tab_reqs, tab_metrics, tab_abc = st.tabs(["View & Edit", "Add New Product", "➕ Restock (Manual/QR)", "📋 Stock Requests", "Stock Metrics", "ABC Analysis"])
    
    conn = db.get_connection()
    df = pd.read_sql("SELECT * FROM products", conn)
    conn.close()
    
    with tab_view:
        st.markdown("<div class='card-container'>", unsafe_allow_html=True)
        st.markdown("### Product Database")
        col_f1, col_f2 = st.columns(2)
        # FIX 3: get_categories_list used here (provided by db module)
        cat_filter = col_f1.selectbox("Filter Category", ["All"] + db.get_categories_list())
        search_txt = col_f2.text_input("Search Name")
        df_filtered = df
        if cat_filter != "All": df_filtered = df[df['category'] == cat_filter]
        if search_txt: df_filtered = df_filtered[df_filtered['name'].str.contains(search_txt, case=False)]
        
        st.dataframe(df_filtered[['id', 'name', 'category', 'price', 'stock', 'expiry_date', 'is_dead_stock']], use_container_width=True)
        
        col_dead_1, col_dead_2 = st.columns(2)
        with col_dead_1:
            st.markdown("##### 💀 Manage Dead Stock")
            ds_id = st.number_input("Product ID", min_value=1, step=1, key="ds_pid")
            ds_action = st.radio("Set Status", ["Active", "Dead Stock"], horizontal=True)
            if st.button("Update Status"):
                db.toggle_dead_stock(ds_id, ds_action == "Dead Stock")
                st.markdown(utils.get_sound_html('success'), unsafe_allow_html=True)
                st.success("Status Updated")
                time.sleep(1)
                st.rerun()
        
        with col_dead_2:
            st.markdown("##### 🖨️ Bulk QR Label Printing")
            # FIX 6: Robust PDF Generation Call
            if st.button("Generate QR Labels PDF (All Items)"):
                try:
                    with st.spinner("Generating QR Codes..."):
                        pdf_bytes = utils.generate_qr_labels_pdf(df_filtered.to_dict('records'))
                    st.download_button("⬇️ Download Labels PDF", pdf_bytes, "qr_labels.pdf", "application/pdf")
                    st.markdown(utils.get_sound_html('success'), unsafe_allow_html=True)
                except Exception as e:
                    st.error(f"Error generating PDF: {e}")
            
            st.markdown("---")
            st.markdown("##### Generate Single QR")
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
        with st.form("new_prod", clear_on_submit=True):
            n = st.text_input("Product Name")
            c = st.selectbox("Category", db.get_categories_list())
            p = st.number_input("Selling Price", min_value=0.0)
            cp = st.number_input("Cost Price", min_value=0.0)
            s = st.number_input("Initial Stock", min_value=0)
            img_file = st.file_uploader("Product Image (Optional)", type=['png', 'jpg', 'jpeg'])
            has_expiry = st.radio("Does this product have an expiry date?", ["Yes", "No"], index=0, horizontal=True)
            exp = None
            if has_expiry == "Yes":
                exp = st.date_input("Expiry Date")
            else:
                exp = "NA"
            
            if st.form_submit_button("Add Product"):
                img_bytes = img_file.getvalue() if img_file else None
                if db.add_product(n, c, p, s, cp, exp, img_bytes):
                    st.markdown(utils.get_sound_html('success'), unsafe_allow_html=True)
                    st.success(f"Product information stored successfully: {n}")
                else: 
                    st.markdown(utils.get_sound_html('error'), unsafe_allow_html=True)
                    st.error("Error adding product")
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
                    st.markdown(utils.get_sound_html('success'), unsafe_allow_html=True)
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
                    st.markdown(utils.get_sound_html('success'), unsafe_allow_html=True)
                    st.success("Request Submitted")
                else: st.error("Invalid Product ID")
        st.divider()
        st.dataframe(db.get_stock_requests(), use_container_width=True)
        
        # Admin Action for Requests
        reqs = db.get_stock_requests()
        pending = reqs[reqs['status'] == 'Pending']
        if not pending.empty and st.session_state['role'] in ['Admin', 'Inventory Manager']:
             st.markdown("#### Pending Actions")
             for _, r in pending.iterrows():
                with st.expander(f"REQ #{r['id']}: {r['product_name']} ({r['quantity']})"):
                    st.write(f"**User:** {r['requested_by']} | **Note:** {r['notes']}")
                    c1, c2 = st.columns(2)
                    if c1.button("✅ Approve", key=f"app_{r['id']}"):
                         db.update_request_status(r['id'], "Approved"); st.rerun()
                    if c2.button("❌ Reject", key=f"rej_{r['id']}"):
                         db.update_request_status(r['id'], "Rejected"); st.rerun()

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

    t1, t2, t3, t4, t5, t6, t7, t8 = st.tabs([
        "💰 Financials & P&L", "⚠️ Risk & Loss Prevention", "Sales Trends", "Staff Performance", 
        "Demand Forecast", "Algorithm Showcase", "🏆 Rankings", "📊 Category Analysis"
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

def admin_panel():
    st.title("🛡️ Admin Console")
    tab_dash, tab_emp_live, tab_cats, tab_settings, tab_cust, tab_term, tab_users, tab_req_app, tab_market, tab_txns, tab_logs = st.tabs([
        "Controls", "👥 Employees (Live)", "Category", "⚙️ Settings", "👥 Customers", "🖥️ Terminals", "👤 Users", "📝 Stock Reqs", "🚀 Marketing", "📜 Transactions", "📝 Logs"
    ])
    
    with tab_dash:
        st.markdown("<div class='card-container'>", unsafe_allow_html=True)
        c_live, c_unlock = st.columns(2)
        with c_live:
            # POINT 5: REAL-TIME SIMULATION
            live_mode = st.checkbox("🔄 Enable Live Dashboard (Auto-Refresh 10s)")
            if live_mode:
                time.sleep(10)
                st.rerun()
        with c_unlock:
            if st.button("🔓 Force Unlock All Terminals"):
                db.force_clear_all_sessions()
                st.success("All session locks cleared.")
        
        st.markdown("---")
        
        # FIX 7: UI for Cancellation with Password & Search
        st.subheader("🚫 Order Cancellation & Reversal")
        
        c_undo, c_search = st.columns(2)
        
        with c_undo:
            st.markdown("#### ↩️ Undo Last My Sale")
            if st.session_state['undo_stack']:
                last_sale_id = st.session_state['undo_stack'][-1]
                st.warning(f"Target: Sale ID #{last_sale_id}")
                
                with st.form("undo_last_form"):
                    u_reason = st.text_input("Cancellation Reason", placeholder="Reason is mandatory...")
                    u_pass = st.text_input("Confirm Password", type="password")
                    if st.form_submit_button("Confirm Undo"):
                        success, msg = db.cancel_sale_transaction(last_sale_id, st.session_state['user'], st.session_state['role'], u_reason, u_pass)
                        if success:
                            st.session_state['redo_stack'].append(st.session_state['undo_stack'].pop())
                            st.markdown(utils.get_sound_html('success'), unsafe_allow_html=True)
                            st.success(msg)
                            time.sleep(1.5)
                            st.rerun()
                        else:
                            st.markdown(utils.get_sound_html('error'), unsafe_allow_html=True)
                            st.error(f"Failed: {msg}")
            else: st.info("No recent transactions in this session.")
        
        with c_search:
            # New Feature: Search & Cancel for Managers/Admins
            st.markdown("#### 🔎 Search & Cancel (Manager/Admin)")
            if st.session_state['role'] in ['Manager', 'Admin']:
                with st.form("search_cancel_form"):
                    sc_id = st.number_input("Enter Sale ID", min_value=1, step=1)
                    sc_reason = st.text_input("Cancellation Reason")
                    sc_pass = st.text_input("Confirm Password", type="password")
                    if st.form_submit_button("Search & Cancel"):
                        success, msg = db.cancel_sale_transaction(sc_id, st.session_state['user'], st.session_state['role'], sc_reason, sc_pass)
                        if success:
                            st.markdown(utils.get_sound_html('success'), unsafe_allow_html=True)
                            st.success(msg)
                        else:
                            st.markdown(utils.get_sound_html('error'), unsafe_allow_html=True)
                            st.error(msg)
            else:
                st.info("Permission Restricted to Managers & Admins.")

        st.markdown("---")
        if st.button("Create System Backup"):
            path = utils.backup_system()
            if path: st.success(f"Backup: {path}")
        st.markdown("</div>", unsafe_allow_html=True)

    with tab_emp_live:
        st.markdown("<div class='card-container'>", unsafe_allow_html=True)
        st.subheader("🔴 Employee Live Monitor")
        st.caption("Real-time activity tracking across all terminals")
        
        live_df = db.get_employee_activity_live()
        
        if not live_df.empty:
            for i, row in live_df.iterrows():
                is_online = pd.notna(row['current_pos']) and row['current_pos'] != ''
                
                status_html = ""
                if is_online:
                     status_html = f"<div class='status-dot-online'></div> Online @ {row['current_pos']}"
                     bg_color = "rgba(16, 185, 129, 0.1)"
                     border_l = "#10b981"
                else:
                     status_html = f"<div class='status-dot-offline'></div> Offline"
                     bg_color = "rgba(255, 255, 255, 0.05)"
                     border_l = "#94a3b8"
                
                st.markdown(f"""
                <div style="background: {bg_color}; border-left: 4px solid {border_l}; border-radius: 8px; padding: 15px; margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <div style="font-weight: bold; font-size: 1.1rem;">{row['full_name']}</div>
                        <div style="font-size: 0.85rem; opacity: 0.7;">{row['role']}</div>
                    </div>
                    <div style="text-align: right;">
                        <div style="font-weight: bold; color: {border_l};">{status_html}</div>
                        <div style="font-size: 0.85rem; margin-top: 5px;">Live Session Sales: {currency}{row['daily_sales']:,.2f}</div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("No employee data found.")
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
        if st.session_state['role'] != 'Admin':
            st.error("⛔ Access Denied. Administrator privileges required.")
        else:
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
                    db.log_activity(st.session_state['user'], "Settings Update", "System settings modified")
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
        if st.session_state['role'] != 'Admin':
            st.error("⛔ Access Denied. Administrator privileges required.")
        else:
            with st.expander("Add New Terminal"):
                with st.form("add_term"):
                    nt_id = st.text_input("Terminal ID (e.g., POS-3)")
                    nt_name = st.text_input("Name (e.g., Upstairs)")
                    nt_loc = st.text_input("Location")
                    if st.form_submit_button("Create Terminal"):
                        if db.add_terminal(nt_id, nt_name, nt_loc): st.success("Terminal Added"); st.rerun()
                        else: st.error("Error creating terminal")
            
            # --- FIX: USE STATUS-AWARE DATAFRAME FOR ADMIN CONTROL ---
            terms_status = db.get_all_terminals_status()
            stats_df = db.get_terminal_stats()
            
            for _, t in terms_status.iterrows():
                with st.container():
                    c1, c2, c3 = st.columns([3, 1, 1])
                    
                    # Match stats
                    t_stat = stats_df[stats_df['pos_id'] == t['id']]
                    rev = 0
                    cnt = 0
                    if not t_stat.empty:
                        rev = t_stat.iloc[0]['total_revenue']
                        cnt = t_stat.iloc[0]['order_count']
                    
                    # VISUAL STATUS
                    stat_icon = "🟢" if t['status'] == 'Active' else "🔴"
                    if pd.notna(t['current_user']) and t['current_user'] != '':
                        stat_icon = "🟡" # In Use
                    
                    c1.write(f"{stat_icon} **{t['name']}** ({t['id']}) - {t['location']}")
                    c1.caption(f"Orders: {cnt} | Revenue: {currency}{rev:,.2f}")
                    
                    # Show active session details if locked
                    if pd.notna(t['current_user']) and t['current_user'] != '':
                         c1.warning(f"🔒 Locked by **{t['current_user']}** since {t['login_time']}")
                         if c1.button(f"🔓 Force Unlock {t['id']}", key=f"unlock_{t['id']}"):
                             db.force_unlock_terminal(t['id'])
                             st.success(f"{t['id']} unlocked!")
                             time.sleep(0.5)
                             st.rerun()

                    new_status = c2.selectbox("Status", ["Active", "Maintenance", "Error"], index=["Active", "Maintenance", "Error"].index(t['status']), key=f"status_{t['id']}")
                    if new_status != t['status']:
                        db.update_terminal_status(t['id'], new_status)
                        st.toast("Status Updated")
                        time.sleep(0.5)
                        st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    with tab_users:
        st.markdown("<div class='card-container'>", unsafe_allow_html=True)
        if st.session_state['role'] != 'Admin':
             st.error("⛔ Access Denied. Administrator privileges required.")
        else:
            with st.expander("Create New User"):
                with st.form("new_user_form", clear_on_submit=True):
                    nu_user = st.text_input("Username")
                    nu_pass = st.text_input("Password", type="password")
                    nu_name = st.text_input("Full Name")
                    nu_role = st.selectbox("Role", ["Operator", "Manager", "Inventory Manager"])
                    
                    # Password Strength
                    if nu_pass:
                        score, label, color = utils.check_password_strength(nu_pass)
                        st.markdown(f"<span style='color:{color}; font-weight:bold;'>Strength: {label}</span>", unsafe_allow_html=True)
                    
                    if st.form_submit_button("Create User"):
                        if score < 2:
                            st.error("Password is too weak!")
                        elif db.create_user(nu_user, nu_pass, nu_role, nu_name): 
                            db.log_activity(st.session_state['user'], "User Created", f"Created user {nu_user}")
                            st.success(f"User '{nu_user}' created successfully")
                        else: st.error("Error creating user")
            
            st.subheader("Manage User Status")
            users = db.get_all_users()
            for _, u in users.iterrows():
                with st.container():
                    c1, c2 = st.columns([4, 1])
                    c1.write(f"**{u['username']}** ({u['role']}) - {u['status']}")
                    
                    if u['username'] != st.session_state['user']:
                        new_stat = c2.selectbox("Status", ["Active", "Disabled"], index=0 if u['status'] == 'Active' else 1, key=f"u_stat_{u['username']}")
                        if new_stat != u['status']:
                            db.update_user_status(u['username'], new_stat)
                            db.log_activity(st.session_state['user'], "User Status Update", f"Set {u['username']} to {new_stat}")
                            st.toast(f"User {u['username']} updated to {new_stat}")
                            time.sleep(0.5)
                            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    with tab_req_app:
        st.markdown("<div class='card-container'>", unsafe_allow_html=True)
        reqs = db.get_stock_requests()
        pending = reqs[reqs['status'] == 'Pending']
        if not pending.empty and st.session_state['role'] in ['Admin', 'Inventory Manager']:
             st.markdown("#### Pending Actions")
             for _, r in pending.iterrows():
                with st.expander(f"REQ #{r['id']}: {r['product_name']} ({r['quantity']})"):
                    st.write(f"**User:** {r['requested_by']} | **Note:** {r['notes']}")
                    c1, c2 = st.columns(2)
                    if c1.button("✅ Approve", key=f"app_{r['id']}"):
                         db.update_request_status(r['id'], "Approved"); st.rerun()
                    if c2.button("❌ Reject", key=f"rej_{r['id']}"):
                         db.update_request_status(r['id'], "Rejected"); st.rerun()

        st.dataframe(reqs, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with tab_market:
        st.subheader("🚀 Retail Marketing Hub")
        st.markdown("<div class='card-container'>", unsafe_allow_html=True)
        
        with st.expander("🎟️ Create Discount Coupon"):
            with st.form("new_coupon"):
                cc_code = st.text_input("Coupon Code (e.g., SUMMER10)")
                cc_type = st.selectbox("Type", ["Flat", "%"])
                cc_val = st.number_input("Value", min_value=1.0)
                cc_min = st.number_input("Min Bill Amount", min_value=0.0)
                cc_days = st.number_input("Validity (Days)", min_value=1, value=30)
                cc_lim = st.number_input("Total Usage Limit", min_value=1, value=100)
                # Added Bound Mobile
                cc_mob = st.text_input("Bound to Mobile (Optional)")
                
                if st.form_submit_button("Create Coupon"):
                    bound = cc_mob if cc_mob else None
                    if db.create_coupon(cc_code, cc_type, cc_val, cc_min, cc_days, cc_lim, bound_mobile=bound):
                        st.success("Coupon Created!")
                    else:
                        st.error("Error creating coupon (Code might exist)")
        
        st.markdown("##### Active Coupons")
        st.dataframe(db.get_all_coupons(), use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)
        
        st.markdown("<div class='card-container'>", unsafe_allow_html=True)
        st.subheader("🎲 Lucky Draw System")
        c1, c2, c3 = st.columns(3)
        with c1:
            ld_days = st.number_input("Sales Lookback (Days)", min_value=1, value=7)
        with c2:
            ld_min = st.number_input("Min Spend Eligibility", min_value=100, value=1000)
        with c3:
            ld_prize = st.text_input("Prize Description", value="Mystery Gift Box")
        
        if st.button("🎰 Run Lucky Draw"):
            with st.spinner("Analyzing sales data..."):
                time.sleep(1.5)
                winner = db.pick_lucky_winner(ld_days, ld_min, ld_prize)
                if winner:
                    st.markdown(utils.get_sound_html('celebration'), unsafe_allow_html=True)
                    st.balloons()
                    st.success(f"🎉 WINNER: {winner['name']} ({winner['mobile']})")
                    st.markdown(f"**Prize Won:** {ld_prize}")
                    db.log_activity(st.session_state['user'], "Lucky Draw", f"Winner selected: {winner['name']}")
                else:
                    st.warning("No eligible customers found for this criteria.")
        
        st.dataframe(db.get_lucky_draw_history(), use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("<div class='card-container'>", unsafe_allow_html=True)
        st.subheader("📢 Campaigns")
        with st.form("new_campaign"):
            cp_name = st.text_input("Campaign Name (e.g., Midnight Flash Sale)")
            cp_type = st.selectbox("Type", ["Flash Sale", "Festival Offer"])
            cp_start = st.text_input("Start Time (YYYY-MM-DD HH:MM:SS)", value=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            cp_end = st.text_input("End Time (YYYY-MM-DD HH:MM:SS)", value=(datetime.now() + pd.Timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S"))
            if st.form_submit_button("Launch Campaign"):
                db.create_campaign(cp_name, cp_type, cp_start, cp_end, {})
                st.success("Campaign Launched!")
        
        # Enhanced Campaign Display
        camps = db.get_all_campaigns()
        if not camps.empty:
            now = datetime.now()
            for _, cp in camps.iterrows():
                start_dt = datetime.strptime(cp['start_time'], "%Y-%m-%d %H:%M:%S")
                end_dt = datetime.strptime(cp['end_time'], "%Y-%m-%d %H:%M:%S")
                is_active = start_dt <= now <= end_dt
                
                style_class = "campaign-active" if is_active else "campaign-expired"
                status_txt = "ACTIVE" if is_active else "EXPIRED"
                status_col = "#10b981" if is_active else "#94a3b8"
                
                st.markdown(f"""
                <div class='{style_class}' style='padding:10px; border-radius:8px; background:rgba(255,255,255,0.05); margin-bottom:5px; border-left:4px solid {status_col};'>
                    <strong>{cp['name']}</strong> ({cp['type']})<br>
                    <span style='font-size:0.8em'>{cp['start_time']} - {cp['end_time']}</span>
                    <div style='float:right; font-weight:bold; color:{status_col}'>{status_txt}</div>
                </div>
                """, unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with tab_txns:
        st.markdown("<div class='card-container'>", unsafe_allow_html=True)
        # FIX 5: Transaction Traceability
        st.subheader("📜 Order & Payment Details")
        
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
        if not txns.empty:
            st.dataframe(
                txns[['id', 'timestamp', 'total_amount', 'status', 'payment_mode', 'operator', 'pos_id', 'customer_mobile', 'integrity_hash']], 
                use_container_width=True
            )
        else:
            st.info("No transactions found.")
        st.markdown("</div>", unsafe_allow_html=True)
        
    with tab_logs:
        st.markdown("<div class='card-container'>", unsafe_allow_html=True)
        # FIX 4: Logs View Control
        st.subheader("📝 System Audit Logs")
        
        logs = db.get_full_logs()
        
        # Access Control for Logs
        if st.session_state['role'] == 'Operator':
            st.warning("Restricted View: General logs only.")
        
        # Cancellation Log Section - Visible to Admin/Manager
        if st.session_state['role'] in ['Admin', 'Manager']:
            st.markdown("#### 🚫 Cancelled Orders Audit")
            cancel_audit = db.get_cancellation_audit_log()
            if not cancel_audit.empty:
                st.dataframe(cancel_audit, use_container_width=True)
            else:
                st.info("No cancellation events recorded.")
            
            st.markdown("---")
            st.markdown("#### All System Logs")
            st.dataframe(logs, use_container_width=True)
        else:
            # Operator view: Filter out cancellation details if sensitive, or just show general
            st.markdown("#### My Activity")
            op_logs = logs[logs['action'] != 'Undo Sale']
            st.dataframe(op_logs, use_container_width=True)
            
        st.markdown("</div>", unsafe_allow_html=True)

def user_profile_page():
    st.title("👤 My Profile")
    st.markdown("<div class='card-container'>", unsafe_allow_html=True)
    with st.form("profile_upd"):
        new_name = st.text_input("Full Name", value=st.session_state['full_name'])
        if st.form_submit_button("Update Profile"):
            db.update_fullname(st.session_state['user'], new_name)
            st.session_state['full_name'] = new_name
            db.log_activity(st.session_state['user'], "Profile Update", "Updated full name")
            st.success("Updated")
    st.divider()
    st.subheader("Change Password")
    with st.form("pass_chg"):
        old_p = st.text_input("Old Password", type="password")
        new_p = st.text_input("New Password", type="password")
        
        if new_p:
            score, label, color = utils.check_password_strength(new_p)
            st.markdown(f"<span style='color:{color}; font-weight:bold;'>Strength: {label}</span>", unsafe_allow_html=True)

        if st.form_submit_button("Change Password"):
            if db.verify_password(st.session_state['user'], old_p):
                if score < 2:
                    st.error("New password is too weak.")
                else:
                    db.update_password(st.session_state['user'], new_p)
                    db.log_activity(st.session_state['user'], "Password Change", "Updated password")
                    st.success("Password Changed Successfully")
            else: st.error("Incorrect Old Password")
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
