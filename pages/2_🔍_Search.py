"""Search page — semantic retrieval over the ingested document index."""

from __future__ import annotations

import html
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import TOP_K  # noqa: E402
from src.embeddings import embed_query  # noqa: E402
from src.llm import generate_rag_answer, list_local_models  # noqa: E402
from src.ui import empty_state, info_banner, load_css, pill_row, result_card, section_header, render_sidebar  # noqa: E402
from src.vectorstore import search, stats  # noqa: E402

# Page config and authentication are handled centrally in app.py


# Load dark glassmorphic layout styles
load_css()

section_header(
    "🔍 Semantic Search Laboratory",
    "Ask in natural language — filter sources, analyze confidence scores, and generate LLM answers.",
)

info_banner(
    "Intelligent Knowledge Search",
    "Enter a search query. Chunks matching the semantics are retrieved, scores are plotted, "
    "and matching keywords are highlighted. Enable local Qwen to compile a response.",
    tone="info",
)

pill_row(["Natural-language Queries", "Confidence Thresholds", "Source Filtering", "Qwen RAG"])

index = stats()
role = st.session_state.get("user_role", "trainee")

if index["total_chunks"] == 0:
    empty_state(
        "Your index is empty",
        "Head to the Ingest page to upload documents and build the vector index before searching." if role == "admin" else "Please ask an administrator to ingest documents to start searching.",
        icon="🗂️",
    )
    if role == "admin" and hasattr(st, "page_link"):
        st.page_link("pages/1_📥_Ingest.py", label="Go to Ingest →", icon="📥")
else:
    # Fetch local Ollama models once
    ollama_models = list_local_models()

    # --- Unified Search Control Cockpit ---
    with st.container(border=True):
        col_q, col_btn = st.columns([5, 1])
        with col_q:
            query = st.text_input(
                "Search Query",
                placeholder="e.g. What is the company onboarding process?",
                label_visibility="collapsed",
            )
        with col_btn:
            # Search action trigger button
            run_search = st.button("🔍 Run Search", use_container_width=True)

        # Advanced Settings and Filters Expander
        with st.expander("🛠️ Advanced Search Filters & RAG Settings", expanded=True):
            col_src, col_filt, col_llm = st.columns([2, 2, 2])

            with col_src:
                selected_sources = st.multiselect(
                    "Filter by Source Files",
                    options=index["source_names"],
                    default=None,
                    help="Select specific files to search. Leave empty to search all documents.",
                )

            with col_filt:
                threshold = st.slider(
                    "Similarity Threshold",
                    min_value=0.0,
                    max_value=1.0,
                    value=0.0,
                    step=0.05,
                    help="Filter out results with similarity scores below this threshold.",
                )
                top_k = st.slider(
                    "Retrieve Top-K Chunks",
                    min_value=1,
                    max_value=15,
                    value=TOP_K,
                    help="The maximum number of matching chunks to retrieve.",
                )

            with col_llm:
                if not ollama_models:
                    st.info("Local Ollama server not detected. Please start Ollama to enable Qwen RAG generation.")
                    enable_rag = False
                else:
                    enable_rag = st.toggle("Enable Qwen RAG Answer", value=True)
                    
                    default_idx = 0
                    for idx, m in enumerate(ollama_models):
                        if "qwen" in m.lower():
                            default_idx = idx
                            break

                    selected_model = st.selectbox(
                        "Local LLM Model",
                        options=ollama_models,
                        index=default_idx,
                        help="Choose which local model to use for answer synthesis.",
                    )

    # --- Search Execution & Output ---
    if run_search and query.strip():
        results = []
        try:
            with st.spinner("Embedding query and matching vectors…"):
                query_vec = embed_query(query.strip())
                results = search(
                    query_vec,
                    top_k=top_k,
                    source_filters=selected_sources if selected_sources else None,
                    threshold=threshold,
                )
        except Exception as exc:  # noqa: BLE001
            st.error(f"❌ Search failed: {exc}")

        if not results:
            st.warning("No matching passages found. Try rephrasing your query, selecting different sources, or lowering the similarity threshold.")
        else:
            # 1. RAG Answer Generation
            if enable_rag:
                st.write("")
                section_header("🤖 Local Qwen RAG Response", f"Synthesized using {selected_model}")
                with st.spinner(f"Qwen is compiling answer using {len(results)} chunks…"):
                    answer = generate_rag_answer(query.strip(), results, selected_model)
                
                st.markdown(
                    f"""
                    <div style='background: var(--ts-badge-bg); border: 1px solid var(--ts-badge-border); 
                    border-radius: 12px; padding: 1.4rem; margin-bottom: 1.8rem; box-shadow: var(--ts-shadow);'>
                        <div style='font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.08em; font-weight: 700; 
                        color: var(--ts-secondary); margin-bottom: 0.6rem;'>🤖 Qwen RAG Assistant</div>
                        <div style='color: var(--ts-text); font-size: 1.02rem; line-height: 1.6;'>
                    """,
                    unsafe_allow_html=True,
                )
                st.markdown(answer)
                st.markdown("</div></div>", unsafe_allow_html=True)
                st.write("")

            # 2. Similarity Scores Visualization Chart (Horizontal Meter List)
            st.write("")
            section_header("📊 Relevance Score Spectrum", "Interactive similarity strength ranking.")
            
            meters_html = []
            for idx, hit in enumerate(results, start=1):
                score_pct = hit["score"] * 100
                short_src = hit["source"] if len(hit["source"]) <= 45 else hit["source"][:42] + "..."
                meters_html.append(
                    f"<div style='margin-bottom: 1rem;'>"
                    f"<div style='display: flex; justify-content: space-between; font-size: 0.9rem; margin-bottom: 0.3rem;'>"
                    f"<span style='font-weight: 600;'>Match {idx} · 📄 {html.escape(short_src)} (Page {hit['page']})</span>"
                    f"<span style='font-weight: 700; color: var(--ts-secondary);'>{hit['score']:.3f}</span>"
                    f"</div>"
                    f"<div style='background: var(--ts-inner-bg); border-radius: 8px; height: 12px; overflow: hidden; width: 100%; border: 1px solid var(--ts-border);'>"
                    f"<div style='background: var(--ts-gradient); width: {score_pct}%; height: 100%; border-radius: 8px;'></div>"
                    f"</div>"
                    f"</div>"
                )
            
            st.markdown(
                f"<div class='ts-card' style='padding: 1.5rem; margin-bottom: 1.8rem;'>"
                f"{''.join(meters_html)}"
                f"</div>",
                unsafe_allow_html=True,
            )
            st.write("")

            # 3. Retrieved source text cards
            st.write("")
            section_header("📄 Retrieved Text Passages", f"Showing top {len(results)} matches.")
            for hit in results:
                result_card(
                    source=hit["source"],
                    page=hit["page"],
                    score=hit["score"],
                    text=hit["text"],
                    query=query.strip(),
                )

# --- Sidebar stats footer --------------------------------------------------
render_sidebar(index)
