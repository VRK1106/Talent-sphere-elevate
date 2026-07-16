"""Talent Sphere Elevate — Documents Catalog & Chunk Explorer Page."""

from __future__ import annotations

import sys
import html
import re
from pathlib import Path
import streamlit as st

# Ensure the project root is importable when Streamlit runs this file directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.ui import load_css, section_header, render_sidebar
from src.vectorstore import stats, get_source_chunks
from src.config import DOCUMENTS_DIR

# Load custom styles
load_css()

st.title("📄 Document Explorer")

# Fetch database stats
index = stats()
source_names = index["source_names"]

if not source_names:
    section_header("Active Document Catalog", "Browse active learning materials and document text chunks.")
    st.info("No documents have been ingested yet. Please contact an administrator to upload PDF training documents.")
else:
    section_header(
        "Active Document Catalog", 
        "Select an ingested file to view its page details, chunk distribution, and raw text content."
    )
    
    # Select document
    selected_doc = st.selectbox(
        "Select Document to Browse",
        options=source_names,
        index=0,
        help="Choose a document to explore its chunk layout."
    )
    
    if selected_doc:
        # Find detail stats
        doc_details = None
        for doc in index["source_details"]:
            if doc["name"] == selected_doc:
                doc_details = doc
                break
        
        role = st.session_state.get("user_role", "trainee")
        
        if role == "trainee":
            if doc_details:
                # Glassmorphic layout showing document stats and the Open PDF action
                col_stats, col_action = st.columns([1, 2])
                with col_stats:
                    st.markdown(
                        f"""
                        <div class="ts-metric ts-metric-card" style="padding: 1.2rem; border-radius: 12px; text-align: center; margin-bottom: 1rem;">
                            <div class="ts-metric-value" style="font-size: 1.8rem; font-weight: 700;">{doc_details['pages']}</div>
                            <div class="ts-metric-label" style="font-size: 0.8rem; text-transform: uppercase; font-weight: 600; margin-top: 0.3rem;">Total Pages</div>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
                with col_action:
                    pdf_path = Path(DOCUMENTS_DIR) / selected_doc
                    if pdf_path.exists():
                        try:
                            with open(pdf_path, "rb") as f:
                                pdf_bytes = f.read()
                            st.download_button(
                                label="📥 Open / Download PDF Document",
                                data=pdf_bytes,
                                file_name=selected_doc,
                                mime="application/pdf",
                                use_container_width=True,
                                type="primary",
                                help="Click to open or download the complete learning material."
                            )
                        except Exception as e:
                            st.error(f"Error loading PDF: {e}")
                    else:
                        st.info("ℹ️ The original PDF file copy is not available in the server's 'documents/' directory. Please copy the PDF file to that folder to enable downloading.")
        else:
            # Admin View: Display stats and chunk browser
            if doc_details:
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.markdown(
                        f"""
                        <div class="ts-metric ts-metric-card" style="padding: 1.2rem; border-radius: 12px; text-align: center; margin-bottom: 1rem;">
                            <div class="ts-metric-value" style="font-size: 1.8rem; font-weight: 700;">{doc_details['chunks']}</div>
                            <div class="ts-metric-label" style="font-size: 0.8rem; text-transform: uppercase; font-weight: 600; margin-top: 0.3rem;">Total Indexed Chunks</div>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
                with col2:
                    st.markdown(
                        f"""
                        <div class="ts-metric ts-metric-card" style="padding: 1.2rem; border-radius: 12px; text-align: center; margin-bottom: 1rem;">
                            <div class="ts-metric-value" style="font-size: 1.8rem; font-weight: 700;">{doc_details['pages']}</div>
                            <div class="ts-metric-label" style="font-size: 0.8rem; text-transform: uppercase; font-weight: 600; margin-top: 0.3rem;">Document Pages</div>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
                with col3:
                    avg_chunks = doc_details['chunks'] / doc_details['pages'] if doc_details['pages'] > 0 else 0
                    st.markdown(
                        f"""
                        <div class="ts-metric ts-metric-card" style="padding: 1.2rem; border-radius: 12px; text-align: center; margin-bottom: 1rem;">
                            <div class="ts-metric-value" style="font-size: 1.8rem; font-weight: 700;">{avg_chunks:.1f}</div>
                            <div class="ts-metric-label" style="font-size: 0.8rem; text-transform: uppercase; font-weight: 600; margin-top: 0.3rem;">Average Chunks / Page</div>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
            
            # Add Open PDF feature for Admins as well for convenience
            pdf_path = Path(DOCUMENTS_DIR) / selected_doc
            if pdf_path.exists():
                try:
                    with open(pdf_path, "rb") as f:
                        pdf_bytes = f.read()
                    st.download_button(
                        label="📥 Open / Download PDF Document",
                        data=pdf_bytes,
                        file_name=selected_doc,
                        mime="application/pdf",
                        use_container_width=False,
                        type="secondary",
                    )
                except Exception:
                    pass
            else:
                st.info("ℹ️ The original PDF file is not available in the server's 'documents/' directory. Please copy the PDF file there to enable downloading.")
                    
            st.write("")
            
            # Load chunks
            chunks = get_source_chunks(selected_doc)
            
            if not chunks:
                st.warning("No text chunks found for this document.")
            else:
                st.markdown("<div style='font-size: 1.15rem; font-weight: 600; color: var(--ts-primary); margin-bottom: 0.6rem;'>Search & Browse Chunks</div>", unsafe_allow_html=True)
                doc_query = st.text_input("Filter Chunks by Keyword", placeholder="Type a keyword to highlight matches...")
                
                if doc_query.strip():
                    filtered_chunks = []
                    for c in chunks:
                        if doc_query.strip().lower() in c["text"].lower():
                            filtered_chunks.append(c)
                    
                    st.write("")
                    st.markdown(f"🔍 Found **{len(filtered_chunks)}** matching chunks out of {len(chunks)} total:")
                    
                    max_display = 15
                    for c in filtered_chunks[:max_display]:
                        with st.container(border=True):
                            q = html.escape(doc_query.strip())
                            escaped_text = html.escape(c["text"])
                            highlighted_text = re.sub(
                                f"({re.escape(q)})",
                                r"<mark style='background: rgba(99, 102, 241, 0.3); color: var(--ts-primary); padding: 0.1rem 0.25rem; border-radius: 4px; font-weight: 600;'>\1</mark>",
                                escaped_text,
                                flags=re.IGNORECASE
                            )
                            st.markdown(
                                f"<div style='margin-bottom: 0.5rem; display: flex; justify-content: space-between;'>"
                                f"<span style='font-weight: 600; color: var(--ts-primary); font-size: 0.9rem;'>📄 Page {c['page']}</span>"
                                f"<span style='font-size: 0.8rem; color: var(--ts-text-secondary);'>Chunk Index: #{c['chunk_index']}</span>"
                                f"</div>"
                                f"<div style='font-size: 0.92rem; color: var(--ts-text); line-height: 1.6; word-break: break-word; font-family: sans-serif;'>"
                                f"{highlighted_text}"
                                f"</div>",
                                unsafe_allow_html=True
                            )
                    if len(filtered_chunks) > max_display:
                        st.info(f"Showing first {max_display} matches. Refine your keyword filter to see other specific content chunks.")
                else:
                    page_list = sorted(list(set(c["page"] for c in chunks)))
                    col_page_sel, col_page_info = st.columns([2.5, 4.5])
                    with col_page_sel:
                        selected_page = st.selectbox("Select Page to Browse", options=page_list, index=0)
                    
                    page_chunks = [c for c in chunks if c["page"] == selected_page]
                    with col_page_info:
                        st.write("")
                        st.write("")
                        st.markdown(f"Page **{selected_page}** contains **{len(page_chunks)}** indexed chunks.")
                    
                    st.write("")
                    
                    for c in page_chunks:
                        with st.container(border=True):
                            highlighted_text = html.escape(c["text"]).replace("\n", "<br>")
                            st.markdown(
                                f"<div style='margin-bottom: 0.5rem; display: flex; justify-content: space-between;'>"
                                f"<span style='font-weight: 600; color: var(--ts-primary); font-size: 0.9rem;'>📄 Page {c['page']}</span>"
                                f"<span style='font-size: 0.8rem; color: var(--ts-text-secondary);'>Chunk Index: #{c['chunk_index']}</span>"
                                f"</div>"
                                f"<div style='font-size: 0.92rem; color: var(--ts-text); line-height: 1.6; word-break: break-word; font-family: sans-serif;'>"
                                f"{highlighted_text}"
                                f"</div>",
                                unsafe_allow_html=True
                            )

# --- Sidebar branding ------------------------------------------------------
render_sidebar(index)
