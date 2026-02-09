from app import db, app, Tool, Question
from app import User
with app.app_context():
    db.create_all()

    # create sample tools/questions if none exist
    if Tool.query.count() == 0:
        laser = Tool(name="Laser Cutter", description="Laser cutter safety")
        bandsaw = Tool(name="Bandsaw", description="Bandsaw safety")
        db.session.add_all([laser, bandsaw])
        db.session.commit()

        # simple sample questions (laser)
        q1 = Question(tool_id=laser.id,
                      text="Before starting the laser cutter you must always wear eye protection?",
                      option1="Yes", option2="No", option3="Only if advised", option4="Sometimes",
                      correct_option=1)
        q2 = Question(tool_id=laser.id,
                      text="Which of these is safe when using the laser cutter?",
                      option1="Loose clothing near the beam", option2="Tidy workspace", option3="Paper on cutter bed", option4="Wet materials",
                      correct_option=2)
        # bandsaw
        q3 = Question(tool_id=bandsaw.id,
                      text="Keep hands at a safe distance from the blade.",
                      option1="True", option2="False", option3="", option4="",
                      correct_option=1)
        q4 = Question(tool_id=bandsaw.id,
                      text="Use push-sticks for small pieces.",
                      option1="No", option2="Yes", option3="", option4="",
                      correct_option=2)
        db.session.add_all([q1, q2, q3, q4])
        db.session.commit()
        print("Sample tools and questions added.")
    else:
        print("Tools already exist.")

class Tool(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(255), nullable=False)
    questions = db.relationship("Question", backref="tool", lazy=True)

class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.String(255), nullable=False)
    answer = db.Column(db.String(100), nullable=False)
    tool_id = db.Column(db.Integer, db.ForeignKey("tool.id"), nullable=False)

