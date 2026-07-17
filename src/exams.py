"""SQLite-backed exams and announcements repository."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

_DB_PATH = Path(__file__).resolve().parent.parent / "users.db"


def init_exams_db() -> None:
    """Initialize SQLite tables for exams, assignments, and announcements."""
    conn = sqlite3.connect(str(_DB_PATH))
    cursor = conn.cursor()
    
    # 1. Create exams table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS exams (
            exam_id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            total_marks INTEGER NOT NULL,
            questions TEXT NOT NULL,  -- JSON serialized questions list
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    
    # 2. Create assignments table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS assignments (
            assignment_id INTEGER PRIMARY KEY AUTOINCREMENT,
            exam_id INTEGER NOT NULL,
            trainee_id TEXT NOT NULL,
            due_date TEXT,
            status TEXT DEFAULT 'assigned',  -- 'assigned', 'completed'
            score REAL,
            answers TEXT,  -- JSON serialized trainee answers
            ai_feedback TEXT,  -- AI grading response feedback
            assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TEXT,
            FOREIGN KEY (exam_id) REFERENCES exams (exam_id) ON DELETE CASCADE,
            FOREIGN KEY (trainee_id) REFERENCES users (employee_id) ON DELETE CASCADE
        )
        """
    )
    
    # 3. Create announcements table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS announcements (
            announcement_id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    
    conn.commit()
    conn.close()


# --- Exams operations ---

def get_all_exams() -> list[dict[str, Any]]:
    """Fetch all created exams."""
    init_exams_db()
    try:
        conn = sqlite3.connect(str(_DB_PATH))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT exam_id, title, description, total_marks, questions, created_at FROM exams ORDER BY exam_id DESC")
        rows = cursor.fetchall()
        conn.close()
        
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["questions"] = json.loads(d["questions"])
            except Exception:
                d["questions"] = []
            result.append(d)
        return result
    except Exception:
        return []


def get_exam_by_id(exam_id: int) -> dict[str, Any] | None:
    """Fetch a single exam by ID."""
    init_exams_db()
    try:
        conn = sqlite3.connect(str(_DB_PATH))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT exam_id, title, description, total_marks, questions, created_at FROM exams WHERE exam_id = ?", (exam_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            d = dict(row)
            try:
                d["questions"] = json.loads(d["questions"])
            except Exception:
                d["questions"] = []
            return d
    except Exception:
        pass
    return None


def add_exam(title: str, description: str, total_marks: int, questions: list[dict[str, Any]]) -> bool:
    """Add a new exam containing a list of questions."""
    init_exams_db()
    try:
        conn = sqlite3.connect(str(_DB_PATH))
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO exams (title, description, total_marks, questions)
            VALUES (?, ?, ?, ?)
            """,
            (title.strip(), description.strip(), total_marks, json.dumps(questions)),
        )
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def delete_exam(exam_id: int) -> bool:
    """Delete an exam and cascade delete its assignments."""
    init_exams_db()
    try:
        conn = sqlite3.connect(str(_DB_PATH))
        cursor = conn.cursor()
        # Enable FK cascade support explicitly in SQLite
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("DELETE FROM exams WHERE exam_id = ?", (exam_id,))
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


# --- Assignments operations ---

def assign_exam(exam_id: int, trainee_id: str, due_date: str | None) -> bool:
    """Assign an exam to a trainee."""
    init_exams_db()
    try:
        conn = sqlite3.connect(str(_DB_PATH))
        cursor = conn.cursor()
        
        # Check if already assigned
        cursor.execute(
            "SELECT count(*) FROM assignments WHERE exam_id = ? AND trainee_id = ? AND status = 'assigned'",
            (exam_id, trainee_id)
        )
        if cursor.fetchone()[0] > 0:
            conn.close()
            return False  # Already assigned and active
            
        cursor.execute(
            """
            INSERT INTO assignments (exam_id, trainee_id, due_date)
            VALUES (?, ?, ?)
            """,
            (exam_id, trainee_id, due_date),
        )
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def get_assignments_for_exam(exam_id: int) -> list[dict[str, Any]]:
    """Get all trainee assignments for a specific exam."""
    init_exams_db()
    try:
        conn = sqlite3.connect(str(_DB_PATH))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT a.assignment_id, a.exam_id, a.trainee_id, a.due_date, a.status, a.score, 
                   a.answers, a.ai_feedback, a.assigned_at, a.completed_at, u.full_name, u.email
            FROM assignments a
            JOIN users u ON a.trainee_id = u.employee_id
            WHERE a.exam_id = ?
            ORDER BY a.assignment_id DESC
            """,
            (exam_id,),
        )
        rows = cursor.fetchall()
        conn.close()
        
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["answers"] = json.loads(d["answers"]) if d["answers"] else {}
            except Exception:
                d["answers"] = {}
            result.append(d)
        return result
    except Exception:
        return []


def get_assignments_for_trainee(trainee_id: str) -> list[dict[str, Any]]:
    """Get all exam assignments for a specific trainee."""
    init_exams_db()
    try:
        conn = sqlite3.connect(str(_DB_PATH))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT a.assignment_id, a.exam_id, a.trainee_id, a.due_date, a.status, a.score, 
                   a.answers, a.ai_feedback, a.assigned_at, a.completed_at, e.title, e.description, e.total_marks
            FROM assignments a
            JOIN exams e ON a.exam_id = e.exam_id
            WHERE a.trainee_id = ?
            ORDER BY a.assignment_id DESC
            """,
            (trainee_id,),
        )
        rows = cursor.fetchall()
        conn.close()
        
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["answers"] = json.loads(d["answers"]) if d["answers"] else {}
            except Exception:
                d["answers"] = {}
            result.append(d)
        return result
    except Exception:
        return []


def get_assignment_by_id(assignment_id: int) -> dict[str, Any] | None:
    """Fetch a single assignment details."""
    init_exams_db()
    try:
        conn = sqlite3.connect(str(_DB_PATH))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT a.assignment_id, a.exam_id, a.trainee_id, a.due_date, a.status, a.score, 
                   a.answers, a.ai_feedback, a.assigned_at, a.completed_at, e.title, e.description, e.questions, e.total_marks, u.full_name
            FROM assignments a
            JOIN exams e ON a.exam_id = e.exam_id
            JOIN users u ON a.trainee_id = u.employee_id
            WHERE a.assignment_id = ?
            """,
            (assignment_id,),
        )
        row = cursor.fetchone()
        conn.close()
        if row:
            d = dict(row)
            d["description"] = d.get("description") or ""
            try:
                d["questions"] = json.loads(d["questions"])
            except Exception:
                d["questions"] = []
            try:
                d["answers"] = json.loads(d["answers"]) if d["answers"] else {}
            except Exception:
                d["answers"] = {}
            return d
    except Exception:
        pass
    return None


def submit_exam_answers(assignment_id: int, answers: dict[str, Any], score: float, ai_feedback: str) -> bool:
    """Submit trainee exam responses and save grade results."""
    init_exams_db()
    try:
        conn = sqlite3.connect(str(_DB_PATH))
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE assignments
            SET status = 'completed',
                answers = ?,
                score = ?,
                ai_feedback = ?,
                completed_at = CURRENT_TIMESTAMP
            WHERE assignment_id = ?
            """,
            (json.dumps(answers), score, ai_feedback, assignment_id),
        )
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def delete_assignment(assignment_id: int) -> bool:
    """Delete a trainee assignment by ID."""
    init_exams_db()
    try:
        conn = sqlite3.connect(str(_DB_PATH))
        cursor = conn.cursor()
        cursor.execute("DELETE FROM assignments WHERE assignment_id = ?", (assignment_id,))
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


# --- Announcements operations ---

def get_all_announcements() -> list[dict[str, Any]]:
    """Fetch all announcements."""
    init_exams_db()
    try:
        conn = sqlite3.connect(str(_DB_PATH))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT announcement_id, title, content, created_at FROM announcements ORDER BY announcement_id DESC")
        rows = cursor.fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def add_announcement(title: str, content: str) -> bool:
    """Add a new system announcement."""
    init_exams_db()
    try:
        conn = sqlite3.connect(str(_DB_PATH))
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO announcements (title, content)
            VALUES (?, ?)
            """,
            (title.strip(), content.strip()),
        )
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def delete_announcement(announcement_id: int) -> bool:
    """Delete an announcement by ID."""
    init_exams_db()
    try:
        conn = sqlite3.connect(str(_DB_PATH))
        cursor = conn.cursor()
        cursor.execute("DELETE FROM announcements WHERE announcement_id = ?", (announcement_id,))
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False
