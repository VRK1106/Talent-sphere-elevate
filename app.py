"""Talent Sphere Elevate — Flask MVC Route Controller Entry Point."""

from __future__ import annotations

import os
import sys
import uuid
import json
import sqlite3
import re
from datetime import datetime
from functools import wraps
from pathlib import Path

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    Response,
    jsonify,
    stream_with_context,
    send_from_directory
)

# Ensure the project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.users import init_db, verify_user, get_all_users, get_active_users_count, _DB_PATH
from src.exams import (
    init_exams_db,
    get_all_exams,
    add_exam,
    delete_exam,
    assign_exam,
    get_assignments_for_exam,
    get_assignments_for_trainee,
    get_assignment_by_id,
    submit_exam_answers,
    get_all_announcements,
    add_announcement,
    delete_announcement
)
from src.chats import (
    init_chats_db,
    get_chat_sessions_for_user,
    get_chat_messages,
    create_chat_session,
    add_chat_message,
    rename_chat_session,
    delete_chat_session,
    get_global_chat_stats
)
from src.config import EMBEDDING_MODEL, DOCUMENTS_DIR
from src.vectorstore import stats, get_source_chunks, search, get_collection
from src.llm import list_local_models, generate_chat_answer, generate_rag_answer, GROQ_API_KEY

# Initialize databases
init_db()
init_exams_db()
init_chats_db()

app = Flask(__name__, static_folder='assets', static_url_path='/assets')
app.secret_key = os.environ.get('SECRET_KEY', 'talent-sphere-elevate-secret-key-12345')

# Helper: clean LLM output to parse as JSON
def clean_json_response(raw_resp: str) -> str:
    resp = raw_resp.strip()
    if resp.startswith("```"):
        match = re.match(r"^```(?:json)?\s*", resp)
        if match:
            resp = resp[match.end():]
        if resp.endswith("```"):
            resp = resp[:-3]
    return resp.strip()

# Login guard decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('authenticated'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Context Processor for base template and other views
@app.context_processor
def inject_global_data():
    if not session.get('authenticated'):
        return {}
    
    path = request.path
    active_page = 'dashboard'
    if path.startswith('/assistant'):
        active_page = 'assistant'
    elif path.startswith('/search'):
        active_page = 'search'
    elif path.startswith('/documents'):
        active_page = 'documents'
    elif path.startswith('/ingest'):
        active_page = 'ingest'
    elif path.startswith('/user_management'):
        active_page = 'user_management'
    elif path.startswith('/exams'):
        active_page = 'exams'
    elif path.startswith('/announcements'):
        active_page = 'announcements'
        
    sqlite_ok = False
    try:
        conn = sqlite3.connect(str(_DB_PATH))
        c = conn.cursor()
        c.execute("SELECT 1")
        c.fetchone()
        conn.close()
        sqlite_ok = True
    except Exception:
        pass
        
    chroma_ok = False
    try:
        from src.vectorstore import get_client
        client = get_client()
        client.heartbeat()
        chroma_ok = True
    except Exception:
        pass
        
    ollama_ok = False
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1.0)
        s.connect(('localhost', 11434))
        s.close()
        ollama_ok = True
    except Exception:
        pass
        
    chroma_stats = stats()
    
    current_user = session.get('current_user', 'User')
    user_info = session.get('user_info', {})
    employee_id = user_info.get('employee_id', '')
    role = session.get('user_role', 'trainee')
    
    names = current_user.split()
    user_initials = "".join([n[0].upper() for n in names if n]) if names else "U"
    
    progress_pct = 0
    progress_text = "0% Completed"
    try:
        conn = sqlite3.connect(str(_DB_PATH))
        c = conn.cursor()
        if role == 'admin':
            c.execute("SELECT COUNT(*) FROM assignments")
            total = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM assignments WHERE status = 'completed'")
            completed = c.fetchone()[0]
        else:
            c.execute("SELECT COUNT(*) FROM assignments WHERE trainee_id = ?", (employee_id,))
            total = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM assignments WHERE trainee_id = ? AND status = 'completed'", (employee_id,))
            completed = c.fetchone()[0]
        conn.close()
        
        if total > 0:
            progress_pct = int((completed / total) * 100)
            progress_text = f"{progress_pct}% ({completed}/{total} Completed)"
        else:
            progress_pct = 0
            progress_text = "No Assignments"
    except Exception:
        pass
        
    user_sessions = get_chat_sessions_for_user(employee_id) if employee_id else []
    active_chat_session_id = session.get('active_chat_session_id')
    
    show_chat_history = (active_page == 'assistant')
    ollama_models = list_local_models()
    
    def get_all_trainees():
        return [u for u in get_all_users() if u["role"] == "trainee"]
        
    def get_all_completed_submissions():
        exams_list = get_all_exams()
        all_results = []
        for e in exams_list:
            all_results.extend(get_assignments_for_exam(e["exam_id"]))
        return [r for r in all_results if r["status"] == "completed"]
        
    def get_trainee_assigned_exams(trainee_id):
        return [a for a in get_assignments_for_trainee(trainee_id) if a["status"] == "assigned"]
        
    def get_trainee_completed_exams(trainee_id):
        return [a for a in get_assignments_for_trainee(trainee_id) if a["status"] == "completed"]
    
    return {
        'active_page': active_page,
        'health': {
            'sqlite_ok': sqlite_ok,
            'chroma_ok': chroma_ok,
            'ollama_ok': ollama_ok
        },
        'stats': chroma_stats,
        'user_initials': user_initials,
        'progress_pct': progress_pct,
        'progress_text': progress_text,
        'user_sessions': user_sessions,
        'active_chat_session_id': active_chat_session_id,
        'show_chat_history': show_chat_history,
        'ollama_models': ollama_models,
        'groq_api_key': GROQ_API_KEY,
        'get_all_trainees': get_all_trainees,
        'get_assignments_for_exam': get_assignments_for_exam,
        'get_all_completed_submissions': get_all_completed_submissions,
        'get_trainee_assigned_exams': get_trainee_assigned_exams,
        'get_trainee_completed_exams': get_trainee_completed_exams
    }

# AUTHENTICATION
@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('authenticated'):
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = verify_user(username, password)
        if user:
            session['authenticated'] = True
            session['current_user'] = user['full_name']
            session['user_role'] = user['role']
            session['user_info'] = user
            
            sessions = get_chat_sessions_for_user(user['employee_id'])
            if sessions:
                session['active_chat_session_id'] = sessions[0]['session_id']
            else:
                session_id = str(uuid.uuid4())
                create_chat_session(session_id, user['employee_id'], "Welcome Conversation")
                session['active_chat_session_id'] = session_id
            return redirect(url_for('dashboard'))
        else:
            flash("Invalid Employee ID or Password")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# DASHBOARD
@app.route('/')
@login_required
def dashboard():
    role = session.get('user_role', 'trainee')
    user_info = session.get('user_info', {}) or {}
    emp_id = user_info.get('employee_id', 'demo')
    
    index_stats = stats()
    
    if role == 'admin':
        users = get_all_users()
        trainees = [u for u in users if u["role"] == "trainee"]
        active_now = get_active_users_count(hours=1)
        
        doc_count = index_stats["sources"]
        chunk_count = index_stats["total_chunks"]
        
        chat_stats = get_global_chat_stats()
        total_sessions = chat_stats["total_sessions"]
        total_messages = chat_stats["total_messages"]
        
        exams_list = get_all_exams()
        all_submissions = []
        for e in exams_list:
            all_submissions.extend(get_assignments_for_exam(e["exam_id"]))
        completed_subs = [s for s in all_submissions if s["status"] == "completed"]
        
        avg_score_pct = 0.0
        if completed_subs:
            exam_marks_map = {e["exam_id"]: e["total_marks"] for e in exams_list}
            sum_pcts = 0.0
            for sub in completed_subs:
                total_m = exam_marks_map.get(sub["exam_id"], 100)
                score = sub["score"] or 0.0
                sum_pcts += (score / total_m * 100.0) if total_m > 0 else 0.0
            avg_score_pct = sum_pcts / len(completed_subs)
            
        try:
            conn = sqlite3.connect(str(_DB_PATH))
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM chat_messages WHERE role = 'assistant' AND sources IS NOT NULL AND sources != '[]' AND sources != ''")
            rag_use_count = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM chat_messages WHERE role = 'assistant' AND (sources IS NULL OR sources = '[]' OR sources = '')")
            general_use_count = c.fetchone()[0]
            conn.close()
        except Exception:
            rag_use_count, general_use_count = 0, 0
            
        sum_use = rag_use_count + general_use_count
        rag_ratio = (rag_use_count / sum_use * 100.0) if sum_use > 0 else 0.0
        
        msg_data = chat_stats["messages_per_day"]
        if not msg_data:
            import datetime
            today = datetime.date.today()
            msg_data = [
                {"date": (today - datetime.timedelta(days=i)).strftime("%Y-%m-%d"), "count": c}
                for i, c in enumerate([10, 15, 12, 22, 19, 14, 20])
            ]
            msg_data.reverse()
        
        chat_dates = [d["date"] for d in msg_data]
        chat_counts = [d["count"] for d in msg_data]
        
        scores = []
        if completed_subs:
            exam_marks_map = {e["exam_id"]: e["total_marks"] for e in exams_list}
            for sub in completed_subs:
                t_marks = exam_marks_map.get(sub["exam_id"], 100)
                score_val = sub["score"] or 0.0
                scores.append((score_val / t_marks * 100.0) if t_marks > 0 else 0.0)
        else:
            scores = [15, 42, 58, 62, 75, 80, 85, 92]
            
        score_ranges = ["0-20%", "21-40%", "41-60%", "61-80%", "81-100%"]
        score_counts = [0, 0, 0, 0, 0]
        for s in scores:
            if s <= 20:
                score_counts[0] += 1
            elif s <= 40:
                score_counts[1] += 1
            elif s <= 60:
                score_counts[2] += 1
            elif s <= 80:
                score_counts[3] += 1
            else:
                score_counts[4] += 1
                
        trainee_rows = []
        domain_map = {}
        for t in trainees:
            t_emp_id = t["employee_id"]
            assignments = get_assignments_for_trainee(t_emp_id)
            pending = len([a for a in assignments if a["status"] == "assigned"])
            completed = len([a for a in assignments if a["status"] == "completed"])
            
            sub_pcts = []
            for a in assignments:
                if a["status"] == "completed":
                    total_m = a.get("total_marks", 100)
                    score_val = a.get("score") or 0.0
                    sub_pcts.append((score_val / total_m * 100.0) if total_m > 0 else 0.0)
            avg_val = f"{sum(sub_pcts)/len(sub_pcts):.1f}%" if sub_pcts else "No Submissions"
            last_active = t.get("last_active") or "Never Active"
            
            trainee_rows.append({
                "ID": t_emp_id,
                "Name": t["full_name"],
                "Domain": t["domain"].upper(),
                "Email": t["email"],
                "Completed": completed,
                "Pending": pending,
                "Avg_Score": avg_val,
                "Last_Active": last_active
            })
            
            dom = t["domain"].upper()
            domain_map[dom] = domain_map.get(dom, 0) + 1
            
        domain_labels = list(domain_map.keys())
        domain_counts = list(domain_map.values())
        
        doc_rows = index_stats["source_details"]
        doc_labels = [d["name"] for d in doc_rows]
        doc_chunks = [d["chunks"] for d in doc_rows]
        
        admin_stats = {
            "trainees_count": len(trainees),
            "active_now": active_now,
            "doc_count": doc_count,
            "chunk_count": chunk_count,
            "total_sessions": total_sessions,
            "total_messages": total_messages,
            "exams_count": len(exams_list),
            "avg_score_pct": avg_score_pct,
            "rag_ratio": rag_ratio,
            "chat_dates": chat_dates,
            "chat_counts": chat_counts,
            "score_ranges": score_ranges,
            "score_counts": score_counts,
            "domain_labels": domain_labels,
            "domain_counts": domain_counts,
            "doc_labels": doc_labels,
            "doc_chunks": doc_chunks,
            "rag_use_count": rag_use_count,
            "general_use_count": general_use_count
        }
        
        return render_template(
            'dashboard.html',
            admin_stats=admin_stats,
            trainee_rows=trainee_rows,
            doc_rows=doc_rows,
            embedding_model_name=EMBEDDING_MODEL
        )
    else:
        assignments = get_assignments_for_trainee(emp_id)
        pending_exams = [a for a in assignments if a["status"] == "assigned"]
        completed_exams = [a for a in assignments if a["status"] == "completed"]
        
        personal_avg = 0.0
        if completed_exams:
            sum_pcts = 0.0
            for a in completed_exams:
                total_m = a.get("total_marks", 100)
                score_val = a.get("score") or 0.0
                sum_pcts += (score_val / total_m * 100.0) if total_m > 0 else 0.0
            personal_avg = sum_pcts / len(completed_exams)
            
        chat_sessions = get_chat_sessions_for_user(emp_id)
        recommendations = index_stats["source_details"]
        resume_chats = chat_sessions[:5]
        
        trajectory_labels = []
        trajectory_scores = []
        sorted_completed = sorted(completed_exams, key=lambda x: x.get("completed_at") or "")
        for idx, a in enumerate(sorted_completed, 1):
            trajectory_labels.append(f"Test {idx}")
            total_m = a.get("total_marks", 100)
            score_val = a.get("score") or 0.0
            trajectory_scores.append((score_val / total_m * 100.0) if total_m > 0 else 0.0)
            
        trainee_stats = {
            "pending_count": len(pending_exams),
            "completed_count": len(completed_exams),
            "personal_avg": personal_avg,
            "chat_count": len(chat_sessions),
            "trajectory_labels": trajectory_labels,
            "trajectory_scores": trajectory_scores
        }
        
        return render_template(
            'dashboard.html',
            trainee_stats=trainee_stats,
            pending_exams=pending_exams,
            recommendations=recommendations,
            resume_chats=resume_chats
        )

# DOCUMENT EXPLORER
@app.route('/documents')
@login_required
def documents():
    index_stats = stats()
    source_names = index_stats["source_names"]
    
    selected_doc = request.args.get('selected_doc')
    if not selected_doc and source_names:
        selected_doc = source_names[0]
        
    doc_details = None
    pdf_exists = False
    
    if selected_doc:
        for doc in index_stats["source_details"]:
            if doc["name"] == selected_doc:
                doc_details = doc
                break
        
        pdf_path = Path(DOCUMENTS_DIR) / selected_doc
        pdf_exists = pdf_path.exists()
        
    role = session.get('user_role', 'trainee')
    
    if role == 'trainee':
        return render_template(
            'documents.html',
            source_names=source_names,
            selected_doc=selected_doc,
            doc_details=doc_details,
            pdf_exists=pdf_exists
        )
    else:
        all_chunks = get_source_chunks(selected_doc) if selected_doc else []
        query = request.args.get('query', '').strip()
        
        if query:
            filtered_chunks = []
            for c in all_chunks:
                text = c.get("text", "")
                if query.lower() in text.lower():
                    import html as py_html
                    escaped_text = py_html.escape(text)
                    escaped_query = py_html.escape(query)
                    highlighted = re.sub(
                        f"({re.escape(escaped_query)})",
                        r"<mark style='background-color: var(--ts-primary); color: #fff; padding: 2px 4px; border-radius: 4px;'>\1</mark>",
                        escaped_text,
                        flags=re.IGNORECASE
                    )
                    filtered_chunks.append({
                        "page": c.get("page"),
                        "chunk_index": c.get("chunk_index"),
                        "highlighted_text": highlighted
                    })
            return render_template(
                'documents.html',
                source_names=source_names,
                selected_doc=selected_doc,
                doc_details=doc_details,
                pdf_exists=pdf_exists,
                query=query,
                filtered_chunks=filtered_chunks,
                all_chunks=all_chunks
            )
        else:
            pages = sorted(list(set([c.get("page") for c in all_chunks if c.get("page") is not None])))
            selected_page = request.args.get('page', type=int)
            if not selected_page and pages:
                selected_page = pages[0]
            elif not selected_page:
                selected_page = 1
                
            page_chunks = [c for c in all_chunks if c.get("page") == selected_page]
            formatted_page_chunks = []
            for c in page_chunks:
                import html as py_html
                formatted_page_chunks.append({
                    "page": c.get("page"),
                    "chunk_index": c.get("chunk_index"),
                    "formatted_text": py_html.escape(c.get("text", ""))
                })
                
            return render_template(
                'documents.html',
                source_names=source_names,
                selected_doc=selected_doc,
                doc_details=doc_details,
                pdf_exists=pdf_exists,
                page_list=pages,
                selected_page=selected_page,
                page_chunks=formatted_page_chunks
            )

@app.route('/documents/download/<path:filename>')
@login_required
def download_document(filename):
    return send_from_directory(DOCUMENTS_DIR, filename, as_attachment=True)

# KNOWLEDGE SEARCH
@app.route('/search')
@login_required
def search_route():
    idx_stats = stats()
    ollama_models = list_local_models()
    
    query = request.args.get('query', '').strip()
    selected_sources = request.args.getlist('selected_sources')
    threshold = request.args.get('threshold', 0.1, type=float)
    top_k = request.args.get('top_k', 4, type=int)
    enable_rag = request.args.get('enable_rag') == 'true'
    selected_model = request.args.get('selected_model')
    if not selected_model and ollama_models:
        selected_model = ollama_models[0]
        
    results = None
    answer = None
    
    if query:
        try:
            from src.embeddings import embed_query
            query_vec = embed_query(query)
            search_results = search(query_vec, top_k=top_k, source_filters=selected_sources if selected_sources else None, threshold=threshold)
            
            results = []
            for hit in search_results:
                text = hit.get("text", "")
                import html as py_html
                escaped_text = py_html.escape(text)
                terms = [re.escape(py_html.escape(t)) for t in query.split() if t.strip()]
                highlighted = escaped_text
                if terms:
                    pattern = f"({'|'.join(terms)})"
                    highlighted = re.sub(
                        pattern,
                        r"<mark style='background-color: var(--ts-primary); color: #fff; padding: 2px 4px; border-radius: 4px;'>\1</mark>",
                        escaped_text,
                        flags=re.IGNORECASE
                    )
                results.append({
                    "source": hit.get("source", "Unknown Source"),
                    "page": hit.get("page", "?"),
                    "score": hit.get("score", 0.0),
                    "text": text,
                    "highlighted_text": highlighted
                })
                
            if enable_rag and results and GROQ_API_KEY:
                answer = generate_rag_answer(query, search_results, selected_model)
        except Exception as e:
            print(f"Search error: {e}")
            results = []
            
    return render_template(
        'search.html',
        query=query,
        stats=idx_stats,
        selected_sources=selected_sources,
        threshold=threshold,
        top_k=top_k,
        enable_rag=enable_rag,
        selected_model=selected_model,
        ollama_models=ollama_models,
        groq_api_key=GROQ_API_KEY,
        results=results,
        answer=answer
    )

# INGESTION
@app.route('/ingest')
@login_required
def ingest():
    if session.get('user_role') != 'admin':
        return redirect(url_for('dashboard'))
        
    idx_stats = stats()
    
    doc_chunks = {}
    for name in idx_stats["source_names"]:
        doc_chunks[name] = get_source_chunks(name)
        
    return render_template(
        'ingest.html',
        stats=idx_stats,
        doc_chunks=doc_chunks,
        summary=session.pop('ingest_summary', None)
    )

@app.route('/ingest', methods=['POST'])
@login_required
def ingest_post():
    if session.get('user_role') != 'admin':
        return redirect(url_for('dashboard'))
        
    from src.embeddings import embed_documents
    from src.ingest import chunk_pages, extract_pages, file_hash
    from src.vectorstore import add_chunks, ingested_hashes
    
    uploaded_files = request.files.getlist('files')
    if not uploaded_files or not uploaded_files[0].filename:
        flash("No files selected")
        return redirect(url_for('ingest'))
        
    known_hashes = ingested_hashes()
    files_processed = 0
    chunks_added = 0
    duplicates = 0
    
    for file in uploaded_files:
        try:
            from io import BytesIO
            data = file.read()
            if not data:
                continue
                
            digest = file_hash(data)
            if digest in known_hashes:
                duplicates += 1
                flash(f"⏭️ {file.filename} is already indexed — skipped duplicate.")
                continue
                
            pages = extract_pages(BytesIO(data))
            if not pages:
                flash(f"⚠️ No extractable text found in {file.filename} — skipped.")
                continue
                
            chunks = chunk_pages(pages, file.filename)
            embeddings = embed_documents([c["text"] for c in chunks])
            added = add_chunks(chunks, embeddings, digest)
            
            try:
                save_path = Path(DOCUMENTS_DIR) / file.filename
                save_path.parent.mkdir(parents=True, exist_ok=True)
                save_path.write_bytes(data)
            except Exception as e:
                flash(f"Could not save PDF copy to disk: {e}")
                
            known_hashes.add(digest)
            files_processed += 1
            chunks_added += added
            flash(f"✅ {file.filename} — Created {added} chunks from {len(pages)} pages.")
            
        except Exception as exc:
            flash(f"❌ Failed to process {file.filename}: {exc}")
            
    session['ingest_summary'] = {
        'processed': files_processed,
        'chunks': chunks_added,
        'duplicates': duplicates
    }
    return redirect(url_for('ingest'))

@app.route('/ingest/delete', methods=['POST'])
@login_required
def ingest_delete():
    if session.get('user_role') != 'admin':
        return redirect(url_for('dashboard'))
        
    doc_name = request.form.get('doc_name')
    if doc_name:
        from src.vectorstore import delete_source
        delete_source(doc_name)
        try:
            pdf_file = Path(DOCUMENTS_DIR) / doc_name
            if pdf_file.exists():
                pdf_file.unlink()
        except Exception:
            pass
        flash(f"Deleted {doc_name}")
    return redirect(url_for('ingest'))

@app.route('/ingest/reset/confirm', methods=['POST'])
@login_required
def ingest_reset_confirm():
    if session.get('user_role') != 'admin':
        return redirect(url_for('dashboard'))
    session['confirm_reset'] = True
    return redirect(url_for('ingest'))

@app.route('/ingest/reset/cancel', methods=['POST'])
@login_required
def ingest_reset_cancel():
    session.pop('confirm_reset', None)
    return redirect(url_for('ingest'))

@app.route('/ingest/reset/execute', methods=['POST'])
@login_required
def ingest_reset_execute():
    if session.get('user_role') != 'admin':
        return redirect(url_for('dashboard'))
        
    from src.vectorstore import reset_collection
    reset_collection()
    try:
        for pdf_file in Path(DOCUMENTS_DIR).glob("*.pdf"):
            pdf_file.unlink()
    except Exception:
        pass
    session.pop('confirm_reset', None)
    flash("Index reset complete.")
    return redirect(url_for('ingest'))

# USER MANAGEMENT
@app.route('/user_management')
@login_required
def user_management():
    if session.get('user_role') != 'admin':
        return redirect(url_for('dashboard'))
    
    users_list = get_all_users()
    active_tab = request.args.get('tab', 'create')
    last_created = session.pop('last_created_user', None)
    
    return render_template(
        'user_management.html',
        users=users_list,
        active_tab=active_tab,
        last_created_user=last_created
    )

@app.route('/user_management/create', methods=['POST'])
@login_required
def user_management_create():
    if session.get('user_role') != 'admin':
        return redirect(url_for('dashboard'))
        
    employee_id = request.form.get('employee_id', '').strip()
    full_name = request.form.get('full_name', '').strip()
    email = request.form.get('email', '').strip()
    domain = request.form.get('domain', 'general')
    password_mode = request.form.get('password_mode', 'auto')
    manual_password = request.form.get('manual_password', '').strip()
    
    if not employee_id:
        flash("Please enter an Employee ID.", "create_user_error")
        return redirect(url_for('user_management', tab='create'))
    if not full_name:
        flash("Please enter a Full Name.", "create_user_error")
        return redirect(url_for('user_management', tab='create'))
    if not email:
        flash("Please enter an Email address.", "create_user_error")
        return redirect(url_for('user_management', tab='create'))
        
    if password_mode == 'auto':
        first_part = full_name.split()[0].capitalize() if full_name.split() else "User"
        generated_password = f"{first_part}@123"
    else:
        generated_password = manual_password
        
    if len(generated_password) < 8:
        flash("Password must be at least 8 characters long.", "create_user_error")
        return redirect(url_for('user_management', tab='create'))
        
    from src.users import add_user
    success, msg = add_user(
        employee_id=employee_id,
        email=email,
        full_name=full_name,
        domain=domain,
        password_plain=generated_password,
        role="trainee"
    )
    
    if success:
        session['last_created_user'] = {
            "email": email,
            "password": generated_password,
            "name": full_name
        }
        return redirect(url_for('user_management', tab='create'))
    else:
        flash(msg, "create_user_error")
        return redirect(url_for('user_management', tab='create'))

@app.route('/user_management/delete', methods=['POST'])
@login_required
def user_management_delete():
    if session.get('user_role') != 'admin':
        return redirect(url_for('dashboard'))
        
    employee_id = request.form.get('employee_id')
    if employee_id == 'admin':
        flash("Cannot delete protected admin account.", "manage_user_info")
        return redirect(url_for('user_management', tab='manage'))
        
    from src.users import delete_user
    if delete_user(employee_id):
        flash("Deleted user successfully.", "manage_user_info")
    else:
        flash("Failed to delete user.", "manage_user_info")
        
    return redirect(url_for('user_management', tab='manage'))

# ANNOUNCEMENTS
@app.route('/announcements')
@login_required
def announcements():
    anns = get_all_announcements()
    return render_template('announcements.html', announcements=anns)

@app.route('/announcements/create', methods=['POST'])
@login_required
def announcements_create():
    if session.get('user_role') != 'admin':
        return redirect(url_for('dashboard'))
        
    title = request.form.get('title', '').strip()
    content = request.form.get('content', '').strip()
    
    if not title or not content:
        flash("Title and Content are required.")
        return redirect(url_for('announcements'))
        
    if add_announcement(title, content):
        flash("Announcement published successfully!")
    else:
        flash("Failed to publish announcement. Database error.")
    return redirect(url_for('announcements'))

@app.route('/announcements/delete', methods=['POST'])
@login_required
def announcements_delete():
    if session.get('user_role') != 'admin':
        return redirect(url_for('dashboard'))
        
    ann_id = request.form.get('announcement_id', type=int)
    if ann_id:
        if delete_announcement(ann_id):
            flash("Announcement deleted successfully.")
        else:
            flash("Failed to delete announcement.")
    return redirect(url_for('announcements'))

# EXAMS & ASSIGNMENTS
@app.route('/exams')
@login_required
def exams():
    role = session.get('user_role', 'trainee')
    active_tab = request.args.get('active_tab', 'create')
    
    exam_title_draft = session.get('exam_title_draft', '')
    exam_desc_draft = session.get('exam_desc_draft', '')
    exam_marks_draft = session.get('exam_marks_draft', 50)
    exam_questions = session.get('exam_questions', [])
    
    all_exams = get_all_exams()
    
    selected_exam_id = request.args.get('selected_exam_id', type=int)
    if not selected_exam_id and all_exams:
        selected_exam_id = all_exams[0]['exam_id']
        
    review_assignment_id = request.args.get('review_assignment_id', type=int)
    review_detail = None
    if review_assignment_id:
        detail = get_assignment_by_id(review_assignment_id)
        if detail:
            try:
                grade_sheet = json.loads(detail["ai_feedback"])
            except Exception:
                grade_sheet = {"overall_comments": detail["ai_feedback"], "questions": []}
                
            review_detail = {
                "assignment_id": detail["assignment_id"],
                "title": detail["title"],
                "full_name": detail["full_name"],
                "score": detail["score"],
                "total_marks": detail["total_marks"],
                "ai_feedback_overall": grade_sheet.get("overall_comments", ""),
                "ai_feedback_questions": grade_sheet.get("questions", []),
                "answers_submitted": detail["answers"],
                "questions": detail["questions"]
            }
            active_tab = 'results'
            
    trainee_review_id = request.args.get('trainee_review_id', type=int)
    if trainee_review_id:
        detail = get_assignment_by_id(trainee_review_id)
        if detail:
            try:
                grade_sheet = json.loads(detail["ai_feedback"])
            except Exception:
                grade_sheet = {"overall_comments": detail["ai_feedback"], "questions": []}
                
            review_detail = {
                "assignment_id": detail["assignment_id"],
                "title": detail["title"],
                "score": detail["score"],
                "total_marks": detail["total_marks"],
                "ai_feedback_overall": grade_sheet.get("overall_comments", ""),
                "ai_feedback_questions": grade_sheet.get("questions", []),
                "answers_submitted": detail["answers"],
                "questions": detail["questions"]
            }
            
    taking_assignment_id = session.get('taking_assignment_id')
    taking_assignment = None
    if taking_assignment_id:
        taking_assignment = get_assignment_by_id(taking_assignment_id)
        
    return render_template(
        'exams.html',
        active_tab=active_tab,
        exam_title_draft=exam_title_draft,
        exam_desc_draft=exam_desc_draft,
        exam_marks_draft=exam_marks_draft,
        exam_questions=exam_questions,
        exams=all_exams,
        selected_exam_id=selected_exam_id,
        review_detail=review_detail,
        taking_assignment=taking_assignment
    )

@app.route('/exams/create/add_manual', methods=['POST'])
@login_required
def exams_create_add_manual():
    if session.get('user_role') != 'admin':
        return redirect(url_for('dashboard'))
        
    session['exam_title_draft'] = request.form.get('title', '').strip()
    session['exam_desc_draft'] = request.form.get('description', '').strip()
    session['exam_marks_draft'] = request.form.get('total_marks', 50, type=int)
    
    mq_text = request.form.get('mq_text', '').strip()
    mq_type = request.form.get('mq_type', 'mcq')
    mq_marks = request.form.get('mq_marks', 10, type=int)
    mq_opts = request.form.get('mq_opts', '').strip()
    mq_ans = request.form.get('mq_ans', '').strip()
    
    if not mq_text:
        flash("Please enter a question.")
        return redirect(url_for('exams', active_tab='create'))
    if mq_type == 'mcq' and not mq_opts:
        flash("Please specify MCQ options.")
        return redirect(url_for('exams', active_tab='create'))
    if not mq_ans:
        flash("Please enter a correct answer / rubric.")
        return redirect(url_for('exams', active_tab='create'))
        
    parsed_opts = [o.strip() for o in mq_opts.split(",") if o.strip()] if mq_type == "mcq" else []
    
    new_q = {
        "question": mq_text,
        "type": mq_type,
        "marks": mq_marks,
        "options": parsed_opts,
        "correct_answer": mq_ans
    }
    
    if 'exam_questions' not in session:
        session['exam_questions'] = []
    questions = session['exam_questions']
    questions.append(new_q)
    session['exam_questions'] = questions
    
    flash("Question added to list!")
    return redirect(url_for('exams', active_tab='create'))

@app.route('/exams/create/generate_ai', methods=['POST'])
@login_required
def exams_create_generate_ai():
    if session.get('user_role') != 'admin':
        return redirect(url_for('dashboard'))
        
    session['exam_title_draft'] = request.form.get('title', '').strip()
    session['exam_desc_draft'] = request.form.get('description', '').strip()
    session['exam_marks_draft'] = request.form.get('total_marks', 50, type=int)
    
    ai_doc = request.form.get('ai_doc')
    ai_count = request.form.get('ai_count', 5, type=int)
    ai_model = request.form.get('ai_model')
    
    if not GROQ_API_KEY or not ai_model or not ai_doc:
        flash("AI generation requirements missing.")
        return redirect(url_for('exams', active_tab='create'))
        
    try:
        coll = get_collection()
        res = coll.get(where={"source": ai_doc}, include=["documents"])
        docs = res.get("documents") or []
        if not docs:
            flash("No text chunks found in document.")
        else:
            context_text = "\n\n".join(docs[:3])
            
            prompt = (
                f"Generate exactly {ai_count} test questions based on the document excerpt below. "
                f"Ensure a mix of Multiple Choice Questions (MCQ) and Free-text questions. "
                f"You MUST return ONLY a valid JSON array of question objects (do not wrap in markdown or prefix text). "
                f"Format of each question object in JSON:\n"
                f"[{{\"question\": \"Question text\", \"type\": \"mcq\", \"marks\": 10, \"options\": [\"Option A\", \"Option B\", \"Option C\", \"Option D\"], \"correct_answer\": \"Option A\"}},\n"
                f" {{\"question\": \"Question text\", \"type\": \"text\", \"marks\": 10, \"options\": [], \"correct_answer\": \"Explain key details...\"}}]\n\n"
                f"--- DOCUMENT EXCERPT ---\n{context_text}"
            )
            
            response = generate_chat_answer(
                prompt=prompt,
                model_name=ai_model,
                system_instruction="You are a professional educational assessor. You output ONLY valid JSON arrays without codeblocks."
            )
            
            cleaned_resp = clean_json_response(response)
            questions_list = json.loads(cleaned_resp)
            
            if isinstance(questions_list, list):
                if 'exam_questions' not in session:
                    session['exam_questions'] = []
                questions = session['exam_questions']
                questions.extend(questions_list)
                session['exam_questions'] = questions
                flash(f"Added {len(questions_list)} AI-generated questions!")
            else:
                flash("AI returned invalid question format. Please try again.")
    except Exception as e:
        flash(f"Failed to generate questions: {e}")
        
    return redirect(url_for('exams', active_tab='create'))

@app.route('/exams/create/remove_question', methods=['POST'])
@login_required
def exams_create_remove_question():
    if session.get('user_role') != 'admin':
        return redirect(url_for('dashboard'))
        
    idx = request.form.get('index', type=int)
    questions = session.get('exam_questions', [])
    if 0 <= idx < len(questions):
        questions.pop(idx)
        session['exam_questions'] = questions
        flash("Question removed.")
    return redirect(url_for('exams', active_tab='create'))

@app.route('/exams/create/clear', methods=['POST'])
@login_required
def exams_create_clear():
    session.pop('exam_title_draft', None)
    session.pop('exam_desc_draft', None)
    session.pop('exam_marks_draft', None)
    session.pop('exam_questions', None)
    return redirect(url_for('exams', active_tab='create'))

@app.route('/exams/create/save', methods=['POST'])
@login_required
def exams_create_save():
    if session.get('user_role') != 'admin':
        return redirect(url_for('dashboard'))
        
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    total_marks = request.form.get('total_marks', 50, type=int)
    questions = session.get('exam_questions', [])
    
    if not title:
        flash("Please enter an exam title.")
        return redirect(url_for('exams', active_tab='create'))
    if not questions:
        flash("Cannot save an exam with zero questions.")
        return redirect(url_for('exams', active_tab='create'))
        
    if add_exam(title, description, total_marks, questions):
        flash(f"Exam '{title}' saved successfully!")
        session.pop('exam_title_draft', None)
        session.pop('exam_desc_draft', None)
        session.pop('exam_marks_draft', None)
        session.pop('exam_questions', None)
        return redirect(url_for('exams', active_tab='assign'))
    else:
        flash("Failed to save exam. Database error.")
        return redirect(url_for('exams', active_tab='create'))

@app.route('/exams/assign', methods=['POST'])
@login_required
def exams_assign():
    if session.get('user_role') != 'admin':
        return redirect(url_for('dashboard'))
        
    exam_id = request.form.get('exam_id', type=int)
    due_date = request.form.get('due_date', '').strip()
    due_date_str = due_date.replace('-', '/') if due_date else ""
    
    trainee_ids = request.form.getlist('trainee_ids')
    
    trainees = [u for u in get_all_users() if u["role"] == "trainee"]
    trainee_options = {u["employee_id"]: u["employee_id"] for u in trainees}
    
    target_ids = list(trainee_options.values()) if not trainee_ids else trainee_ids
    
    success_count = 0
    for t_id in target_ids:
        if assign_exam(exam_id, t_id, due_date_str):
            success_count += 1
            
    if success_count > 0:
        flash(f"Assigned exam to {success_count} trainees!")
    else:
        flash("Trainees are already assigned to this exam.")
        
    return redirect(url_for('exams', active_tab='assign', selected_exam_id=exam_id))

@app.route('/exams/assignment/delete', methods=['POST'])
@login_required
def exams_assignment_delete():
    if session.get('user_role') != 'admin':
        return redirect(url_for('dashboard'))
        
    assignment_id = request.form.get('assignment_id', type=int)
    selected_exam_id = request.form.get('selected_exam_id')
    
    if assignment_id:
        try:
            conn = sqlite3.connect(str(_DB_PATH))
            c = conn.cursor()
            c.execute("DELETE FROM assignments WHERE assignment_id = ?", (assignment_id,))
            conn.commit()
            conn.close()
            flash("Assignment deleted successfully.")
        except Exception as e:
            flash(f"Failed to delete assignment: {e}")
            
    return redirect(url_for('exams', active_tab='assign', selected_exam_id=selected_exam_id))

@app.route('/exams/delete', methods=['POST'])
@login_required
def exams_delete_post():
    if session.get('user_role') != 'admin':
        return redirect(url_for('dashboard'))
        
    exam_id = request.form.get('exam_id', type=int)
    if exam_id:
        if delete_exam(exam_id):
            flash("Exam deleted successfully.")
        else:
            flash("Failed to delete exam.")
    return redirect(url_for('exams', active_tab='assign'))

@app.route('/exams/take', methods=['POST'])
@login_required
def exams_take():
    assignment_id = request.form.get('assignment_id', type=int)
    if assignment_id:
        session['taking_assignment_id'] = assignment_id
    return redirect(url_for('exams'))

@app.route('/exams/submit', methods=['POST'])
@login_required
def exams_submit():
    assignment_id = request.form.get('assignment_id', type=int)
    if not assignment_id:
        return redirect(url_for('exams'))
        
    detail = get_assignment_by_id(assignment_id)
    if not detail:
        session.pop('taking_assignment_id', None)
        return redirect(url_for('exams'))
        
    is_malpractice = request.form.get('malpractice') == 'true'
    if is_malpractice:
        responses = {}
        for idx, q in enumerate(detail["questions"]):
            responses[idx] = request.form.get(f"answer_{idx}", "").strip()
            
        ai_breakdowns = []
        for idx, q in enumerate(detail["questions"]):
            ai_breakdowns.append({
                "index": idx,
                "score": 0.0,
                "feedback": "Grading bypassed. Proctoring system detected active window/tab switching or unauthorized actions."
            })
            
        overall_feedback = {
            "overall_comments": "🚨 MALPRACTICE DETECTED: This assessment was terminated automatically. Multiple proctoring violations (tab switching, window focus loss, or screenshot attempts) were registered. The score is set to 0.0.",
            "questions": ai_breakdowns
        }
        
        if submit_exam_answers(assignment_id, responses, 0.0, json.dumps(overall_feedback)):
            flash("Exam submitted automatically and flagged as MALPRACTICE.")
        else:
            flash("Failed to save malpractice submission to database.")
            
        session.pop('taking_assignment_id', None)
        return redirect(url_for('exams'))
        
    responses = {}
    for idx, q in enumerate(detail["questions"]):
        responses[idx] = request.form.get(f"answer_{idx}", "").strip()
        
    local_models = list_local_models()
    grade_model = None
    if GROQ_API_KEY and local_models:
        d_idx = 0
        for idx, m in enumerate(local_models):
            if "llama-3.3" in m.lower() or "llama" in m.lower():
                d_idx = idx
                break
        grade_model = local_models[d_idx]
        
    total_earned_score = 0.0
    ai_breakdowns = []
    
    for idx, q in enumerate(detail["questions"]):
        t_ans = responses.get(idx) or responses.get(str(idx)) or ""
        if q["type"] == "mcq":
            is_correct = str(t_ans).strip().lower() == str(q["correct_answer"]).strip().lower()
            score_q = float(q["marks"]) if is_correct else 0.0
            feedback_q = "Correct!" if is_correct else f"Incorrect. Correct answer was: {q['correct_answer']}"
            total_earned_score += score_q
            ai_breakdowns.append({
                "index": idx,
                "score": score_q,
                "feedback": feedback_q
            })
        else:
            if not grade_model:
                total_earned_score += float(q["marks"]) / 2
                ai_breakdowns.append({
                    "index": idx,
                    "score": float(q["marks"]) / 2,
                    "feedback": "Graded 50% (No LLM detected for evaluation)"
                })
            else:
                prompt = (
                    f"Grade the trainee's answer against the expected rubric/keywords.\n"
                    f"Question: {q['question']}\n"
                    f"Expected Rubric: {q['correct_answer']}\n"
                    f"Trainee Answer: {t_ans}\n"
                    f"Max Marks: {q['marks']}\n\n"
                    f"You MUST assign a score between 0 and {q['marks']} based on accuracy and completeness. "
                    f"You MUST return ONLY a valid JSON object matching this structure: "
                    f"{{\"score\": 8.5, \"feedback\": \"Trainee correctly identified visibility protocols but missed...\"}}"
                )
                try:
                    resp = generate_chat_answer(
                        prompt=prompt,
                        model_name=grade_model,
                        system_instruction="You are a strict grading assistant. Return ONLY a single JSON object."
                    )
                    cleaned = clean_json_response(resp)
                    res_grade = json.loads(cleaned)
                    score_q = float(res_grade.get("score", 0.0))
                    feedback_q = res_grade.get("feedback", "No feedback generated.")
                except Exception:
                    score_q = 0.0
                    feedback_q = "AI Grading failure. Assigned 0."
                    
                total_earned_score += score_q
                ai_breakdowns.append({
                    "index": idx,
                    "score": score_q,
                    "feedback": feedback_q
                })
                
    overall_feedback = {
        "overall_comments": f"Completed test with a total score of {total_earned_score} / {detail['total_marks']}.",
        "questions": ai_breakdowns
    }
    
    if submit_exam_answers(assignment_id, responses, total_earned_score, json.dumps(overall_feedback)):
        flash("Test submitted and graded successfully!")
    else:
        flash("Failed to save submissions to database.")
        
    session.pop('taking_assignment_id', None)
    return redirect(url_for('exams'))

# AI ASSISTANT & SSE CHAT STREAMING
active_generations = {} # employee_id -> { "session_id", "query", "partial_response", "sources", "stop" }

@app.route('/assistant')
@login_required
def assistant():
    user_info = session.get('user_info', {}) or {}
    emp_id = user_info.get('employee_id', 'demo')
    
    user_sessions = get_chat_sessions_for_user(emp_id)
    
    session_id = request.args.get('session_id')
    if session_id:
        session['active_chat_session_id'] = session_id
        active_id = session_id
    else:
        active_id = str(uuid.uuid4())
        create_chat_session(active_id, emp_id, "New Chat")
        session['active_chat_session_id'] = active_id
        user_sessions = get_chat_sessions_for_user(emp_id)
        
    active_messages = get_chat_messages(active_id)
    return render_template(
        'assistant.html',
        active_messages=active_messages,
        user_sessions=user_sessions,
        active_chat_session_id=active_id
    )

@app.route('/assistant/chat_stream', methods=['POST'])
@login_required
def chat_stream():
    data = request.get_json() or {}
    query = data.get('query', '').strip()
    model = data.get('model')
    mode = data.get('mode', 'RAG (Document Guided)')
    
    user_info = session.get('user_info', {}) or {}
    emp_id = user_info.get('employee_id', 'demo')
    active_session_id = session.get('active_chat_session_id')
    
    if not active_session_id:
        return jsonify({"error": "No active chat session"}), 400
        
    add_chat_message(active_session_id, "user", query)
    
    user_sessions = get_chat_sessions_for_user(emp_id)
    current_title = "Welcome Conversation"
    for s in user_sessions:
        if s["session_id"] == active_session_id:
            current_title = s["title"]
            break
    if current_title in ["Welcome Conversation", "New Conversation"] or current_title.startswith("Chat "):
        new_title = " ".join(query.split()[:4])
        if len(new_title) > 20:
            new_title = new_title[:18] + "..."
        if not new_title.strip():
            new_title = "Conversation"
        rename_chat_session(active_session_id, new_title)
        
    sources = []
    if mode == "RAG (Document Guided)":
        try:
            from src.embeddings import embed_query
            query_vec = embed_query(query)
            results = search(query_vec, top_k=4, threshold=0.1)
            if results:
                sources = results
        except Exception as e:
            print(f"Retrieval error: {e}")
            
    active_generations[emp_id] = {
        "session_id": active_session_id,
        "query": query,
        "partial_response": "",
        "sources": [{"source": s["source"], "page": s["page"], "text": s["text"], "score": s["score"]} for s in sources],
        "stop": False
    }
    
    def event_generator():
        gen_state = active_generations.get(emp_id)
        if not gen_state:
            yield "Error: State not found."
            return
            
        from src.llm import generate_rag_answer_stream, generate_chat_answer_stream
        
        if mode == "RAG (Document Guided)":
            if not sources:
                chunk_stream = ["No matching document context was found to guide an answer. Please upload documents first or check search configurations."]
            else:
                chunk_stream = generate_rag_answer_stream(query, sources, model)
        else:
            system_prompt = (
                "You are a helpful, encouraging learning coach for 'Talent Sphere Elevate', an advanced corporate training platform. "
                "Provide clear, professional explanation or training advice depending on the trainee's question. "
                "Do NOT include any code blocks, programming snippets, or code examples in your response unless the user's query explicitly asks for code or programming implementation."
            )
            chunk_stream = generate_chat_answer_stream(query, model, system_prompt)
            
        try:
            for chunk in chunk_stream:
                if gen_state.get("stop"):
                    break
                gen_state["partial_response"] += chunk
                yield chunk
                
            final_text = gen_state["partial_response"]
            if gen_state.get("stop"):
                final_text += " ⏹️ *[Response stopped by user]*"
                
            add_chat_message(active_session_id, "assistant", final_text, gen_state["sources"])
            
            if gen_state["sources"]:
                sources_json = json.dumps(gen_state["sources"])
                yield f"[SOURCES_JSON_START]{sources_json}[SOURCES_JSON_END]"
                
        except Exception as e:
            yield f"Error in streaming: {e}"
        finally:
            active_generations.pop(emp_id, None)
            
    return Response(stream_with_context(event_generator()), mimetype='text/event-stream')

@app.route('/assistant/chat_stop', methods=['POST'])
@login_required
def chat_stop():
    user_info = session.get('user_info', {}) or {}
    emp_id = user_info.get('employee_id', 'demo')
    if emp_id in active_generations:
        active_generations[emp_id]["stop"] = True
    return jsonify({"status": "success"})

@app.route('/assistant/clear', methods=['POST'])
@login_required
def assistant_clear():
    active_id = session.get('active_chat_session_id')
    if active_id:
        try:
            conn = sqlite3.connect(str(_DB_PATH))
            cursor = conn.cursor()
            cursor.execute("DELETE FROM chat_messages WHERE session_id = ?", (active_id,))
            conn.commit()
            conn.close()
        except Exception:
            pass
    return redirect(url_for('assistant'))

@app.route('/assistant/session/create')
@login_required
def assistant_session_create():
    user_info = session.get('user_info', {}) or {}
    emp_id = user_info.get('employee_id', 'demo')
    new_id = str(uuid.uuid4())
    create_chat_session(new_id, emp_id, "New Conversation")
    session['active_chat_session_id'] = new_id
    return redirect(url_for('assistant'))

@app.route('/assistant/session/rename')
@login_required
def assistant_session_rename():
    session_id = request.args.get('id')
    if session_id:
        session['renaming_session_id'] = session_id
        user_info = session.get('user_info', {}) or {}
        emp_id = user_info.get('employee_id', 'demo')
        sessions = get_chat_sessions_for_user(emp_id)
        title = "Conversation"
        for s in sessions:
            if s["session_id"] == session_id:
                title = s["title"]
                break
        session['renaming_session_title'] = title
    return redirect(url_for('assistant'))

@app.route('/assistant/session/rename/save', methods=['POST'])
@login_required
def assistant_session_rename_save():
    session_id = session.get('renaming_session_id')
    new_title = request.form.get('new_title', '').strip()
    if session_id and new_title:
        rename_chat_session(session_id, new_title)
    session.pop('renaming_session_id', None)
    session.pop('renaming_session_title', None)
    return redirect(url_for('assistant'))

@app.route('/assistant/session/rename/cancel')
@login_required
def assistant_session_rename_cancel():
    session.pop('renaming_session_id', None)
    session.pop('renaming_session_title', None)
    return redirect(url_for('assistant'))

@app.route('/assistant/session/delete')
@login_required
def assistant_session_delete():
    session_id = request.args.get('id')
    if session_id:
        delete_chat_session(session_id)
        if session.get('active_chat_session_id') == session_id:
            session.pop('active_chat_session_id', None)
    return redirect(url_for('assistant'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)