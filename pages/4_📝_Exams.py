"""Talent Sphere Elevate — Exams and Assessments Page."""

from __future__ import annotations

import sys
from pathlib import Path
import html
import json
import re

import streamlit as st

# Ensure the project root is importable when Streamlit runs this file directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.ui import load_css, section_header, render_sidebar
from src.vectorstore import stats, get_collection
from src.users import get_all_users
from src.exams import (
    get_all_exams,
    add_exam,
    delete_exam,
    assign_exam,
    get_assignments_for_exam,
    get_assignments_for_trainee,
    get_assignment_by_id,
    submit_exam_answers
)
from src.llm import list_local_models, generate_chat_answer

# Load custom styles
load_css()

# Helper: clean LLM output to parse as JSON
def clean_json_response(raw_resp: str) -> str:
    resp = raw_resp.strip()
    # Remove markdown blocks
    if resp.startswith("```"):
        # Match ```json or ```
        match = re.match(r"^```(?:json)?\s*", resp)
        if match:
            resp = resp[match.end():]
        if resp.endswith("```"):
            resp = resp[:-3]
    return resp.strip()


# Fetch active user details
role = st.session_state.get("user_role", "trainee")
user_info = st.session_state.get("user_info", {}) or {}
employee_id = user_info.get("employee_id", "demo")

# Sidebar stats & navigation
index = stats()

# Global state for exam creation
if "exam_questions" not in st.session_state:
    st.session_state.exam_questions = []
if "active_exam_tab" not in st.session_state:
    st.session_state.active_exam_tab = "Assign"
if "taking_assignment_id" not in st.session_state:
    st.session_state.taking_assignment_id = None

# --- ADMIN VIEW -------------------------------------------------------------
if role == "admin":
    st.title("📝 Exam Management")
    
    st.markdown(
        "<div style='font-size: 1.05rem; color: var(--ts-text-secondary); margin-bottom: 1.5rem;'>"
        "Create assessments, assign them to trainees, and review AI-graded results."
        "</div>",
        unsafe_allow_html=True
    )
    
    # Custom segmented tab navigation
    col_t1, col_t2, col_t3, _ = st.columns([1.5, 1.2, 1.2, 5])
    with col_t1:
        type_btn = "primary" if st.session_state.active_exam_tab == "Create exam" else "secondary"
        if st.button("Create exam", key="tab_create", type=type_btn, use_container_width=True):
            st.session_state.active_exam_tab = "Create exam"
            st.rerun()
    with col_t2:
        type_btn = "primary" if st.session_state.active_exam_tab == "Assign" else "secondary"
        if st.button("Assign", key="tab_assign", type=type_btn, use_container_width=True):
            st.session_state.active_exam_tab = "Assign"
            st.rerun()
    with col_t3:
        type_btn = "primary" if st.session_state.active_exam_tab == "Results" else "secondary"
        if st.button("Results", key="tab_results", type=type_btn, use_container_width=True):
            st.session_state.active_exam_tab = "Results"
            st.rerun()
            
    st.write("")
    
    # --- Tab 1: Create exam ---
    if st.session_state.active_exam_tab == "Create exam":
        with st.container(border=True):
            st.markdown("<div style='font-size: 1.15rem; font-weight: 600; color: var(--ts-primary); margin-bottom: 1rem;'>1. Exam Basic Info</div>", unsafe_allow_html=True)
            e_title = st.text_input("Exam Title", placeholder="e.g. GS1 Supply Chain Visibility")
            e_desc = st.text_area("Exam Description", placeholder="e.g. Test understanding of supply chain tracking and visibility guidelines.")
            e_marks = st.number_input("Total Marks", min_value=1, max_value=100, value=50)
            
        st.write("")
        
        # AI Generator Card
        with st.container(border=True):
            st.markdown("<div style='font-size: 1.15rem; font-weight: 600; color: var(--ts-primary); margin-bottom: 1rem;'>2. AI-Assisted Question Generator</div>", unsafe_allow_html=True)
            st.markdown("<div style='font-size: 0.88rem; color: var(--ts-text-secondary); margin-bottom: 0.8rem;'>Select an uploaded PDF and let Qwen generate professional questions.</div>", unsafe_allow_html=True)
            
            doc_sources = index["source_names"]
            if not doc_sources:
                st.info("No documents are currently ingested. Upload files in Document Ingestion to enable AI Question Generation.")
            else:
                col_sel_doc, col_q_count = st.columns([4, 2])
                with col_sel_doc:
                    ai_doc = st.selectbox("Select Target PDF", options=doc_sources)
                with col_q_count:
                    ai_count = st.slider("Questions to Generate", min_value=2, max_value=10, value=5)
                    
                local_models = list_local_models()
                ai_model = None
                if local_models:
                    d_idx = 0
                    for idx, m in enumerate(local_models):
                        if "qwen" in m.lower():
                            d_idx = idx
                            break
                    ai_model = st.selectbox("LLM Model for Generation", options=local_models, index=d_idx)
                
                col_ai_btn, _ = st.columns([2, 4])
                with col_ai_btn:
                    gen_clicked = st.button("🤖 Generate with Qwen", type="primary", use_container_width=True, disabled=(ai_model is None))
                    
                if gen_clicked and ai_model and ai_doc:
                    with st.spinner("Qwen is reading document chunks and drafting questions..."):
                        # Get some chunks of the document to use as context
                        try:
                            coll = get_collection()
                            res = coll.get(where={"source": ai_doc}, include=["documents"])
                            docs = res.get("documents") or []
                            if not docs:
                                st.error("No text chunks found in document.")
                            else:
                                # Combine first 3 chunks to make context
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
                                    st.session_state.exam_questions.extend(questions_list)
                                    st.success(f"Added {len(questions_list)} AI-generated questions!")
                                else:
                                    st.error("AI returned invalid question format. Please try again.")
                        except Exception as e:
                            st.error(f"Failed to generate questions: {e}")
                            
        st.write("")
        
        # Manual Question Builder
        with st.container(border=True):
            st.markdown("<div style='font-size: 1.15rem; font-weight: 600; color: var(--ts-primary); margin-bottom: 1rem;'>3. Manual Question Builder</div>", unsafe_allow_html=True)
            mq_text = st.text_input("Question Text", placeholder="What is the visibility protocol?")
            mq_type = st.selectbox("Question Type", options=["mcq", "text"])
            mq_marks = st.number_input("Question Marks", min_value=1, max_value=50, value=10)
            
            mq_opts = st.text_input("MCQ Options (comma separated)", placeholder="Option A, Option B, Option C, Option D")
            mq_ans = st.text_input("Correct Answer / Scoring Rubric", placeholder="Correct MCQ option or key phrases for grading text answers")
            
            col_add, _ = st.columns([1.5, 5])
            with col_add:
                add_clicked = st.button("➕ Add Question", type="secondary", use_container_width=True)
                
            if add_clicked:
                if not mq_text.strip():
                    st.error("Please enter a question.")
                elif mq_type == "mcq" and not mq_opts.strip():
                    st.error("Please specify MCQ options.")
                elif not mq_ans.strip():
                    st.error("Please enter a correct answer / rubric.")
                else:
                    parsed_opts = [o.strip() for o in mq_opts.split(",") if o.strip()] if mq_type == "mcq" else []
                    new_q = {
                        "question": mq_text.strip(),
                        "type": mq_type,
                        "marks": int(mq_marks),
                        "options": parsed_opts,
                        "correct_answer": mq_ans.strip()
                    }
                    st.session_state.exam_questions.append(new_q)
                    st.toast("Question added to list!")
                    st.rerun()
                    
        st.write("")
        
        # Questions List & Save
        with st.container(border=True):
            st.markdown("<div style='font-size: 1.15rem; font-weight: 600; color: var(--ts-primary); margin-bottom: 1rem;'>4. Exam Questions Preview</div>", unsafe_allow_html=True)
            
            if not st.session_state.exam_questions:
                st.info("No questions added to the exam yet. Build or generate some questions above.")
            else:
                total_q_marks = sum(q["marks"] for q in st.session_state.exam_questions)
                st.write(f"Total Questions: **{len(st.session_state.exam_questions)}** &nbsp;·&nbsp; Combined Marks: **{total_q_marks}**")
                
                for idx, q in enumerate(st.session_state.exam_questions):
                    col_info, col_act = st.columns([5, 1])
                    with col_info:
                        st.markdown(
                            f"**Q{idx+1}: {html.escape(q['question'])}** ({q['type'].upper()} · {q['marks']} marks)  \n"
                            f"Rubric/Correct Answer: *{html.escape(str(q['correct_answer']))}*  \n"
                            f"{'Options: ' + ', '.join(q['options']) if q['options'] else ''}"
                        )
                    with col_act:
                        if st.button("🗑️ Remove", key=f"rem_q_{idx}", type="secondary", use_container_width=True):
                            st.session_state.exam_questions.pop(idx)
                            st.rerun()
                    st.divider()
                    
                col_save, col_clear_all, _ = st.columns([1.8, 1.8, 4])
                with col_save:
                    save_clicked = st.button("💾 Save Exam", type="primary", use_container_width=True)
                with col_clear_all:
                    clear_all_clicked = st.button("🧹 Clear All", type="secondary", use_container_width=True)
                    
                if clear_all_clicked:
                    st.session_state.exam_questions = []
                    st.rerun()
                    
                if save_clicked:
                    if not e_title.strip():
                        st.error("Please enter an exam title.")
                    elif not st.session_state.exam_questions:
                        st.error("Cannot save an exam with zero questions.")
                    else:
                        if add_exam(e_title, e_desc, e_marks, st.session_state.exam_questions):
                            st.success(f"Exam '{e_title}' saved successfully!")
                            st.session_state.exam_questions = []
                            st.session_state.active_exam_tab = "Assign"
                            st.rerun()
                        else:
                            st.error("Failed to save exam. Database error.")

    # --- Tab 2: Assign ---
    elif st.session_state.active_exam_tab == "Assign":
        exams = get_all_exams()
        
        if not exams:
            st.info("No exams exist in the database. Go to 'Create exam' to build one first!")
        else:
            with st.container(border=True):
                # 1. Exam selection
                exam_options = {f"{e['title']} · {len(e['questions'])} questions · {e['total_marks']} marks": e["exam_id"] for e in exams}
                selected_exam_label = st.selectbox("Exam", options=list(exam_options.keys()))
                selected_exam_id = exam_options[selected_exam_label]
                
                # Find the actual exam details
                active_exam = next(e for e in exams if e["exam_id"] == selected_exam_id)
                
                # 2. Date input
                due_date = st.date_input("Due date (optional)", value=None)
                due_date_str = due_date.strftime("%Y/%m/%d") if due_date else ""
                
                # 3. Trainee selector
                trainees = [u for u in get_all_users() if u["role"] == "trainee"]
                if not trainees:
                    st.warning("No trainee users are currently registered in the database.")
                    assign_enabled = False
                else:
                    assign_enabled = True
                    trainee_options = {f"{u['full_name']} ({u['employee_id']})": u["employee_id"] for u in trainees}
                    selected_trainees = st.multiselect(
                        "Assign to Trainees", 
                        options=list(trainee_options.keys()),
                        default=None,
                        help="Select trainees to assign. Leave empty to select all."
                    )
                
                st.write("")
                col_btn, _ = st.columns([1.5, 5])
                with col_btn:
                    assign_clicked = st.button("▶ Assign exam", type="primary", use_container_width=True, disabled=not assign_enabled)
                    
                if assign_clicked and assign_enabled:
                    # If empty list, assign to all
                    target_ids = list(trainee_options.values()) if not selected_trainees else [trainee_options[t] for t in selected_trainees]
                    
                    success_count = 0
                    for t_id in target_ids:
                        if assign_exam(selected_exam_id, t_id, due_date_str):
                            success_count += 1
                            
                    if success_count > 0:
                        st.success(f"Assigned exam to {success_count} trainees!")
                        st.rerun()
                    else:
                        st.error("Trainee is already assigned to this exam.")
            
            st.write("")
            
            # Current assignments list
            st.markdown("<div style='font-size: 1.2rem; font-weight: 700; color: var(--ts-text); margin-bottom: 0.6rem;'>Current assignments</div>", unsafe_allow_html=True)
            assignments = get_assignments_for_exam(selected_exam_id)
            
            if not assignments:
                st.markdown("<div style='color: var(--ts-text-muted); font-size: 0.95rem;'>Nobody is assigned to this exam yet.</div>", unsafe_allow_html=True)
            else:
                with st.container(border=True):
                    for a in assignments:
                        st.markdown(
                            f"<div style='margin-bottom: 0.2rem;'>"
                            f"👤 <b>{html.escape(a['full_name'])}</b> ({html.escape(a['trainee_id'])} &nbsp;·&nbsp; {html.escape(a['email'])})  \n"
                            f"Status: <span style='font-weight:600; color: "
                            f"{'var(--ts-primary)' if a['status'] == 'completed' else 'orange'};'>"
                            f"{a['status'].upper()}</span> &nbsp;·&nbsp; "
                            f"Due Date: <b>{a['due_date'] or 'N/A'}</b> &nbsp;·&nbsp; "
                            f"Score: <b>{a['score'] if a['score'] is not None else '—'}</b> / {active_exam['total_marks']}"
                            f"</div>",
                            unsafe_allow_html=True
                        )
                        st.divider()
            
            st.write("")
            # Delete this exam button at the bottom
            col_del, _ = st.columns([2, 5])
            with col_del:
                del_exam_clicked = st.button("🗑 Delete this exam", type="secondary", use_container_width=True)
                
            if del_exam_clicked:
                if delete_exam(selected_exam_id):
                    st.success("Exam deleted successfully.")
                    st.rerun()
                else:
                    st.error("Failed to delete exam.")

    # --- Tab 3: Results ---
    elif st.session_state.active_exam_tab == "Results":
        exams = get_all_exams()
        all_results = []
        for e in exams:
            all_results.extend(get_assignments_for_exam(e["exam_id"]))
            
        completed_results = [r for r in all_results if r["status"] == "completed"]
        
        if not completed_results:
            st.info("No completed assessments found in the system.")
        else:
            with st.container(border=True):
                for res in completed_results:
                    exam_obj = next((e for e in exams if e["exam_id"] == res["exam_id"]), None)
                    exam_title = exam_obj["title"] if exam_obj else "Unknown Exam"
                    exam_total = exam_obj["total_marks"] if exam_obj else 100
                    
                    col_info, col_act = st.columns([5, 1.2])
                    with col_info:
                        st.markdown(
                            f"<div style='margin-bottom: 0.2rem;'>"
                            f"<b>{html.escape(res['full_name'])}</b> submitted <b>{html.escape(exam_title)}</b>"
                            f"</div>"
                            f"<div style='font-size: 0.82rem; color: var(--ts-text-muted);'>"
                            f"Completed At: <b>{res['completed_at']}</b> &nbsp;·&nbsp; "
                            f"Score: <span style='font-weight:700; color: var(--ts-primary);'>{res['score']}</span> / {exam_total}"
                            f"</div>",
                            unsafe_allow_html=True
                        )
                    with col_act:
                        if st.button("Review AI Grade", key=f"rev_ai_{res['assignment_id']}", use_container_width=True):
                            st.session_state.review_assignment_id = res["assignment_id"]
                            st.rerun()
                    st.divider()
                    
            if "review_assignment_id" in st.session_state:
                detail = get_assignment_by_id(st.session_state.review_assignment_id)
                if detail:
                    st.write("")
                    with st.container(border=True):
                        st.markdown(f"<div style='font-size: 1.15rem; font-weight: 700; color: var(--ts-primary); margin-bottom: 0.8rem;'>AI Evaluation: {html.escape(detail['title'])} ({detail['full_name']})</div>", unsafe_allow_html=True)
                        st.markdown(f"**Final Score**: {detail['score']} / {detail['total_marks']}")
                        
                        try:
                            grade_sheet = json.loads(detail["ai_feedback"])
                        except Exception:
                            grade_sheet = {"overall_comments": detail["ai_feedback"], "questions": []}
                            
                        st.markdown(f"**AI Comments**: {grade_sheet.get('overall_comments', '')}")
                        
                        st.markdown("<div style='font-weight:600; margin-top: 1rem;'>Question Level Breakdown:</div>", unsafe_allow_html=True)
                        for idx, q in enumerate(detail["questions"]):
                            st.markdown(f"**Q{idx+1}: {html.escape(q['question'])}** ({q['marks']} marks)")
                            ans_trainee = detail["answers"].get(str(idx)) or detail["answers"].get(idx) or "—"
                            st.markdown(f"- Trainee Answer: *{html.escape(str(ans_trainee))}*")
                            st.markdown(f"- Rubric/Correct Answer: *{html.escape(str(q['correct_answer']))}*")
                            
                            # Find matching question grade
                            q_grade = next((item for item in grade_sheet.get("questions", []) if item.get("index") == idx), None)
                            if q_grade:
                                st.markdown(f"- Score assigned: **{q_grade.get('score')}** / {q['marks']}")
                                st.markdown(f"- AI Feedback: {q_grade.get('feedback')}")
                            st.divider()
                            
                        if st.button("Close Review", type="secondary"):
                            del st.session_state.review_assignment_id
                            st.rerun()

# --- TRAINEE VIEW -----------------------------------------------------------
else:
    st.title("📝 My Assessments")
    st.markdown(
        "<div style='font-size: 1.05rem; color: var(--ts-text-secondary); margin-bottom: 1.5rem;'>"
        "View your assigned exams, complete tests, and review AI-graded comments."
        "</div>",
        unsafe_allow_html=True
    )
    
    # Check if trainee is in the middle of taking an exam
    if st.session_state.taking_assignment_id:
        detail = get_assignment_by_id(st.session_state.taking_assignment_id)
        if not detail:
            st.session_state.taking_assignment_id = None
            st.rerun()
            
        with st.container(border=True):
            st.markdown(f"<div style='font-size: 1.25rem; font-weight:700; color: var(--ts-primary); margin-bottom: 0.4rem;'>{html.escape(detail['title'])}</div>", unsafe_allow_html=True)
            st.markdown(f"<div style='font-size: 0.9rem; color: var(--ts-text-secondary); margin-bottom: 1.2rem;'>{html.escape(detail['description'])} &nbsp;·&nbsp; Total Marks: {detail['total_marks']}</div>", unsafe_allow_html=True)
            
            # Form to collect answers
            responses = {}
            for idx, q in enumerate(detail["questions"]):
                st.markdown(f"**Q{idx+1}: {html.escape(q['question'])}** ({q['marks']} marks)")
                if q["type"] == "mcq":
                    responses[idx] = st.radio(f"Select option for Q{idx+1}", options=q["options"], key=f"t_mcq_{idx}")
                else:
                    responses[idx] = st.text_area(f"Write your response for Q{idx+1}", placeholder="Type answer here...", key=f"t_txt_{idx}")
                st.divider()
                
            col_sub, col_can = st.columns([1.5, 1.5])
            with col_sub:
                sub_clicked = st.button("🚀 Submit Assessment", type="primary", use_container_width=True)
            with col_can:
                if st.button("❌ Cancel", type="secondary", use_container_width=True):
                    st.session_state.taking_assignment_id = None
                    st.rerun()
                    
            if sub_clicked:
                # Trigger grading
                with st.spinner("AI is grading your answers, please wait..."):
                    local_models = list_local_models()
                    grade_model = None
                    if local_models:
                        d_idx = 0
                        for idx, m in enumerate(local_models):
                            if "qwen" in m.lower():
                                d_idx = idx
                                break
                        grade_model = local_models[d_idx]
                        
                    total_earned_score = 0.0
                    ai_breakdowns = []
                    
                    for idx, q in enumerate(detail["questions"]):
                        t_ans = responses[idx]
                        if q["type"] == "mcq":
                            # Auto grade MCQs
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
                            # Grade Free text with LLM
                            if not grade_model:
                                # Fallback if no LLM
                                total_earned_score += float(q["marks"]) / 2  # default 50%
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
                                
                    # Structure overall feedback JSON
                    overall_feedback = {
                        "overall_comments": f"Completed test with a total score of {total_earned_score} / {detail['total_marks']}.",
                        "questions": ai_breakdowns
                    }
                    
                    if submit_exam_answers(st.session_state.taking_assignment_id, responses, total_earned_score, json.dumps(overall_feedback)):
                        st.success("Test submitted and graded successfully!")
                        st.session_state.taking_assignment_id = None
                        st.rerun()
                    else:
                        st.error("Failed to save submissions to database.")
                        
    else:
        # Show lists of assigned and completed exams
        assignments = get_assignments_for_trainee(employee_id)
        
        assigned_list = [a for a in assignments if a["status"] == "assigned"]
        completed_list = [a for a in assignments if a["status"] == "completed"]
        
        # 1. Assigned
        st.markdown("<div style='font-size: 1.25rem; font-weight: 700; color: var(--ts-primary); margin-bottom: 0.8rem;'>Assigned Exams</div>", unsafe_allow_html=True)
        if not assigned_list:
            st.info("You have no pending exam assignments. Nice work!")
        else:
            for a in assigned_list:
                with st.container(border=True):
                    col_info, col_act = st.columns([5, 1.2])
                    with col_info:
                        st.markdown(
                            f"<div style='margin-bottom: 0.2rem;'>"
                            f"<span style='font-size: 1.1rem; font-weight: 600; color: var(--ts-text);'>📝 {html.escape(a['title'])}</span>"
                            f"</div>"
                            f"<div style='font-size: 0.85rem; color: var(--ts-text-secondary);'>"
                            f"Due Date: <b>{a['due_date'] or 'Flexible'}</b> &nbsp;·&nbsp; Total Marks: <b>{a['total_marks']}</b>"
                            f"</div>",
                            unsafe_allow_html=True
                        )
                    with col_act:
                        if st.button("▶ Take Exam", key=f"take_{a['assignment_id']}", type="primary", use_container_width=True):
                            st.session_state.taking_assignment_id = a["assignment_id"]
                            st.rerun()
                            
        st.write("")
        
        # 2. Completed
        st.markdown("<div style='font-size: 1.25rem; font-weight: 700; color: var(--ts-primary); margin-bottom: 0.8rem;'>Completed Exams</div>", unsafe_allow_html=True)
        if not completed_list:
            st.write("No completed exams yet.")
        else:
            with st.container(border=True):
                for a in completed_list:
                    col_info, col_act = st.columns([5, 1.5])
                    with col_info:
                        st.markdown(
                            f"<div style='margin-bottom: 0.2rem;'>"
                            f"<span style='font-weight:600; color:var(--ts-text);'>📝 {html.escape(a['title'])}</span>"
                            f"</div>"
                            f"<div style='font-size: 0.85rem; color: var(--ts-text-secondary);'>"
                            f"Submitted: <b>{a['completed_at'] or 'N/A'}</b> &nbsp;·&nbsp; "
                            f"Score: <span style='font-weight:700; color: var(--ts-primary);'>{a['score']}</span> / {a['total_marks']}"
                            f"</div>",
                            unsafe_allow_html=True
                        )
                    with col_act:
                        if st.button("Review Grade", key=f"rev_trn_{a['assignment_id']}", use_container_width=True):
                            st.session_state.trainee_review_id = a["assignment_id"]
                            st.rerun()
                    st.divider()
                    
            if "trainee_review_id" in st.session_state:
                detail = get_assignment_by_id(st.session_state.trainee_review_id)
                if detail:
                    st.write("")
                    with st.container(border=True):
                        st.markdown(f"<div style='font-size: 1.15rem; font-weight: 700; color: var(--ts-primary); margin-bottom: 0.8rem;'>AI Grading Report: {html.escape(detail['title'])}</div>", unsafe_allow_html=True)
                        st.markdown(f"**Final Score**: {detail['score']} / {detail['total_marks']}")
                        
                        try:
                            grade_sheet = json.loads(detail["ai_feedback"])
                        except Exception:
                            grade_sheet = {"overall_comments": detail["ai_feedback"], "questions": []}
                            
                        st.markdown(f"**AI Comments**: {grade_sheet.get('overall_comments', '')}")
                        
                        st.markdown("<div style='font-weight:600; margin-top: 1rem;'>Question Level Breakdown:</div>", unsafe_allow_html=True)
                        for idx, q in enumerate(detail["questions"]):
                            st.markdown(f"**Q{idx+1}: {html.escape(q['question'])}** ({q['marks']} marks)")
                            ans_trainee = detail["answers"].get(str(idx)) or detail["answers"].get(idx) or "—"
                            st.markdown(f"- Your Answer: *{html.escape(str(ans_trainee))}*")
                            st.markdown(f"- Correct Answer/Rubric: *{html.escape(str(q['correct_answer']))}*")
                            
                            q_grade = next((item for item in grade_sheet.get("questions", []) if item.get("index") == idx), None)
                            if q_grade:
                                st.markdown(f"- Score: **{q_grade.get('score')}** / {q['marks']}")
                                st.markdown(f"- AI Feedback: {q_grade.get('feedback')}")
                            st.divider()
                            
                        if st.button("Close Report", type="secondary"):
                            del st.session_state.trainee_review_id
                            st.rerun()

# --- Sidebar branding ------------------------------------------------------
render_sidebar(index)
