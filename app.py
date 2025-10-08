from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import random
import os

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///database.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")

db = SQLAlchemy(app)

# ----------------------
# Models
# ----------------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'student' or 'teacher'
    licenses = db.relationship("License", backref="user", lazy=True)
    results = db.relationship("Result", backref="user", lazy=True)

class Tool(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=True)
    questions = db.relationship("Question", backref="tool", lazy=True)
    licenses = db.relationship("License", backref="tool", lazy=True)

class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tool_id = db.Column(db.Integer, db.ForeignKey("tool.id"), nullable=False)
    text = db.Column(db.Text, nullable=False)
    option1 = db.Column(db.String(200), nullable=False)
    option2 = db.Column(db.String(200), nullable=False)
    option3 = db.Column(db.String(200), nullable=True)
    option4 = db.Column(db.String(200), nullable=True)
    correct_option = db.Column(db.Integer, nullable=False)  # 1..4

class Result(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    tool_id = db.Column(db.Integer, db.ForeignKey("tool.id"), nullable=False)
    score = db.Column(db.Float, nullable=False)  # percentage
    passed = db.Column(db.Boolean, default=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)

class License(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    tool_id = db.Column(db.Integer, db.ForeignKey("tool.id"), nullable=False)
    issued_date = db.Column(db.DateTime, default=datetime.utcnow)
    revoked = db.Column(db.Boolean, default=False)

# ----------------------
# Helpers
# ----------------------
def current_user():
    if "user_id" in session:
        return User.query.get(session["user_id"])
    return None

def login_required(f):
    from functools import wraps
    @wraps(f)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapped

# ----------------------
# Routes
# ----------------------
@app.route("/")
def home():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        role = request.form["role"]
        if not username or not password:
            flash("Enter username and password")
            return redirect(url_for("register"))
        if User.query.filter_by(username=username).first():
            flash("Username already taken")
            return redirect(url_for("register"))
        pw_hash = generate_password_hash(password)
        user = User(username=username, password_hash=pw_hash, role=role)
        db.session.add(user)
        db.session.commit()
        flash("Registered. Please log in.")
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            session["user_id"] = user.id
            session["role"] = user.role
            flash("Logged in")
            return redirect(url_for("dashboard"))
        flash("Invalid credentials")
        return redirect(url_for("login"))
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out")
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required
def dashboard():
    user = current_user()
    if user.role == "student":
        tools = Tool.query.all()
        # check licenses
        lic_map = { (l.tool_id): l for l in user.licenses if not l.revoked }
        return render_template("dashboard.html", role="student", tools=tools, lic_map=lic_map)
    else:
        students = User.query.filter_by(role="student").all()
        return render_template("dashboard.html", role="teacher", students=students)

@app.route("/tools", methods=["GET", "POST"])
@login_required
def tools():
    # Teacher can add tools; students see list & take quizzes
    user = current_user()
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

@app.route("/tool/<int:tool_id>/quiz", methods=["GET", "POST"])
@login_required
def quiz(tool_id):
    user = current_user()
    tool = Tool.query.get_or_404(tool_id)
    questions = Question.query.filter_by(tool_id=tool_id).all()
    if not questions:
        flash("No questions for this tool yet.")
        return redirect(url_for("tools"))

    # choose up to 5 random questions
    qcount = min(5, len(questions))
    questions_sample = random.sample(questions, qcount)

    if request.method == "POST":
        # evaluate
        total = len(questions_sample)
        correct = 0
        for q in questions_sample:
            selected = request.form.get(f"q_{q.id}")
            if selected and int(selected) == q.correct_option:
                correct += 1
        score = (correct / total) * 100
        passed = score >= 60  # pass threshold
        result = Result(user_id=user.id, tool_id=tool_id, score=score, passed=passed)
        db.session.add(result)
        db.session.commit()

        if passed:
            existing = License.query.filter_by(user_id=user.id, tool_id=tool_id, revoked=False).first()
            if not existing:
                lic = License(user_id=user.id, tool_id=tool_id)
                db.session.add(lic)
                db.session.commit()
        return redirect(url_for("result", result_id=result.id))

    return render_template("quiz.html", tool=tool, questions=questions_sample)

@app.route("/result/<int:result_id>")
@login_required
def result(result_id):
    r = Result.query.get_or_404(result_id)
    return render_template("result.html", result=r)

# ----------------------
# Run
# ----------------------
if __name__ == "__main__":
    app.run(debug=True)
