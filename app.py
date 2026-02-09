# Import necessary Flask and Python libraries
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os

from safety_engine import AdaptiveQuizEngine, SafetyScorePolicy, ToolSafetyPlanner

# Initialize Flask app and configure database
app = Flask(__name__)
basedir = os.path.abspath(os.path.dirname(__file__))
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{os.path.join(basedir, 'data', 'app.db')}"  # SQLite database stored in /data folder
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")  # Used for sessions and security

# ------------------------- DATABASE MODELS -------------------------
os.makedirs("data", exist_ok=True)  # make sure data folder exists

db = SQLAlchemy(app)  # Initialize SQLAlchemy ORM


# User model stores login credentials and role (student/teacher)
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    licenses = db.relationship("License", backref="user", lazy=True)
    results = db.relationship("Result", backref="user", lazy=True)


# Tool model stores tool name and description, and links to related questions and licenses
class Tool(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=True)
    questions = db.relationship("Question", backref="tool", lazy=True)
    licenses = db.relationship("License", backref="tool", lazy=True)
    results = db.relationship("Result", backref="tool", lazy=True)


# Question model stores quiz questions, 4 multiple choice options, and correct answer
class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.String(255), nullable=False)
    option_a = db.Column(db.String(255))
    option_b = db.Column(db.String(255))
    option_c = db.Column(db.String(255))
    option_d = db.Column(db.String(255))
    correct_answer = db.Column(db.String(1))  # Correct answer: 'A', 'B', 'C', or 'D'
    image_filename = db.Column(db.String(255), nullable=True)
    tool_id = db.Column(db.Integer, db.ForeignKey("tool.id"), nullable=False)
    weight = db.Column(db.Integer, default=0)


class StudentAnswer(db.Model):
    __tablename__ = "studentanswers"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey("question.id"), nullable=False)
    tool_id = db.Column(db.Integer, db.ForeignKey("tool.id"), nullable=False)
    selected_answer = db.Column(db.String(10))
    is_correct = db.Column(db.Boolean)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


class Result(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    tool_id = db.Column(db.Integer, db.ForeignKey("tool.id"), nullable=False)
    score = db.Column(db.Float, nullable=False)
    passed = db.Column(db.Boolean, default=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)


class License(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    tool_id = db.Column(db.Integer, db.ForeignKey("tool.id"), nullable=False)
    issued_date = db.Column(db.DateTime, default=datetime.utcnow)
    revoked = db.Column(db.Boolean, default=False)


# ------------------------- HELPER FUNCTIONS -------------------------

# Get the currently logged-in user from the session
def current_user():
    if "user_id" in session:
        return User.query.get(session["user_id"])
    return None


# Decorator to restrict access to logged-in users only
def login_required(f):
    from functools import wraps

    @wraps(f)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return wrapped


# Decorator to restrict access by role (e.g. teacher-only pages)
def role_required(required_role):
    from functools import wraps

    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("login"))

            user = User.query.get(session["user_id"])
            if not user or user.role != required_role:
                flash("Access denied.")
                return redirect(url_for("dashboard"))

            return f(*args, **kwargs)

        return wrapped

    return decorator


# ------------------------- ROUTES -------------------------

# Redirect root URL to dashboard or login
@app.route("/")
def home():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


# ------------------------- REGISTER -------------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        role = request.form["role"]

        # Validation checks
        if not username or not password:
            flash("Enter username and password")
            return redirect(url_for("register"))
        if User.query.filter_by(username=username).first():
            flash("Username already taken")
            return redirect(url_for("register"))

        # Create new user and hash password
        pw_hash = generate_password_hash(password)
        user = User(username=username, password_hash=pw_hash, role=role)
        db.session.add(user)
        db.session.commit()
        flash("Registered. Please log in.")
        return redirect(url_for("login"))

    return render_template("register.html")


# ------------------------- LOGIN -------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        user = User.query.filter_by(username=username).first()

        # Check password validity
        if user and check_password_hash(user.password_hash, password):
            session["user_id"] = user.id
            session["role"] = user.role
            flash("Logged in")
            return redirect(url_for("dashboard"))
        flash("Invalid credentials")
        return redirect(url_for("login"))
    return render_template("login.html")


# ------------------------- LOGOUT -------------------------
@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out")
    return redirect(url_for("login"))


# ------------------------- DASHBOARD -------------------------
@app.route("/dashboard")
@login_required
def dashboard():
    user = current_user()
    if user is None:
        flash("Please log in to continue.")
        return redirect(url_for("login"))

    # Show different content depending on user role
    if user.role == "student":
        tools = Tool.query.all()
        lic_map = {l.tool_id: l for l in user.licenses if not l.revoked}
        return render_template("dashboard.html", role="student", tools=tools, lic_map=lic_map)
    if user.role == "teacher":
        students = User.query.filter_by(role="student").all()
        return render_template("dashboard.html", role="teacher", students=students)

    flash("Invalid user role.")
    return redirect(url_for("logout"))


# ------------------------- TOOLS MANAGEMENT -------------------------
@app.route("/tools", methods=["GET", "POST"])
@login_required
def tools():
    user = current_user()

    # Teachers can add new tools
    if request.method == "POST":
        if user.role != "teacher":
            flash("Not allowed")
            return redirect(url_for("tools"))
        name = request.form.get("name")
        desc = request.form.get("description", "")
        if name:
            t = Tool(name=name, description=desc)
            db.session.add(t)
            db.session.commit()
            flash("Tool added")
            return redirect(url_for("tools"))

    tools = Tool.query.all()
    return render_template("tools.html", tools=tools, role=user.role)


# ------------------------- QUIZ SYSTEM -------------------------
@app.route("/tool/<int:tool_id>/quiz", methods=["GET", "POST"])
@login_required
def quiz(tool_id):
    user = current_user()
    tool = Tool.query.get_or_404(tool_id)
    questions = Question.query.filter_by(tool_id=tool_id).all()

    if not questions:
        flash("No questions for this tool yet.")
        return redirect(url_for("tools"))

    qcount = min(5, len(questions))
    engine = AdaptiveQuizEngine(questions, tool.name)

    if request.method == "GET":
        selected_ids = engine.select_question_ids(qcount)
        session[f"quiz_questions_{tool_id}"] = selected_ids
        selected_set = set(selected_ids)
        questions_sample = [q for q in questions if q.id in selected_set]
        questions_sample.sort(key=lambda q: selected_ids.index(q.id))
        return render_template("quiz.html", tool=tool, questions=questions_sample)

    selected_ids = session.get(f"quiz_questions_{tool_id}")
    if not selected_ids:
        flash("Quiz session expired. Please try again.")
        return redirect(url_for("tools"))
    selected_set = set(selected_ids)
    questions_sample = [q for q in questions if q.id in selected_set]
    questions_sample.sort(key=lambda q: selected_ids.index(q.id))

    correct_map = {}
    for question in questions_sample:
        answer = request.form.get(f"q_{question.id}")
        is_correct = (
            answer
            and answer.strip().upper() == (question.correct_answer or "").strip().upper()
        )
        correct_map[question.id] = bool(is_correct)

        if is_correct:
            question.weight = max(0, question.weight - 1)
        else:
            question.weight += 2

        sa = StudentAnswer(
            user_id=user.id,
            question_id=question.id,
            tool_id=tool.id,
            selected_answer=answer if answer else "",
            is_correct=bool(is_correct),
        )
        db.session.add(sa)

    policy = SafetyScorePolicy(tool.name)
    score = policy.weighted_score(correct_map, engine.difficulty_map())
    passed = score >= policy.pass_threshold()
    result = Result(user_id=user.id, tool_id=tool.id, score=score, passed=passed)
    db.session.add(result)
    db.session.commit()

    if passed:
        existing = License.query.filter_by(user_id=user.id, tool_id=tool.id, revoked=False).first()
        if not existing:
            lic = License(user_id=user.id, tool_id=tool.id)
            db.session.add(lic)
            db.session.commit()

    session.pop(f"quiz_questions_{tool_id}", None)
    return redirect(url_for("result", result_id=result.id))


# ------------------------- ADD QUESTION -------------------------
@app.route("/add_question/<int:tool_id>", methods=["GET", "POST"])
def add_question(tool_id):
    # Ensure teacher access only
    if "user_id" not in session:
        return redirect(url_for("login"))
    user = User.query.get(session["user_id"])
    if user.role != "teacher":
        flash("Access denied.")
        return redirect(url_for("dashboard"))

    tool = Tool.query.get_or_404(tool_id)

    # Add new question to tool
    if request.method == "POST":
        text_value = request.form["text"]
        option_a = request.form["option_a"]
        option_b = request.form["option_b"]
        option_c = request.form["option_c"]
        option_d = request.form["option_d"]
        correct_answer = request.form["correct_answer"]
        image_filename = request.form.get("image_filename", "").strip()
        new_question = Question(
            text=text_value,
            option_a=option_a,
            option_b=option_b,
            option_c=option_c,
            option_d=option_d,
            correct_answer=correct_answer,
            image_filename=image_filename if image_filename else None,
            tool_id=tool.id,
        )
        db.session.add(new_question)
        db.session.commit()
        flash("Question added successfully!")
        return redirect(url_for("tools"))

    return render_template("add_question.html", tool=tool)


@app.route("/tool_report/<int:tool_id>")
@role_required("teacher")
def tool_report(tool_id):

    # PARAMETERISED SQL JOIN
    sql = text(
        """
    SELECT q.id AS question_id,
           q.text AS question_text,
           COUNT(a.id) AS attempts,
           SUM(CASE WHEN a.is_correct = 1 THEN 1 ELSE 0 END) AS correct_count
    FROM question q
    LEFT JOIN studentanswers a ON a.question_id = q.id
    WHERE q.tool_id = :tool_id
    GROUP BY q.id;
"""
    )

    result = db.session.execute(sql, {"tool_id": tool_id}).fetchall()

    # Fetch tool info
    tool = Tool.query.get_or_404(tool_id)

    return render_template("tool_report.html", tool=tool, data=result)


# ------------------------- DELETE QUESTION -------------------------
@app.route("/delete_question/<int:question_id>", methods=["POST"])
def delete_question(question_id):
    # Ensure teacher access only
    if "user_id" not in session:
        return redirect(url_for("login"))
    user = User.query.get(session["user_id"])
    if user.role != "teacher":
        flash("Access denied.")
        return redirect(url_for("dashboard"))

    question = Question.query.get_or_404(question_id)
    tool_id = question.tool_id
    db.session.delete(question)
    db.session.commit()
    flash("Question deleted successfully!")
    return redirect(url_for("tools"))


# ------------------------- WEIGHT DASHBOARD-------------------------
@app.route("/weights/<int:tool_id>")
@login_required
def weight_dashboard(tool_id):
    user = current_user()
    if user.role != "teacher":
        flash("Access denied.")
        return redirect(url_for("dashboard"))

    tool = Tool.query.get_or_404(tool_id)
    questions = Question.query.filter_by(tool_id=tool_id).order_by(Question.weight.desc()).all()

    return render_template("weights.html", tool=tool, questions=questions)


# ------------------------- VIEW WEIGHTS-------------------------
@app.route("/tool/<int:tool_id>/weights")
def view_weights(tool_id):
    tool = Tool.query.get_or_404(tool_id)
    questions = Question.query.filter_by(tool_id=tool_id).all()

    # Calculate total weight
    total_weight = sum(q.weight for q in questions)

    return render_template("weights.html", tool=tool, questions=questions, total_weight=total_weight)


# ------------------------- RESULT DISPLAY -------------------------
@app.route("/result/<int:result_id>")
@login_required
def result(result_id):
    r = Result.query.get_or_404(result_id)
    planner = ToolSafetyPlanner()
    learning_path = planner.learning_path()
    return render_template("result.html", result=r, learning_path=learning_path)


# ------------------------- DATABASE INITIALISATION -------------------------
with app.app_context():
    db.create_all()  # Create all database tables if not already existing


# ------------------------- RUN APP -------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=81, debug=True)  # Run on all interfaces (useful for Codespaces)
