"""User Management page — provision trainee accounts and manage directory."""

from __future__ import annotations

import html
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.ui import load_css, render_sidebar, section_header, card
from src.users import add_user, delete_user, get_all_users
from src.vectorstore import stats

# Load dark glassmorphic layout styles
load_css()

# Admin permission guard
if st.session_state.get("user_role", "trainee") != "admin":
    st.error("🚫 Access Denied. Only administrators are allowed to view this page.")
    st.stop()

section_header(
    "👥 User Management",
    "Provision trainee accounts. Credentials are stored securely (hashed) in SQLite.",
)

# Initialize page navigation tab in session state
if "user_mgmt_tab" not in st.session_state:
    st.session_state.user_mgmt_tab = "Create user"

# Custom Segmented Toggle Buttons
col_tab1, col_tab2, _ = st.columns([1.2, 1.2, 5])
with col_tab1:
    btn_type = "primary" if st.session_state.user_mgmt_tab == "Create user" else "secondary"
    if st.button("Create user", key="tab_create", use_container_width=True, type=btn_type):
        st.session_state.user_mgmt_tab = "Create user"
        st.rerun()

with col_tab2:
    btn_type = "primary" if st.session_state.user_mgmt_tab == "Manage users" else "secondary"
    if st.button("Manage users", key="tab_manage", use_container_width=True, type=btn_type):
        st.session_state.user_mgmt_tab = "Manage users"
        st.rerun()

st.write("")

# ---------------------------------------------------------------------------
# VIEW: Create user
# ---------------------------------------------------------------------------
if st.session_state.user_mgmt_tab == "Create user":
    with st.container(border=True):
        col_left, col_right = st.columns(2)
        
        with col_left:
            employee_id = st.text_input(
                "Employee ID",
                placeholder="EMP-1024",
                help="Unique identifier for the employee/trainee."
            )
            full_name = st.text_input(
                "Full name",
                placeholder="Priya Sharma",
                help="Official full name of the employee."
            )
            
        with col_right:
            email = st.text_input(
                "Email",
                placeholder="priya@company.com",
                help="Corporate email address."
            )
            domain = st.selectbox(
                "Training domain",
                options=["general", "development", "testing", "design", "security"],
                index=0,
                help="Assigned functional domain."
            )
            
        # Password options
        if "password_mode" not in st.session_state:
            st.session_state.password_mode = "Auto-generate"
            
        st.write("")
        st.markdown(
            "<div style='font-size: 0.85rem; font-weight: 600; color: var(--ts-text); margin-bottom: 0.5rem;'>Password</div>",
            unsafe_allow_html=True
        )
        col_pw1, col_pw2, _ = st.columns([1.2, 1.2, 4])
        with col_pw1:
            pw_type = "primary" if st.session_state.password_mode == "Auto-generate" else "secondary"
            if st.button("Auto-generate", key="pw_auto", use_container_width=True, type=pw_type):
                st.session_state.password_mode = "Auto-generate"
                st.rerun()
                
        with col_pw2:
            pw_type = "primary" if st.session_state.password_mode == "Set manually" else "secondary"
            if st.button("Set manually", key="pw_manual", use_container_width=True, type=pw_type):
                st.session_state.password_mode = "Set manually"
                st.rerun()
                
        st.write("")
        manual_password = st.text_input(
            "Manual password (min 8 chars)",
            placeholder="Leave blank if auto-generating",
            type="password",
            disabled=(st.session_state.password_mode == "Auto-generate")
        )
        
        st.write("")
        col_btn, _ = st.columns([1.5, 5])
        with col_btn:
            create_clicked = st.button("👤 Create user", type="primary", use_container_width=True)
            
        if create_clicked:
            if not employee_id.strip():
                st.error("Please enter an Employee ID.")
            elif not email.strip():
                st.error("Please enter an Email address.")
            elif not full_name.strip():
                st.error("Please enter a Full name.")
            else:
                if st.session_state.password_mode == "Auto-generate":
                    # Generate password based on first name + prefix
                    first_part = full_name.strip().split()[0].capitalize() if full_name.strip().split() else "User"
                    generated_password = f"{first_part}@123"
                else:
                    generated_password = manual_password.strip()
                    
                if len(generated_password) < 8:
                    st.error("Password must be at least 8 characters long.")
                else:
                    success, msg = add_user(
                        employee_id=employee_id.strip(),
                        email=email.strip(),
                        full_name=full_name.strip(),
                        domain=domain,
                        password_plain=generated_password,
                        role="trainee"
                    )
                    if success:
                        st.session_state.last_created_user = {
                            "email": email.strip(),
                            "password": generated_password,
                            "name": full_name.strip()
                        }
                        st.rerun()
                    else:
                        st.error(msg)
                        
        # Display last created credentials if available
        if "last_created_user" in st.session_state:
            st.write("")
            c_info = st.session_state.last_created_user
            first_name = c_info["name"].split()[0] if c_info["name"].split() else "the user"
            
            st.success("User created successfully.")
            
            st.markdown(
                f"""
                <div style='background: var(--ts-badge-bg); border: 1px solid var(--ts-badge-border); 
                border-radius: 12px; padding: 1.4rem; margin-top: 1rem; box-shadow: var(--ts-shadow);'>
                    <div style='font-weight: 700; color: var(--ts-primary); margin-bottom: 0.8rem; font-size: 1rem;'>
                        Share these credentials with {html.escape(first_name)} now — the password is not stored in plain text and cannot be shown again.
                    </div>
                    <ul style='color: var(--ts-text); font-size: 0.95rem; margin-left: 1.2rem; line-height: 1.6;'>
                        <li>Email: <b>{html.escape(c_info['email'])}</b></li>
                        <li>Password: <b>{html.escape(c_info['password'])}</b></li>
                    </ul>
                </div>
                """,
                unsafe_allow_html=True
            )
            
            if st.button("Dismiss / Create Another"):
                del st.session_state.last_created_user
                st.rerun()

# ---------------------------------------------------------------------------
# VIEW: Manage users
# ---------------------------------------------------------------------------
else:
    users = get_all_users()
    
    if not users:
        st.info("No registered users found in the system.")
    else:
        with st.container(border=True):
            for u in users:
                col_info, col_act = st.columns([5, 1])
                with col_info:
                    st.markdown(
                        f"<div style='margin-bottom: 0.2rem;'>"
                        f"<span style='font-size: 1.05rem; font-weight: 600; color: var(--ts-text);'>👤 {html.escape(u['full_name'])}</span> "
                        f"<span class='ts-badge-outline' style='margin-left: 0.5rem;'>{u['role'].upper()}</span>"
                        f"</div>"
                        f"<div style='font-size: 0.85rem; color: var(--ts-text-secondary);'>"
                        f"ID: <b>{html.escape(u['employee_id'])}</b> &nbsp;·&nbsp; "
                        f"Email: <b>{html.escape(u['email'])}</b> &nbsp;·&nbsp; "
                        f"Domain: <b>{html.escape(u['domain'])}</b>"
                        f"<br><span style='margin-top: 0.4rem; display: inline-block; color: var(--ts-primary); font-weight: 500;'>"
                        f"🔑 Credentials: &nbsp;Username: <code class='ts-code-highlight'>{html.escape(u['employee_id'])}</code> &nbsp;·&nbsp; "
                        f"Password: <code class='ts-code-highlight'>{html.escape(u.get('password_plain') or 'demo123')}</code>"
                        f"</span>"
                        f"</div>",
                        unsafe_allow_html=True
                    )
                with col_act:
                    # Protect default admin from deletion
                    if u["employee_id"] == "admin":
                        st.markdown(
                            "<div style='text-align: center; color: var(--ts-text-muted); font-size: 0.85rem; padding-top: 0.5rem;'>Protected</div>",
                            unsafe_allow_html=True
                        )
                    else:
                        del_key = f"del_usr_{u['employee_id']}"
                        if st.button("🗑️ Delete", key=del_key, type="secondary", use_container_width=True):
                            if delete_user(u["employee_id"]):
                                st.toast(f"Deleted user {u['full_name']}")
                                st.rerun()
                            else:
                                st.error(f"Failed to delete {u['full_name']}")
                                
                st.divider()

# --- Sidebar ---------------------------------------------------------------
index = stats()
render_sidebar(index)
