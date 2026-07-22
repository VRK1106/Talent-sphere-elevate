import sqlite3
import json
from pathlib import Path

_DB_PATH = Path(__file__).resolve().parent.parent / "users.db"

# The concept mapping tag graph (related concepts)
CONCEPT_MAP = {
    # Python
    "variables": ["control flow", "functions"],
    "control flow": ["variables", "functions"],
    "functions": ["decorators", "generators"],
    "oop": ["decorators", "classes"],
    "decorators": ["functions", "generators"],
    "generators": ["decorators", "functions"],
    "classes": ["oop"],
    # Machine Learning
    "supervised learning": ["linear regression", "decision trees"],
    "linear regression": ["supervised learning", "overfitting"],
    "decision trees": ["supervised learning", "overfitting"],
    "overfitting": ["regularization", "neural networks"],
    "regularization": ["overfitting", "supervised learning"],
    "neural networks": ["overfitting", "supervised learning"],
    # Web Development
    "html/css": ["javascript dom"],
    "javascript dom": ["html/css", "rest apis"],
    "rest apis": ["javascript dom", "authentication"],
    "authentication": ["rest apis"],
    # General / Admin / HR
    "onboarding": ["compliance", "code of conduct"],
    "compliance": ["onboarding", "code of conduct"],
    "code of conduct": ["compliance", "onboarding"]
}

# Keywords to match text/queries to concepts
CONCEPT_KEYWORDS = {
    "variables": ["variable", "var", "assign", "data type", "string", "integer", "float", "boolean"],
    "control flow": ["loop", "for", "while", "if", "else", "elif", "branch", "condition"],
    "functions": ["function", "def", "return", "argument", "parameter", "scope", "lambda"],
    "oop": ["oop", "polymorphism", "inheritance", "encapsulation", "abstraction"],
    "decorators": ["decorator", "wrapper", "decorated", "@"],
    "generators": ["generator", "yield", "next", "iterable", "iterator"],
    "classes": ["class", "object", "init", "self", "instance", "method"],
    "supervised learning": ["supervised", "labels", "training data", "classification", "regression"],
    "linear regression": ["regression", "linear", "slope", "intercept", "least squares", "mse"],
    "decision trees": ["tree", "decision tree", "entropy", "gini", "split", "random forest"],
    "overfitting": ["overfit", "overfitting", "high variance", "generalize", "train score", "test score"],
    "regularization": ["regularization", "l1", "l2", "lasso", "ridge", "penalty"],
    "neural networks": ["neural", "network", "layer", "neuron", "activation", "weights", "bias", "backpropagation"],
    "html/css": ["html", "css", "style", "div", "span", "layout", "flexbox", "grid"],
    "javascript dom": ["javascript", "js", "dom", "element", "event", "listener", "queryselector"],
    "rest apis": ["rest", "api", "http", "get", "post", "put", "delete", "endpoint", "request", "response"],
    "authentication": ["auth", "login", "password", "token", "jwt", "session", "cookie"],
    "onboarding": ["onboard", "orientation", "guidelines", "handbook", "welcome"],
    "compliance": ["compliance", "policy", "legal", "regulation", "standard"],
    "code of conduct": ["conduct", "harassment", "ethics", "behavior", "professionalism"]
}

# Clickable template questions for each concept
CONCEPT_SUGGESTIONS = {
    "variables": "What are the rules for declaring variables and data types in Python?",
    "control flow": "Can you explain how to write nested for-loops and while-loops in Python?",
    "functions": "How do scope, arguments, and return values work inside a Python function?",
    "oop": "Explain the four pillars of Object-Oriented Programming (OOP) with examples.",
    "decorators": "How do Python decorators work? Please show a step-by-step example.",
    "generators": "What is the difference between yield and return? How do generators work?",
    "classes": "How do I create a class and define the __init__ constructor in Python?",
    "supervised learning": "What is supervised learning and how does it differ from unsupervised learning?",
    "linear regression": "Explain the concept of linear regression and how we calculate the best-fit line.",
    "decision trees": "How does a decision tree decide where to split a node (Gini vs Entropy)?",
    "overfitting": "What is overfitting, and what are the most common ways to resolve it?",
    "regularization": "Explain Lasso (L1) and Ridge (L2) regularization in machine learning.",
    "neural networks": "How does backpropagation update weights in a multi-layer neural network?",
    "html/css": "What is the CSS box model, and how do Flexbox and Grid layouts differ?",
    "javascript dom": "How do I select, modify, and add event listeners to DOM elements in JS?",
    "rest apis": "Explain the REST API architectural constraints and standard HTTP methods.",
    "authentication": "What is the difference between session-based and token-based authentication?",
    "onboarding": "What are the key onboarding steps and guidelines for a new trainee?",
    "compliance": "Explain the mandatory corporate compliance policies I need to follow.",
    "code of conduct": "What is the company's code of conduct regarding workplace ethics?"
}

def get_completed_assignments(trainee_id: str) -> list[dict]:
    """Fetch completed exam assignments with questions and grading feedback."""
    try:
        conn = sqlite3.connect(str(_DB_PATH))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT a.answers, a.ai_feedback, e.questions
            FROM assignments a
            JOIN exams e ON a.exam_id = e.exam_id
            WHERE a.trainee_id = ? AND a.status = 'completed'
            """,
            (trainee_id,)
        )
        rows = cursor.fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"Error fetching completed assignments: {e}")
        return []

def identify_weak_concepts(trainee_id: str) -> list[str]:
    """Analyze incorrect quiz/exam questions and extract weak concept tags."""
    assignments = get_completed_assignments(trainee_id)
    weak_concepts = set()
    
    for a in assignments:
        try:
            feedback_data = json.loads(a["ai_feedback"]) if a["ai_feedback"] else {}
            questions = json.loads(a["questions"]) if a["questions"] else []
            q_feedbacks = feedback_data.get("questions", [])
            
            for q_f in q_feedbacks:
                idx = q_f.get("index")
                if idx is not None and idx < len(questions):
                    q = questions[idx]
                    score = q_f.get("score", 0.0)
                    max_marks = float(q.get("marks", 10.0))
                    # If trainee scored less than 70% of max marks, it's a weak area
                    if score < (max_marks * 0.7):
                        q_text = q.get("question", "").lower()
                        # Match concepts via keywords
                        for concept, keywords in CONCEPT_KEYWORDS.items():
                            for kw in keywords:
                                if kw in q_text:
                                    weak_concepts.add(concept)
                                    break
        except Exception as e:
            print(f"Error parsing assignment for weak areas: {e}")
            
    return list(weak_concepts)

def get_personalized_suggestions(trainee_id: str) -> list[str]:
    """Retrieve 3-4 dynamic chat prompts based on weak areas, falling back to domain-based defaults."""
    weak = identify_weak_concepts(trainee_id)
    suggestions = []
    
    # Add weak area suggestions
    if weak:
        for c in weak:
            if c in CONCEPT_SUGGESTIONS:
                suggestions.append(CONCEPT_SUGGESTIONS[c])
                if len(suggestions) >= 4:
                    break
                    
    # Fill remaining slots with domain-based defaults
    if len(suggestions) < 3:
        domain = "python"
        try:
            conn = sqlite3.connect(str(_DB_PATH))
            c = conn.cursor()
            c.execute("SELECT domain FROM users WHERE employee_id = ?", (trainee_id,))
            row = c.fetchone()
            if row:
                domain = row[0].lower()
            conn.close()
        except Exception:
            pass
            
        default_concepts = []
        if "python" in domain or "developer" in domain or "coding" in domain:
            default_concepts = ["variables", "control flow", "functions", "oop", "decorators"]
        elif "ml" in domain or "ai" in domain or "data" in domain:
            default_concepts = ["supervised learning", "linear regression", "overfitting", "neural networks"]
        elif "web" in domain or "front" in domain or "back" in domain:
            default_concepts = ["html/css", "javascript dom", "rest apis", "authentication"]
        else:
            default_concepts = ["onboarding", "compliance", "code of conduct"]
            
        for c in default_concepts:
            if c in CONCEPT_SUGGESTIONS and CONCEPT_SUGGESTIONS[c] not in suggestions:
                suggestions.append(CONCEPT_SUGGESTIONS[c])
                if len(suggestions) >= 4:
                    break
                    
    return suggestions[:4]

def get_related_concepts(query: str) -> list[str]:
    """Find related concept recommendations from the query text."""
    query_lower = query.lower()
    matched_concepts = []
    
    for concept, keywords in CONCEPT_KEYWORDS.items():
        for kw in keywords:
            if kw in query_lower:
                matched_concepts.append(concept)
                break
                
    related = set()
    for mc in matched_concepts:
        if mc in CONCEPT_MAP:
            for rel in CONCEPT_MAP[mc]:
                related.add(rel)
                
    # Exclude concepts already mentioned in query
    final_related = [r for r in related if r not in matched_concepts]
    return [r.title() for r in final_related[:3]]
