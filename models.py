from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from database import db


class User(db.Model, UserMixin):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'teacher' or 'student'

    # Student-only fields for parent contacts
    parent_email = db.Column(db.String(255))
    parent_whatsapp = db.Column(db.String(50))

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


class Lesson(db.Model):
    __tablename__ = "lessons"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    file_path = db.Column(db.String(500))
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_by = db.relationship("User", backref=db.backref("lessons", lazy=True))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Announcement(db.Model):
    __tablename__ = "announcements"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_by = db.relationship("User", backref=db.backref("announcements", lazy=True))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Quiz(db.Model):
    __tablename__ = "quizzes"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_by = db.relationship("User", backref=db.backref("quizzes", lazy=True))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)


class QuizQuestion(db.Model):
    __tablename__ = "quiz_questions"

    id = db.Column(db.Integer, primary_key=True)
    quiz_id = db.Column(db.Integer, db.ForeignKey("quizzes.id"), nullable=False)
    quiz = db.relationship("Quiz", backref=db.backref("questions", lazy=True, cascade="all, delete-orphan"))

    question_text = db.Column(db.Text, nullable=False)
    question_type = db.Column(db.String(20), nullable=False)  # 'mcq', 'text', 'file'
    options_json = db.Column(db.Text)  # JSON string for MCQ options
    correct_answer = db.Column(db.Text)  # For MCQ only
    points = db.Column(db.Integer, default=1)


class QuizSubmission(db.Model):
    __tablename__ = "quiz_submissions"

    id = db.Column(db.Integer, primary_key=True)
    quiz_id = db.Column(db.Integer, db.ForeignKey("quizzes.id"), nullable=False)
    quiz = db.relationship("Quiz", backref=db.backref("submissions", lazy=True, cascade="all, delete-orphan"))

    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    student = db.relationship("User", backref=db.backref("submissions", lazy=True))

    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    total_score = db.Column(db.Integer)
    graded = db.Column(db.Boolean, default=False)


class QuizAnswer(db.Model):
    __tablename__ = "quiz_answers"

    id = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(db.Integer, db.ForeignKey("quiz_submissions.id"), nullable=False)
    submission = db.relationship(
        "QuizSubmission",
        backref=db.backref("answers", lazy=True, cascade="all, delete-orphan"),
    )

    question_id = db.Column(db.Integer, db.ForeignKey("quiz_questions.id"), nullable=False)
    question = db.relationship("QuizQuestion")

    answer_text = db.Column(db.Text)
    file_path = db.Column(db.String(500))

    is_correct = db.Column(db.Boolean)
    score = db.Column(db.Integer)