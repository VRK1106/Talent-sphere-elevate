"""Login page — authenticate users before accessing the Talent Sphere Elevate dashboard."""

from __future__ import annotations

import hashlib
import html
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.ui import load_css, render_sidebar  # noqa: E402
from src.vectorstore import stats  # noqa: E402

# Page config is handled in app.py


# Load dark glassmorphic layout styles
load_css()

from src.users import verify_user  # noqa: E402

def _verify_credentials(username: str, password: str) -> dict[str, Any] | None:
    """Check username/password against the SQLite database."""
    return verify_user(username, password)


# ---------------------------------------------------------------------------
# Session state initialization
# ---------------------------------------------------------------------------
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "current_user" not in st.session_state:
    st.session_state.current_user = None


# Execution block moved to the bottom of the file to ensure functions are defined first



# ===========================================================================
# View: Authenticated user
# ===========================================================================
def _render_authenticated_view() -> None:
    """Show a welcome dashboard for already-logged-in users."""
    index = stats()

    # Hero
    st.markdown(
        f"""
        <div class="ts-hero">
            <div class="ts-hero-title">Welcome back, {html.escape(st.session_state.current_user)} 👋</div>
            <div class="ts-hero-subtitle">
                You are authenticated and ready to explore the Talent Sphere Elevate platform.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.write("")

    # Quick navigation cards
    role = st.session_state.get("user_role", "trainee")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(
            """
            <div class="ts-card" style="text-align: center; cursor: pointer;">
                <div class="ts-card-icon" style="font-size: 2.5rem;">🏠</div>
                <div class="ts-card-title">Home Dashboard</div>
                <div class="ts-card-body">View index metrics, document catalog, and system overview.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Go to Home", key="nav_home", use_container_width=True):
            st.switch_page("pages/home.py")

    with col2:
        if role == "admin":
            st.markdown(
                """
                <div class="ts-card" style="text-align: center;">
                    <div class="ts-card-icon" style="font-size: 2.5rem;">📥</div>
                    <div class="ts-card-title">Document Ingestion</div>
                    <div class="ts-card-body">Upload PDFs, chunk, embed, and build the vector index.</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button("Go to Ingest", key="nav_ingest", use_container_width=True):
                st.switch_page("pages/1_📥_Ingest.py")
        else:
            st.markdown(
                """
                <div class="ts-card" style="text-align: center;">
                    <div class="ts-card-icon" style="font-size: 2.5rem;">🤖</div>
                    <div class="ts-card-title">AI Assistant</div>
                    <div class="ts-card-body">Ask questions and get help from the Qwen AI assistant.</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button("Go to Assistant", key="nav_assistant", use_container_width=True):
                st.switch_page("pages/6_🤖_AI_Assistant.py")

    with col3:
        st.markdown(
            """
            <div class="ts-card" style="text-align: center;">
                <div class="ts-card-icon" style="font-size: 2.5rem;">🔍</div>
                <div class="ts-card-title">Semantic Search</div>
                <div class="ts-card-body">Query documents with natural language and LLM-powered RAG.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Go to Search", key="nav_search", use_container_width=True):
            st.switch_page("pages/2_🔍_Search.py")

    st.write("")
    st.divider()

    # Logout
    col_logout, _ = st.columns([1, 4])
    with col_logout:
        if st.button("🚪 Logout", use_container_width=True, type="secondary"):
            st.session_state.authenticated = False
            st.session_state.current_user = None
            st.rerun()

    # Sidebar
    render_sidebar(index)


# ===========================================================================
# View: Login form
# ===========================================================================
def _render_login_form() -> None:
    """Render the glassmorphic login form."""
    index = stats()

    # Centered layout using columns
    col_left, col_center, col_right = st.columns([1, 2, 1])

    with col_center:
        st.markdown('<div style="height: 3rem;"></div>', unsafe_allow_html=True)

        # Logo / branding
        st.markdown(
            """
            <div style="text-align: center; margin-bottom: 2rem;">
                <span style="font-size: 3.5rem;">🚀</span>
                <div style="font-size: 1.8rem; font-weight: 800; 
                            background: linear-gradient(135deg, #6366f1 0%, #06b6d4 100%); 
                            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
                            margin-top: 0.5rem;">
                    Talent Sphere Elevate
                </div>
                <div style="font-size: 0.85rem; color: var(--ts-text-secondary); margin-top: 0.3rem;">
                    Sign in to access your knowledge discovery platform
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Login card wrapper using native Streamlit container with border
        with st.container(border=True):
            # --- Login form fields ---
            username = st.text_input(
                "Username",
                placeholder="Enter your username",
                key="login_username",
                label_visibility="visible",
            )

            password = st.text_input(
                "Password",
                placeholder="Enter your password",
                type="password",
                key="login_password",
                label_visibility="visible",
            )

            col_btn, _ = st.columns([1, 2])
            with col_btn:
                login_clicked = st.button("🔐 Sign In", use_container_width=True, type="primary")

            # --- Handle login ---
            if login_clicked:
                if not username or not password:
                    st.error("Please enter both username and password.")
                else:
                    user_info = _verify_credentials(username, password)
                    if user_info:
                        st.session_state.authenticated = True
                        st.session_state.current_user = user_info["full_name"]
                        st.session_state.user_role = user_info["role"]
                        st.session_state.user_info = user_info
                        st.success(f"✅ Welcome, **{html.escape(user_info['full_name'])}**! Redirecting…")
                        st.rerun()
                    else:
                        st.error("Invalid username or password. Please try again.")

            # Demo credentials hint
            st.markdown(
                """
                <div style="text-align: center; margin-top: 1.2rem; font-size: 0.78rem; color: var(--ts-text-muted);">
                    🔑 Demo credentials: <b>admin</b> / <b>admin123</b> &nbsp;|&nbsp; <b>demo</b> / <b>demo123</b>
                </div>
                """,
                unsafe_allow_html=True,
            )

    # Sidebar is not rendered on login page to keep the menu hidden
    pass

# ---------------------------------------------------------------------------
# Execution: Show the appropriate view based on authentication state
# ---------------------------------------------------------------------------
if st.session_state.authenticated:
    _render_authenticated_view()
else:
    _render_login_form()