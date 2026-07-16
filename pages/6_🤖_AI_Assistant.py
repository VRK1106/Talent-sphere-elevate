"""Talent Sphere Elevate — Interactive AI Assistant Page with Chat Persistence."""

from __future__ import annotations

import sys
import html
import sqlite3
import datetime
from pathlib import Path
import streamlit as st

# Ensure the project root is importable when Streamlit runs this file directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.ui import load_css, section_header, render_sidebar
from src.vectorstore import stats, search
from src.embeddings import embed_query
from src.llm import list_local_models, generate_rag_answer, generate_chat_answer, GROQ_API_KEY
from src.users import _DB_PATH
from src.chats import (
    get_chat_sessions_for_user,
    get_chat_messages,
    create_chat_session,
    add_chat_message,
    delete_chat_session,
    rename_chat_session
)

# Load custom styles
load_css()

st.title("🤖 AI Assistant")

# Model configuration
ollama_models = list_local_models()
selected_model = None

# Sidebar stats & branding
index = stats()

# User Details
user_info = st.session_state.get("user_info", {}) or {}
emp_id = user_info.get("employee_id", "demo")

# Fetch chat sessions
user_sessions = get_chat_sessions_for_user(emp_id)

# Initialize active session in session state if not set
if "active_chat_session_id" not in st.session_state:
    st.session_state.active_chat_session_id = None

# Ensure active session exists, else select first or auto-create
if not st.session_state.active_chat_session_id:
    if user_sessions:
        st.session_state.active_chat_session_id = user_sessions[0]["session_id"]
    else:
        # Auto-create first chat session
        import uuid
        new_id = str(uuid.uuid4())
        create_chat_session(new_id, emp_id, "Welcome Conversation")
        st.session_state.active_chat_session_id = new_id
        # Refresh sessions list
        user_sessions = get_chat_sessions_for_user(emp_id)



# Load active messages
active_messages = get_chat_messages(st.session_state.active_chat_session_id)

# Top Controls Bar
with st.container(border=True):
    col_mode, col_model, col_clear = st.columns([2.5, 3.5, 1.5])
    
    with col_mode:
        chat_mode = st.radio(
            "Assistant Mode",
            options=["RAG (Document Guided)", "General Assistant"],
            index=0,
            horizontal=True,
            help="RAG mode answers queries based on your uploaded documents. General mode answers general questions."
        )
        
    with col_model:
        if not GROQ_API_KEY:
            st.warning("⚠️ Groq API Key not detected! Please add GROQ_API_KEY to your .env file.")
            selected_model = None
        else:
            default_idx = 0
            for idx, m in enumerate(ollama_models):
                if "llama-3.3" in m.lower() or "llama" in m.lower():
                    default_idx = idx
                    break
            selected_model = st.selectbox(
                "Groq AI Model",
                options=ollama_models,
                index=default_idx,
                help="Select which Groq model to converse with."
            )
            
    with col_clear:
        st.write("")  # padding
        if st.button("🧹 Clear Messages", use_container_width=True):
            # Delete messages in active session instead of clearing st.session_state
            try:
                conn = sqlite3.connect(str(_DB_PATH))
                cursor = conn.cursor()
                cursor.execute("DELETE FROM chat_messages WHERE session_id = ?", (st.session_state.active_chat_session_id,))
                conn.commit()
                conn.close()
            except Exception:
                pass
            st.rerun()

st.write("")

# Render Messages from SQLite history
for msg in active_messages:
    avatar = "👤" if msg["role"] == "user" else "🤖"
    with st.chat_message(msg["role"], avatar=avatar):
        st.write(msg["content"])
        if msg.get("sources"):
            with st.expander("📚 Sources Cited"):
                for idx, src in enumerate(msg["sources"], 1):
                    st.markdown(f"**[{idx}] {html.escape(src['source'])} (Page {src['page']})**")
                    st.caption(f"Similarity: {src['score']:.2%}")
                    st.markdown(f"> {html.escape(src['text'])}")

# Chat Input & Processing
if query := st.chat_input("Ask a question to your AI Coach...", disabled=(selected_model is None)):
    # 1. Save and display user message
    with st.chat_message("user", avatar="👤"):
        st.write(query)
    
    add_chat_message(st.session_state.active_chat_session_id, "user", query)
    
    # Auto-rename "Welcome Conversation" on first query
    current_title = "Welcome Conversation"
    for s in user_sessions:
        if s["session_id"] == st.session_state.active_chat_session_id:
            current_title = s["title"]
            break
            
    if current_title in ["Welcome Conversation", "New Conversation"] or current_title.startswith("Chat "):
        new_title = " ".join(query.split()[:4])
        if len(new_title) > 20:
            new_title = new_title[:18] + "..."
        if not new_title.strip():
            new_title = "Conversation"
            
        try:
            conn = sqlite3.connect(str(_DB_PATH))
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE chat_sessions SET title = ? WHERE session_id = ?",
                (new_title, st.session_state.active_chat_session_id)
            )
            conn.commit()
            conn.close()
        except Exception:
            pass

    # 2. Process and save assistant response
    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner("AI is thinking..."):
            sources = []
            if chat_mode == "RAG (Document Guided)":
                try:
                    # Embed and retrieve chunks
                    query_vec = embed_query(query.strip())
                    results = search(query_vec, top_k=4, threshold=0.1)
                    
                    if not results:
                        response = "No matching document context was found to guide an answer. Please upload documents first or check search configurations."
                    else:
                        response = generate_rag_answer(query.strip(), results, selected_model)
                        sources = results
                except Exception as e:
                    response = f"An error occurred during retrieval/generation: {e}"
            else:
                # General conversation mode
                system_prompt = (
                    "You are a helpful, encouraging learning coach for 'Talent Sphere Elevate', an advanced corporate training platform. "
                    "Provide clear, professional explanation, code example, or training advice depending on the trainee's question."
                )
                response = generate_chat_answer(query.strip(), selected_model, system_prompt)
                
            st.write(response)
            
            # Show sources inside the bubble immediately on generation
            if sources:
                with st.expander("📚 Sources Cited"):
                    for idx, src in enumerate(sources, 1):
                        st.markdown(f"**[{idx}] {html.escape(src['source'])} (Page {src['page']})**")
                        st.caption(f"Similarity: {src['score']:.2%}")
                        st.markdown(f"> {html.escape(src['text'])}")
                        
    # Save Assistant message
    serialized_sources = [{"source": s["source"], "page": s["page"], "text": s["text"], "score": s["score"]} for s in sources]
    add_chat_message(st.session_state.active_chat_session_id, "assistant", response, serialized_sources)
    st.rerun()

# Render standard sidebar branding & stats with Chat History nested under AI Assistant
render_sidebar(index, show_chat_history=True)
