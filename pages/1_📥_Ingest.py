"""Ingest page — upload PDFs, chunk, embed, and build the persistent index."""

from __future__ import annotations

import html
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.embeddings import embed_documents  # noqa: E402
from src.config import DOCUMENTS_DIR  # noqa: E402
from src.ingest import chunk_pages, extract_pages, file_hash  # noqa: E402
from src.ui import card, info_banner, load_css, metric_tile, pill_row, section_header, render_sidebar  # noqa: E402
from src.vectorstore import (  # noqa: E402
    add_chunks,
    delete_source,
    get_source_chunks,
    ingested_hashes,
    reset_collection,
    stats,
)

# Page config and authentication are handled centrally in app.py


# Load dark glassmorphic layout styles
load_css()

section_header(
    "📥 Document Ingestion Pipeline",
    "Upload training PDFs, view text chunks, and update the searchable vector index.",
)

info_banner(
    "Secure Ingestion Control",
    "Upload PDFs to split them into overlapping passages. Duplicate checks prevent "
    "redundant processing, and progress stats keep you fully informed.",
    tone="info",
)

pill_row(["PDF Ingestion", "Recursive Chunking", "Embedding Engine", "Live Catalog"])

# --- Uploader --------------------------------------------------------------
uploaded = st.file_uploader(
    "Drop PDF files here",
    type=["pdf"],
    accept_multiple_files=True,
    help="Upload one or more training PDFs. Duplicate uploads are recognized and skipped automatically.",
)

build = st.button("🔧 Build Vector Index", disabled=not uploaded, use_container_width=False)

if build and uploaded:
    known_hashes = ingested_hashes()
    files_processed = 0
    chunks_added = 0
    duplicates = 0

    progress = st.progress(0.0, text="Starting…")
    total = len(uploaded)

    for i, file in enumerate(uploaded, start=1):
        label = f"Processing {file.name} ({i}/{total})"
        progress.progress((i - 1) / total, text=label)

        try:
            data = file.getvalue()
            digest = file_hash(data)

            if digest in known_hashes:
                duplicates += 1
                st.info(f"⏭️ **{file.name}** is already indexed — skipped duplicate.")
                progress.progress(i / total, text=label)
                continue

            pages = extract_pages(file)
            if not pages:
                st.warning(
                    f"⚠️ No extractable text found in **{file.name}** — skipped. "
                    "If this is a scanned/image PDF, make sure pytesseract and pdf2image OCR dependencies are installed."
                )
                progress.progress(i / total, text=label)
                continue

            chunks = chunk_pages(pages, file.name)
            embeddings = embed_documents([c["text"] for c in chunks])
            added = add_chunks(chunks, embeddings, digest)

            # Save uploaded PDF to DOCUMENTS_DIR
            try:
                save_path = Path(DOCUMENTS_DIR) / file.name
                save_path.parent.mkdir(parents=True, exist_ok=True)
                save_path.write_bytes(data)
            except Exception as e:
                st.warning(f"Could not save PDF copy to disk: {e}")

            known_hashes.add(digest)
            files_processed += 1
            chunks_added += added
            st.success(f"✅ **{file.name}** — Created {added} chunks from {len(pages)} pages.")

        except Exception as exc:  # noqa: BLE001
            st.error(f"❌ Failed to process **{file.name}**: {exc}")

        progress.progress(i / total, text=label)

    progress.progress(1.0, text="Index build complete!")

    st.write("")
    card(
        "Ingestion Summary",
        f"Files processed: <b>{files_processed}</b> &nbsp;·&nbsp; "
        f"Chunks added: <b>{chunks_added}</b> &nbsp;·&nbsp; "
        f"Duplicates skipped: <b>{duplicates}</b>",
        icon="📦",
    )

st.write("")

# --- Current index stats ---------------------------------------------------
section_header("Document Library Catalog", "Browse file details, view source chunks, or delete files.")

index = stats()

col1, col2 = st.columns(2)
with col1:
    metric_tile("Documents Ingested", index["sources"])
with col2:
    metric_tile("Total Vector Chunks", index["total_chunks"])

st.write("")

if not index["source_names"]:
    st.info("The vector store is currently empty. Use the uploader above to build your index.")
else:
    for doc in index["source_details"]:
        c_info, c_action = st.columns([5, 1])
        with c_info:
            st.markdown(
                f"<div style='margin-bottom: 0.5rem;'>"
                f"<span style='font-size: 1.1rem; font-weight: 600; color: var(--ts-text);'>📄 {html.escape(doc['name'])}</span><br>"
                f"<span style='color: var(--ts-text-secondary); font-size: 0.85rem;'>"
                f"{doc['pages']} pages &nbsp;·&nbsp; {doc['chunks']} chunks</span>"
                f"</div>",
                unsafe_allow_html=True,
            )
        with c_action:
            delete_key = f"del_{doc['name']}"
            if st.button("🗑️ Delete", key=delete_key, type="secondary", use_container_width=True):
                delete_source(doc["name"])
                try:
                    pdf_file = Path(DOCUMENTS_DIR) / doc["name"]
                    if pdf_file.exists():
                        pdf_file.unlink()
                except Exception:
                    pass
                st.toast(f"Deleted {doc['name']}")
                st.rerun()

        # Collapsible Chunk Browser
        with st.expander("👁️ Browse Chunks", expanded=False):
            chunks = get_source_chunks(doc["name"])
            if not chunks:
                st.caption("No chunks found in database.")
            else:
                st.caption(f"Showing all {len(chunks)} text chunks for this document.")
                for chunk in chunks:
                    st.markdown(
                        f"<div class='ts-nested-card'>"
                        f"<div style='font-size: 0.8rem; color: var(--ts-secondary); margin-bottom: 0.3rem; font-weight: 600;'>"
                        f"Page {chunk['page']} · Chunk {chunk['chunk_index']}</div>"
                        f"<div style='font-size: 0.9rem; color: var(--ts-text); line-height: 1.5;'>{html.escape(chunk['text'])}</div>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
        st.divider()

# --- Reset index (destructive) --------------------------------------------
st.write("")
section_header("Danger Zone", "Reset your database vector index permanently.")

if "confirm_reset" not in st.session_state:
    st.session_state.confirm_reset = False

st.markdown('<div class="ts-danger">', unsafe_allow_html=True)
if not st.session_state.confirm_reset:
    if st.button("🗑️ Reset entire database index", type="secondary"):
        st.session_state.confirm_reset = True
        st.rerun()
else:
    st.warning("Warning: This will delete ALL chunks from the vector database index. This cannot be undone.")
    c1, c2 = st.columns([1, 1])
    with c1:
        if st.button("Yes, reset index", type="secondary"):
            reset_collection()
            try:
                for pdf_file in Path(DOCUMENTS_DIR).glob("*.pdf"):
                    pdf_file.unlink()
            except Exception:
                pass
            st.session_state.confirm_reset = False
            st.success("Index reset complete.")
            st.rerun()
    with c2:
        if st.button("Cancel", type="secondary"):
            st.session_state.confirm_reset = False
            st.rerun()
st.markdown("</div>", unsafe_allow_html=True)

# --- Sidebar ---------------------------------------------------------------
render_sidebar(index)
