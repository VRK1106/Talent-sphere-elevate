"""Talent Sphere Elevate — Announcements Dashboard Page."""

from __future__ import annotations

import sys
from pathlib import Path
import html

import streamlit as st

# Ensure the project root is importable when Streamlit runs this file directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.ui import load_css, section_header, render_sidebar
from src.vectorstore import stats
from src.exams import get_all_announcements, add_announcement, delete_announcement

# Load custom styles
load_css()

st.title("📢 Announcements")

# Fetch active user details
role = st.session_state.get("user_role", "trainee")
user_name = st.session_state.get("current_user", "Trainee")

if role == "admin":
    section_header(
        "Announcements Cockpit", 
        "Publish system-wide notifications, training notices, or timeline changes to all trainees."
    )
    
    # 1. Publish announcement form
    with st.container(border=True):
        st.markdown("<div style='font-size: 1.1rem; font-weight: 600; color: var(--ts-primary); margin-bottom: 1rem;'>Publish Announcement</div>", unsafe_allow_html=True)
        
        a_title = st.text_input("Title", placeholder="e.g. Schedule Update: RAG Workshop")
        a_content = st.text_area("Content", placeholder="Enter description or notice text here...")
        
        col_btn, _ = st.columns([1.5, 5])
        with col_btn:
            publish_clicked = st.button("📢 Publish Now", type="primary", use_container_width=True)
            
        if publish_clicked:
            if not a_title.strip():
                st.error("Please enter an announcement title.")
            elif not a_content.strip():
                st.error("Please enter announcement content.")
            else:
                if add_announcement(a_title, a_content):
                    st.success("Announcement published successfully!")
                    st.rerun()
                else:
                    st.error("Failed to publish announcement. Database error.")

    st.write("")
    
    # 2. Existing announcements directory
    section_header("Active Board Notices", "Current notices shown to all users on their dashboards.")
    announcements = get_all_announcements()
    
    if not announcements:
        st.info("No active announcements found on the board.")
    else:
        with st.container(border=True):
            for a in announcements:
                col_info, col_act = st.columns([5, 1])
                with col_info:
                    formatted_content = html.escape(a['content']).replace('\n', '<br>')
                    st.markdown(
                        f"<div style='margin-bottom: 0.2rem;'>"
                        f"<span style='font-size: 1.05rem; font-weight: 600; color: var(--ts-text);'>📢 {html.escape(a['title'])}</span>"
                        f"</div>"
                        f"<div style='font-size: 0.8rem; color: var(--ts-text-muted); margin-bottom: 0.6rem;'>"
                        f"Published: <b>{a['created_at']}</b>"
                        f"</div>"
                        f"<div style='font-size: 0.92rem; color: var(--ts-text-secondary); line-height: 1.5;'>"
                        f"{formatted_content}"
                        f"</div>",
                        unsafe_allow_html=True
                    )
                with col_act:
                    del_key = f"del_ann_{a['announcement_id']}"
                    if st.button("🗑️ Delete", key=del_key, type="secondary", use_container_width=True):
                        if delete_announcement(a["announcement_id"]):
                            st.toast(f"Deleted announcement: {a['title']}")
                            st.rerun()
                        else:
                            st.error("Failed to delete announcement.")
                            
                st.divider()

else:
    # Trainee View
    section_header(
        f"Notice Board for {user_name}", 
        "Read latest broadcast updates and timeline announcements from the administrators."
    )
    
    announcements = get_all_announcements()
    
    if not announcements:
        st.info("No announcements posted yet. Check back later!")
    else:
        with st.container(border=True):
            for a in announcements:
                formatted_content = html.escape(a['content']).replace('\n', '<br>')
                st.markdown(
                    f"<div style='margin-bottom: 0.2rem;'>"
                    f"<span style='font-size: 1.1rem; font-weight: 600; color: var(--ts-primary);'>📢 {html.escape(a['title'])}</span>"
                    f"</div>"
                    f"<div style='font-size: 0.8rem; color: var(--ts-text-muted); margin-bottom: 0.8rem;'>"
                    f"Published: <b>{a['created_at']}</b>"
                    f"</div>"
                    f"<div style='font-size: 0.95rem; color: var(--ts-text); line-height: 1.6;'>"
                    f"{formatted_content}"
                    f"</div>",
                    unsafe_allow_html=True
                )
                st.divider()

# --- Sidebar branding ------------------------------------------------------
index = stats()
render_sidebar(index)
