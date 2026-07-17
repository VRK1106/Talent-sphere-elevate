import os
import sys
import json
import sqlite3
from unittest.mock import patch

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, _DB_PATH

def test_exam_wizard_flow():
    print("Initializing Flask test client...")
    client = app.test_client()

    print("Logging in as admin...")
    # Follow redirects because login redirects to dashboard
    resp = client.post('/login', data={
        'username': 'admin',
        'password': 'admin123'
    }, follow_redirects=True)
    assert resp.status_code == 200
    print("[OK] Login successful.")

    # 1. Test GET /assistant/wizard/docs
    print("Testing GET /assistant/wizard/docs...")
    resp = client.get('/assistant/wizard/docs')
    assert resp.status_code == 200
    docs_data = json.loads(resp.data)
    assert "documents" in docs_data
    print(f"[OK] Received documents: {docs_data['documents']}")

    # 2. Test GET /assistant/wizard/trainees
    print("Testing GET /assistant/wizard/trainees...")
    resp = client.get('/assistant/wizard/trainees')
    assert resp.status_code == 200
    trainees_data = json.loads(resp.data)
    assert "trainees" in trainees_data
    print(f"[OK] Received trainees count: {len(trainees_data['trainees'])}")

    # 3. Test GET /assistant/wizard/previous_exams
    print("Testing GET /assistant/wizard/previous_exams...")
    resp = client.get('/assistant/wizard/previous_exams')
    assert resp.status_code == 200
    prev_exams_data = json.loads(resp.data)
    assert "exams" in prev_exams_data
    print(f"[OK] Received previous exams count: {len(prev_exams_data['exams'])}")

    # 4. Test POST /assistant/wizard/generate (with mocked LLM response)
    print("Testing POST /assistant/wizard/generate...")
    mock_llm_response = """
    [
      {
        "question": "What is the primary phase in hardened steel?",
        "type": "mcq",
        "marks": 5,
        "options": ["Martensite", "Ferrite", "Austenite", "Cementite"],
        "correct_answer": "Martensite"
      },
      {
        "question": "Explain the quenching process.",
        "type": "subjective",
        "marks": 10,
        "correct_answer": "Rapid cooling of austenite to form martensite."
      }
    ]
    """
    
    generate_payload = {
        "docs": ["Unit-1.pdf"],
        "weights": {"Unit-1.pdf": 100},
        "sections": [
            {"name": "Section A", "type": "mcq", "count": 1, "marks": 5},
            {"name": "Section B", "type": "subjective", "count": 1, "marks": 10}
        ],
        "difficulty": {"easy": 40, "medium": 40, "hard": 20},
        "blooms": ["Remembering", "Understanding"],
        "exclude_exams": [],
        "auto_weight": False
    }

    with patch('src.llm.generate_chat_answer', return_value=mock_llm_response):
        resp = client.post(
            '/assistant/wizard/generate',
            data=json.dumps(generate_payload),
            content_type='application/json'
        )
        print(f"Generate response status code: {resp.status_code}")
        print(f"Generate response body: {resp.data.decode('utf-8')}")
        assert resp.status_code == 200
        gen_data = json.loads(resp.data)
        assert "questions" in gen_data
        questions = gen_data["questions"]
        assert len(questions) == 4
        print(f"[OK] Generated questions: {json.dumps(questions, indent=2)}")

    # 5. Test POST /assistant/wizard/save
    print("Testing POST /assistant/wizard/save...")
    save_payload = {
        "title": "Unit Test Steel Exam",
        "description": "Formative assessment on steel heat treatment.",
        "total_marks": 15,
        "questions": questions,
        "settings": {
            "scheduling": {
                "assignee_id": "all",
                "start_date": "2026-07-17T12:00",
                "end_date": "2026-07-18T12:00",
                "timezone": "UTC"
            },
            "security": {
                "shuffle": True,
                "proctoring": "Webcam",
                "proctoring_consent": "I agree to webcam monitoring.",
                "access_restrict": "AccessCode",
                "access_restrict_value": "SECRET999",
                "ip_allowlist": ""
            },
            "duration": 45,
            "post_exam": {
                "result_release": "after_deadline",
                "grading_mode": "hybrid"
            }
        },
        "save_as_template": True,
        "template_name": "Test Template Steel"
    }

    resp = client.post(
        '/assistant/wizard/save',
        data=json.dumps(save_payload),
        content_type='application/json'
    )
    assert resp.status_code == 200
    save_data = json.loads(resp.data)
    print(f"[OK] Save response: {save_data}")

    # 6. Verify SQLite Database Entries
    print("Verifying database records...")
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Check exam
    cursor.execute("SELECT * FROM exams WHERE title = 'Unit Test Steel Exam'")
    exam_row = cursor.fetchone()
    assert exam_row is not None
    print(f"[OK] Verified exam inserted. ID: {exam_row['exam_id']}, Title: {exam_row['title']}")
    
    # Check assignments
    cursor.execute("SELECT * FROM assignments WHERE exam_id = ?", (exam_row['exam_id'],))
    assignments = cursor.fetchall()
    assert len(assignments) > 0
    print(f"[OK] Verified assignments created. Trainee IDs: {[r['trainee_id'] for r in assignments]}")

    # Check template
    cursor.execute("SELECT * FROM exam_templates WHERE name = 'Test Template Steel'")
    template_row = cursor.fetchone()
    assert template_row is not None
    print(f"[OK] Verified exam template created. Name: {template_row['name']}")

    conn.close()
    print("ALL TESTS PASSED SUCCESSFULLY!")

if __name__ == '__main__':
    test_exam_wizard_flow()
