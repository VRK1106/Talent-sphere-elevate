import re
import sqlite3
import datetime
from pathlib import Path

_DB_PATH = Path(__file__).resolve().parent.parent / "users.db"

def detect_performance_query(query: str) -> str | None:
    """Detect if the query is requesting student performance details.
    Returns:
        - The requested student name, ID, or 'self' if requesting own.
        - None if not a performance query.
    """
    q_lower = query.lower().strip()
    
    # Self-query patterns
    self_patterns = [
        r"\bhow\b.*\b(?:am i|i am)\b.*\b(?:doing|performing|progressing)\b",
        r"\b(?:my|own)\b.*\b(?:performance|score|progress|analytic|stat|grade|report)\b",
        r"\b(?:what is|what are|show|get)\b.*\b(?:my|own)\b.*\b(?:score|grade|report|progress|stat)\b",
        r"\bhow\b.*\b(?:my|own)\b.*\b(?:performance|progress|score|grade)\b"
    ]
    for pattern in self_patterns:
        if re.search(pattern, q_lower):
            return "self"
            
    # Trainee-specific query patterns
    patterns = [
        r"\b(?:performance|score|progress|grade|analytic|stat|status|report|average)\b.*\b(?:of|for)\b.*\b(?:student|trainee|user)?\s*(\w+)",
        r"\bhow\s+is\s+(?:student|trainee|user)?\s*(\w+)\s+(?:doing|performing|progressing)",
        r"\bshow\s+(?:student|trainee|user)?\s*(\w+)\s*(?:performance|score|progress|grade|stat|report)",
    ]
    
    for pattern in patterns:
        match = re.search(pattern, q_lower)
        if match:
            target = match.group(1).strip()
            # Ignore general words that might match accidentally
            if target not in ["the", "a", "this", "my", "your", "student", "trainee", "user"]:
                return target
                
    return None

def get_trainee_log_analytics(emp_id: str) -> dict:
    """Query activity logs for a student and calculate estimated study hours and actions."""
    conn = sqlite3.connect(str(_DB_PATH))
    c = conn.cursor()
    
    analytics = {
        "total_activities": 0,
        "study_hours": 0.0,
        "avg_session_mins": 0.0
    }
    
    try:
        # Total activity count
        c.execute("SELECT COUNT(*) FROM activity_logs WHERE employee_id = ?", (emp_id,))
        analytics["total_activities"] = c.fetchone()[0]
        
        # Calculate Study Time / Session Estimate
        c.execute("SELECT timestamp FROM activity_logs WHERE employee_id = ? ORDER BY timestamp ASC", (emp_id,))
        timestamps = []
        for row in c.fetchall():
            if row[0]:
                try:
                    timestamps.append(datetime.datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S"))
                except Exception:
                    pass
        
        sessions = []
        if timestamps:
            current_session = [timestamps[0]]
            for ts in timestamps[1:]:
                diff = (ts - current_session[-1]).total_seconds() / 60.0
                if diff <= 30.0:
                    current_session.append(ts)
                else:
                    sessions.append(current_session)
                    current_session = [ts]
            sessions.append(current_session)
            
            total_minutes = 0
            for s in sessions:
                if len(s) > 1:
                    duration = (s[-1] - s[0]).total_seconds() / 60.0
                    total_minutes += max(duration, 5.0)
                else:
                    total_minutes += 5.0
            
            analytics["study_hours"] = round(total_minutes / 60.0, 1)
            analytics["avg_session_mins"] = round(total_minutes / len(sessions), 1) if sessions else 0.0
            
    except Exception as e:
        print(f"Error calculating trainee log stats: {e}")
        
    conn.close()
    return analytics

def get_student_performance_context(identifier: str, requester_role: str, requester_id: str) -> str:
    """Fetch user profile, exams, log analytics, and proctoring violations and format as a context block.
    Checks authorization: Trainees can only query themselves ('self' or their own ID).
    """
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    try:
        # 1. Resolve employee_id
        target_emp_id = None
        if identifier == "self":
            target_emp_id = requester_id
        else:
            # Check if identifier matches employee_id directly
            c.execute("SELECT employee_id FROM users WHERE employee_id = ?", (identifier,))
            row = c.fetchone()
            if row:
                target_emp_id = row["employee_id"]
            else:
                # Try matching by name
                c.execute("SELECT employee_id FROM users WHERE full_name LIKE ?", (f"%{identifier}%",))
                row = c.fetchone()
                if row:
                    target_emp_id = row["employee_id"]
                    
        if not target_emp_id:
            conn.close()
            return f"Trainee matching '{identifier}' was not found in the platform database."
            
        # 2. Check Authorization
        if requester_role != 'admin' and target_emp_id != requester_id:
            conn.close()
            return "Unauthorized. You are only permitted to query your own performance data. Please ask 'How is my performance?'."
            
        # 3. Retrieve Profile
        c.execute("SELECT employee_id, full_name, email, domain, last_active, role FROM users WHERE employee_id = ?", (target_emp_id,))
        profile = c.fetchone()
        if not profile or profile["role"] == "admin":
            conn.close()
            return "The requested user is either not registered or is an administrator."
            
        # 4. Retrieve Exams & Assignments
        c.execute("""
            SELECT a.score, a.status, a.ai_feedback, a.completed_at, e.title, e.total_marks
            FROM assignments a
            JOIN exams e ON a.exam_id = e.exam_id
            WHERE a.trainee_id = ?
        """, (target_emp_id,))
        assignments = [dict(r) for r in c.fetchall()]
        
        # 5. Retrieve Proctoring Violations (Admins only)
        proctor_logs = []
        if requester_role == 'admin':
            c.execute("""
                SELECT pl.trigger_reason, pl.groq_label, pl.timestamp, e.title
                FROM proctor_logs pl
                JOIN assignments a ON pl.assignment_id = a.assignment_id
                JOIN exams e ON a.exam_id = e.exam_id
                WHERE a.trainee_id = ?
            """, (target_emp_id,))
            proctor_logs = [dict(r) for r in c.fetchall()]
            
        # 6. Retrieve Log Analytics (Study hours, average session mins)
        log_stats = get_trainee_log_analytics(target_emp_id)
        
        # Compile context string
        context_lines = []
        context_lines.append(f"=== STUDENT PROFILE: {profile['full_name']} (ID: {profile['employee_id']}) ===")
        context_lines.append(f"Name: {profile['full_name']}")
        context_lines.append(f"Email: {profile['email']}")
        context_lines.append(f"Domain/Specialization: {profile['domain'].upper()}")
        context_lines.append(f"Last Active on Platform: {profile['last_active'] or 'Never'}")
        context_lines.append("")
        
        # Study Habit Analytics
        context_lines.append("=== PLATFORM STUDY HABIT ANALYTICS ===")
        context_lines.append(f"Total Platform Actions: {log_stats.get('total_activities', 0)}")
        context_lines.append(f"Estimated Total Study Hours: {log_stats.get('study_hours', 0.0)} hours")
        context_lines.append(f"Average Study Session Duration: {log_stats.get('avg_session_mins', 0.0)} minutes")
        context_lines.append("")
        
        # Exam Progress & Scores
        context_lines.append("=== EXAM ASSIGNMENT & SCORE RECORD ===")
        completed = [a for a in assignments if a["status"] == "completed"]
        pending = [a for a in assignments if a["status"] == "assigned"]
        context_lines.append(f"Total Assigned: {len(assignments)}")
        context_lines.append(f"Completed: {len(completed)}")
        context_lines.append(f"Pending: {len(pending)}")
        
        if completed:
            context_lines.append("\nCompleted Exams:")
            for a in completed:
                score_str = f"{a['score']} / {a['total_marks']}"
                pct = (a['score'] / a['total_marks'] * 100.0) if a['total_marks'] > 0 else 0.0
                context_lines.append(f" - {a['title']}: {score_str} ({pct:.1f}%) [Completed on: {a['completed_at'] or 'N/A'}]")
        else:
            context_lines.append("\nNo completed exams on record yet.")
            
        if pending:
            context_lines.append("\nPending/Uncompleted Exams:")
            for a in pending:
                context_lines.append(f" - {a['title']} (Due/Assigned)")
                
        # Proctoring Violation Log (Admin review only)
        if requester_role == 'admin':
            context_lines.append("\n=== SECURE PROCTORING & INTEGRITY LOGS ===")
            if proctor_logs:
                context_lines.append(f"Total Integrity Flagged Events: {len(proctor_logs)}")
                for log in proctor_logs:
                    context_lines.append(f" - Exam '{log['title']}': {log['trigger_reason']} (Groq classification: {log['groq_label']}) [At: {log['timestamp']}]")
            else:
                context_lines.append("No integrity violations or proctoring flags logged for this student.")
                
        conn.close()
        return "\n".join(context_lines)
        
    except Exception as e:
        if conn:
            conn.close()
        return f"Error retrieving student performance data: {e}"
