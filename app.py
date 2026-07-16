"""Talent Sphere Elevate — Routing Entry Point.

Run with: ``streamlit run app.py``
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# Ensure the project root is importable when Streamlit runs this file directly.
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Initialize session state for authentication
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "current_user" not in st.session_state:
    st.session_state.current_user = None

# Consolidated page configuration
st.set_page_config(
    page_title="Talent Sphere Elevate",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded",
)

from src.users import init_db  # noqa: E402

# Initialize SQLite database
init_db()

# Declare all Page objects
login_page = st.Page("pages/0_🔐_Login.py", title="Login", icon="🔐")
home_page = st.Page("pages/home.py", title="Dashboard", icon="📊", default=True)
assistant_page = st.Page("pages/6_🤖_AI_Assistant.py", title="AI Assistant", icon="🤖")
documents_page = st.Page("pages/7_📄_Documents.py", title="Documents", icon="📄")
search_page = st.Page("pages/2_🔍_Search.py", title="Knowledge Search", icon="🔍")
user_mgmt_page = st.Page("pages/3_👥_User_Management.py", title="User Management", icon="👥")
ingest_page = st.Page("pages/1_📥_Ingest.py", title="Document Ingestion", icon="📥")
exams_page = st.Page("pages/4_📝_Exams.py", title="Exams", icon="📝")
announcements_page = st.Page("pages/5_📢_Announcements.py", title="Announcements", icon="📢")

# Perform routing dynamically
if not st.session_state.authenticated:
    # Restrict unauthenticated users to the login screen and hide the sidebar menu
    pg = st.navigation([login_page], position="hidden")
else:
    # Expose sections based on role
    role = st.session_state.get("user_role", "trainee")
    if role == "admin":
        pg = st.navigation({
            "🏆 Hub": [home_page],
            "💡 AI Workspace": [assistant_page, search_page],
            "📂 File Center": [documents_page, ingest_page],
            "🛠️ Management": [user_mgmt_page, exams_page, announcements_page]
        }, position="sidebar")
    else:
        pg = st.navigation({
            "🏆 Hub": [home_page],
            "💡 AI Workspace": [assistant_page, search_page],
            "📂 File Center": [documents_page],
            "📝 Learning": [exams_page, announcements_page]
        }, position="sidebar")

pg.run()