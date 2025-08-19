import json
import os
import shutil
from typing import List, Dict

from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, abort
from flask_login import LoginManager, login_user, logout_user, login_required, current_user

from config import Config, ensure_directories
from database import db
from models import User, Lesson, Announcement, Quiz, QuizQuestion, QuizSubmission, QuizAnswer
from notifications import Notifier
from utils import role_required


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)

    ensure_directories(app.config)

    db.init_app(app)

    login_manager = LoginManager(app)
    login_manager.login_view = "login"

    notifier = Notifier(app.config)

    # Jinja filter to load JSON strings
    @app.template_filter("loads")
    def jinja_loads_filter(value):
        try:
            return json.loads(value) if value else []
        except Exception:
            return []

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    @app.context_processor
    def inject_globals():
        return {"current_user": current_user}

    @app.route("/uploads/<path:filename>")
    @login_required
    def uploaded_file(filename):
        return send_from_directory(app.config["UPLOAD_FOLDER"], filename, as_attachment=True)

    @app.route("/")
    def index():
        if current_user.is_authenticated:
            return redirect(url_for("dashboard"))
        return redirect(url_for("login"))

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            role = request.form.get("role", "student")
            parent_email = request.form.get("parent_email", "").strip()
            parent_whatsapp = request.form.get("parent_whatsapp", "").strip()

            if not name or not email or not password or role not in ("teacher", "student"):
                flash("Please fill all required fields.", "error")
                return render_template("register.html")

            if User.query.filter_by(email=email).first():
                flash("Email already registered.", "error")
                return render_template("register.html")

            user = User(name=name, email=email, role=role)
            if role == "student":
                user.parent_email = parent_email
                user.parent_whatsapp = parent_whatsapp
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            flash("Registration successful. Please log in.", "success")
            return redirect(url_for("login"))
        return render_template("register.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            user = User.query.filter_by(email=email).first()
            if not user or not user.check_password(password):
                flash("Invalid credentials.", "error")
                return render_template("login.html")
            login_user(user)
            return redirect(url_for("dashboard"))
        return render_template("login.html")

    @app.route("/logout")
    @login_required
    def logout():
        logout_user()
        return redirect(url_for("login"))

    @app.route("/dashboard")
    @login_required
    def dashboard():
        if current_user.role == "teacher":
            quizzes = Quiz.query.filter_by(created_by_id=current_user.id).order_by(Quiz.created_at.desc()).all()
            return render_template("teacher_dashboard.html", quizzes=quizzes)
        else:
            announcements = Announcement.query.order_by(Announcement.created_at.desc()).all()
            quizzes = Quiz.query.filter_by(is_active=True).order_by(Quiz.created_at.desc()).all()
            lessons = Lesson.query.order_by(Lesson.created_at.desc()).all()
            return render_template("student_dashboard.html", announcements=announcements, quizzes=quizzes, lessons=lessons)

    # Lessons
    @app.route("/lessons", methods=["GET", "POST"])
    @login_required
    def lessons_page():
        if request.method == "POST":
            if current_user.role != "teacher":
                abort(403)
            title = request.form.get("title", "").strip()
            description = request.form.get("description", "").strip()
            uploaded = request.files.get("file")
            file_path = None
            if uploaded and uploaded.filename:
                filename = uploaded.filename
                safe_name = filename
                file_dir = app.config["UPLOAD_FOLDER"]
                os.makedirs(file_dir, exist_ok=True)
                destination = os.path.join(file_dir, safe_name)
                uploaded.save(destination)
                file_path = safe_name
            lesson = Lesson(title=title, description=description, file_path=file_path, created_by=current_user)
            db.session.add(lesson)
            db.session.commit()
            flash("Lesson uploaded.", "success")
            return redirect(url_for("lessons_page"))
        all_lessons = Lesson.query.order_by(Lesson.created_at.desc()).all()
        return render_template("lessons.html", lessons=all_lessons)

    # Announcements
    @app.route("/announcements", methods=["GET", "POST"])
    @login_required
    def announcements_page():
        if request.method == "POST":
            if current_user.role != "teacher":
                abort(403)
            title = request.form.get("title", "").strip()
            content = request.form.get("content", "").strip()
            ann = Announcement(title=title, content=content, created_by=current_user)
            db.session.add(ann)
            db.session.commit()
            flash("Announcement posted.", "success")
            return redirect(url_for("announcements_page"))
        all_ann = Announcement.query.order_by(Announcement.created_at.desc()).all()
        return render_template("announcements.html", announcements=all_ann)

    # Quizzes
    @app.route("/quiz/create", methods=["GET", "POST"])
    @login_required
    @role_required("teacher")
    def quiz_create():
        if request.method == "POST":
            title = request.form.get("title", "").strip()
            description = request.form.get("description", "").strip()
            quiz = Quiz(title=title, description=description, created_by=current_user)
            db.session.add(quiz)
            db.session.flush()

            # Parse dynamic questions
            total_questions = int(request.form.get("total_questions", 0))
            for i in range(1, total_questions + 1):
                q_text = request.form.get(f"q{i}_text", "").strip()
                q_type = request.form.get(f"q{i}_type", "mcq")
                points = int(request.form.get(f"q{i}_points", 1))
                options_json = None
                correct_answer = None
                if q_type == "mcq":
                    options = [o for o in request.form.getlist(f"q{i}_options") if o.strip()]
                    options_json = json.dumps(options)
                    correct_answer = request.form.get(f"q{i}_correct", "").strip()
                question = QuizQuestion(
                    quiz=quiz,
                    question_text=q_text,
                    question_type=q_type,
                    options_json=options_json,
                    correct_answer=correct_answer,
                    points=points,
                )
                db.session.add(question)
            db.session.commit()
            flash("Quiz created.", "success")
            return redirect(url_for("dashboard"))
        return render_template("quiz_create.html")

    @app.route("/quiz/manage")
    @login_required
    @role_required("teacher")
    def quiz_manage():
        quizzes = Quiz.query.filter_by(created_by_id=current_user.id).order_by(Quiz.created_at.desc()).all()
        return render_template("quiz_manage.html", quizzes=quizzes)

    @app.route("/quiz/<int:quiz_id>", methods=["GET", "POST"])
    @login_required
    def quiz_take(quiz_id: int):
        quiz = Quiz.query.get_or_404(quiz_id)
        if request.method == "POST":
            submission = QuizSubmission(quiz=quiz, student=current_user)
            db.session.add(submission)
            db.session.flush()

            total_score = 0
            fully_graded = True

            for question in quiz.questions:
                field_name = f"q_{question.id}"
                file_field = f"q_{question.id}_file"
                answer_text = None
                file_path = None
                is_correct = None
                score = None

                if question.question_type == "file":
                    uploaded = request.files.get(file_field)
                    if uploaded and uploaded.filename:
                        safe_name = f"answer_{submission.id}_{question.id}_{uploaded.filename}"
                        destination = os.path.join(app.config["UPLOAD_FOLDER"], safe_name)
                        uploaded.save(destination)
                        file_path = safe_name
                        fully_graded = False
                else:
                    answer_text = request.form.get(field_name, "")
                    if question.question_type == "mcq":
                        is_correct = (answer_text.strip() == (question.correct_answer or "").strip())
                        score = question.points if is_correct else 0
                        total_score += score
                    else:
                        # text: needs manual grading
                        fully_graded = False

                ans = QuizAnswer(
                    submission=submission,
                    question=question,
                    answer_text=answer_text,
                    file_path=file_path,
                    is_correct=is_correct,
                    score=score,
                )
                db.session.add(ans)

            submission.total_score = total_score if fully_graded else None
            submission.graded = fully_graded
            db.session.commit()

            # Notify parents if student and config enabled
            if current_user.role == "student" and app.config.get("AUTO_NOTIFY_PARENTS", True):
                summary = f"Student {current_user.name} submitted quiz '{quiz.title}'."
                if submission.graded:
                    summary += f" Score: {submission.total_score}."
                else:
                    summary += " Grading pending for some answers."
                if current_user.parent_email:
                    notifier.send_email(current_user.parent_email, "Quiz submission update", summary)
                if current_user.parent_whatsapp:
                    notifier.send_whatsapp(current_user.parent_whatsapp, summary)

            flash("Submission received.", "success")
            return redirect(url_for("dashboard"))

        return render_template("quiz_take.html", quiz=quiz)

    @app.route("/quiz/<int:quiz_id>/results")
    @login_required
    def quiz_results(quiz_id: int):
        quiz = Quiz.query.get_or_404(quiz_id)
        if current_user.role == "teacher":
            submissions = QuizSubmission.query.filter_by(quiz_id=quiz.id).order_by(QuizSubmission.submitted_at.desc()).all()
            return render_template("quiz_results.html", quiz=quiz, submissions=submissions)
        else:
            submission = QuizSubmission.query.filter_by(quiz_id=quiz.id, student_id=current_user.id).order_by(QuizSubmission.submitted_at.desc()).first()
            if not submission:
                flash("No submissions yet.", "info")
                return redirect(url_for("dashboard"))
            return render_template("quiz_results.html", quiz=quiz, submissions=[submission])

    @app.route("/quiz/<int:submission_id>/grade", methods=["POST"]) 
    @login_required
    @role_required("teacher")
    def quiz_grade_submission(submission_id: int):
        submission = QuizSubmission.query.get_or_404(submission_id)
        total = 0
        for ans in submission.answers:
            if ans.question.question_type in ("text", "file"):
                try:
                    score = int(request.form.get(f"score_{ans.id}", "0"))
                except ValueError:
                    score = 0
                ans.score = max(0, min(score, ans.question.points))
            if ans.score is None:
                ans.score = 0
            total += ans.score
            ans.is_correct = None if ans.question.question_type != "mcq" else ans.is_correct
        submission.total_score = total
        submission.graded = True
        db.session.commit()

        # Notify parents with final score
        student = submission.student
        quiz = submission.quiz
        summary = f"Student {student.name} graded for quiz '{quiz.title}'. Score: {submission.total_score}."
        if student.parent_email:
            notifier.send_email(student.parent_email, "Quiz result", summary)
        if student.parent_whatsapp:
            notifier.send_whatsapp(student.parent_whatsapp, summary)

        flash("Submission graded and parents notified.", "success")
        return redirect(url_for("quiz_results", quiz_id=submission.quiz_id))

    @app.route("/quiz/<int:quiz_id>/toggle", methods=["POST"]) 
    @login_required
    @role_required("teacher")
    def quiz_toggle(quiz_id: int):
        quiz = Quiz.query.get_or_404(quiz_id)
        quiz.is_active = not quiz.is_active
        db.session.commit()
        return redirect(url_for("quiz_manage"))

    @app.route("/reset", methods=["POST"]) 
    @login_required
    @role_required("teacher")
    def reset():
        # Danger: clears all data and uploads
        upload_dir = app.config["UPLOAD_FOLDER"]
        if os.path.isdir(upload_dir):
            for name in os.listdir(upload_dir):
                try:
                    path = os.path.join(upload_dir, name)
                    if os.path.isfile(path):
                        os.remove(path)
                    else:
                        shutil.rmtree(path, ignore_errors=True)
                except Exception:
                    pass
        # Recreate database
        db.drop_all()
        db.create_all()
        flash("Application data reset.", "success")
        return redirect(url_for("dashboard"))

    with app.app_context():
        db.create_all()

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)