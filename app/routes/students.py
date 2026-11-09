"""
Student Management Routes
--------------------------
Handles student directory listing, new student registration with USN uniqueness validation,
and student profile deletion with cascading attendance record cleanup.
"""

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from sqlalchemy.exc import IntegrityError
from app.extensions import db
from app.models import Student

students_bp = Blueprint("students", __name__)


def _is_json_request() -> bool:
    """Helper to detect if incoming client request expects JSON response."""
    return request.is_json or request.headers.get("Accept") == "application/json"


@students_bp.route("/students", methods=["GET"])
@students_bp.route("/students/", methods=["GET"])
def list_students():
    """
    GET /students
    Lists all registered engineering students ordered alphabetically by USN.
    Supports both Jinja2 HTML presentation and JSON API consumption.
    """
    students = Student.query.order_by(Student.usn.asc()).all()

    if _is_json_request():
        return jsonify({
            "status": "success",
            "count": len(students),
            "students": [s.to_dict() for s in students]
        }), 200

    return render_template("students.html", students=students)


@students_bp.route("/students/add", methods=["POST"])
def add_student():
    """
    POST /students/add
    Accepts form data (or JSON payload) to register a new student.
    Performs field validation, verifies USN uniqueness, handles database errors gracefully,
    and returns informative flash feedback banners.
    """
    data = request.get_json(silent=True) if request.is_json else request.form

    usn = (data.get("usn") or "").strip().upper()
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    department = (data.get("department") or "").strip()
    semester_raw = data.get("semester")
    section = (data.get("section") or "").strip().upper()

    # 1. Required fields presence check
    missing_fields = []
    if not usn:
        missing_fields.append("USN")
    if not name:
        missing_fields.append("Name")
    if not email:
        missing_fields.append("Email")
    if not department:
        missing_fields.append("Department")
    if semester_raw is None or str(semester_raw).strip() == "":
        missing_fields.append("Semester")
    if not section:
        missing_fields.append("Section")

    if missing_fields:
        error_msg = f"Validation Error: Missing required fields: {', '.join(missing_fields)}."
        flash(error_msg, "danger")
        if _is_json_request():
            return jsonify({"status": "error", "message": error_msg, "missing_fields": missing_fields}), 400
        return redirect(url_for("students.list_students"))

    # 2. Semester range validation (1-8)
    try:
        semester = int(semester_raw)
        if semester < 1 or semester > 8:
            raise ValueError()
    except (ValueError, TypeError):
        error_msg = f"Validation Error: Semester '{semester_raw}' is invalid. Must be an integer between 1 and 8."
        flash(error_msg, "danger")
        if _is_json_request():
            return jsonify({"status": "error", "message": error_msg}), 400
        return redirect(url_for("students.list_students"))

    # 3. Email format basic validation
    if "@" not in email or "." not in email:
        error_msg = f"Validation Error: Email address '{email}' is not valid."
        flash(error_msg, "danger")
        if _is_json_request():
            return jsonify({"status": "error", "message": error_msg}), 400
        return redirect(url_for("students.list_students"))

    # 4. Check USN uniqueness
    existing_usn = Student.query.filter(Student.usn.ilike(usn)).first()
    if existing_usn:
        error_msg = f"Duplicate Error: Student with USN '{usn}' is already registered (assigned to '{existing_usn.name}')."
        flash(error_msg, "danger")
        if _is_json_request():
            return jsonify({"status": "error", "message": error_msg, "field": "usn"}), 400
        return redirect(url_for("students.list_students"))

    # 5. Check Email uniqueness
    existing_email = Student.query.filter(Student.email.ilike(email)).first()
    if existing_email:
        error_msg = f"Duplicate Error: Student email '{email}' is already in use by '{existing_email.name}' ({existing_email.usn})."
        flash(error_msg, "danger")
        if _is_json_request():
            return jsonify({"status": "error", "message": error_msg, "field": "email"}), 400
        return redirect(url_for("students.list_students"))

    # 6. Database persistence with rollback safety
    try:
        new_student = Student(
            usn=usn,
            name=name,
            email=email,
            department=department,
            semester=semester,
            section=section
        )
        db.session.add(new_student)
        db.session.commit()

        success_msg = f"Student '{new_student.name}' ({new_student.usn}) was successfully registered!"
        flash(success_msg, "success")

        if _is_json_request():
            return jsonify({
                "status": "success",
                "message": success_msg,
                "data": new_student.to_dict()
            }), 201

        return redirect(url_for("students.list_students"))

    except IntegrityError as exc:
        db.session.rollback()
        error_msg = "Database Integrity Error: A student with this USN or email already exists."
        flash(error_msg, "danger")
        if _is_json_request():
            return jsonify({"status": "error", "message": error_msg}), 400
        return redirect(url_for("students.list_students"))

    except Exception as exc:
        db.session.rollback()
        error_msg = f"Failed to register student: {str(exc)}"
        flash(error_msg, "danger")
        if _is_json_request():
            return jsonify({"status": "error", "message": error_msg}), 500
        return redirect(url_for("students.list_students"))


@students_bp.route("/students/<int:id>/delete", methods=["POST"])
def delete_student(id: int):
    """
    POST /students/<int:id>/delete
    Deletes an enrolled student by primary key ID and cascades deletion of
    all their associated daily attendance records.
    """
    student = db.session.get(Student, id) if hasattr(db.session, "get") else Student.query.get(id)

    if not student:
        error_msg = f"Cannot delete: Student with ID #{id} was not found."
        flash(error_msg, "danger")
        if _is_json_request():
            return jsonify({"status": "error", "message": error_msg, "code": 404}), 404
        return redirect(url_for("students.list_students"))

    student_name = student.name
    student_usn = student.usn

    try:
        db.session.delete(student)
        db.session.commit()

        success_msg = f"Student '{student_name}' ({student_usn}) and related attendance records were successfully deleted."
        flash(success_msg, "success")

        if _is_json_request():
            return jsonify({
                "status": "success",
                "message": success_msg,
                "deleted_id": id,
                "usn": student_usn
            }), 200

        return redirect(url_for("students.list_students"))

    except Exception as exc:
        db.session.rollback()
        error_msg = f"Failed to delete student: {str(exc)}"
        flash(error_msg, "danger")
        if _is_json_request():
            return jsonify({"status": "error", "message": error_msg}), 500
        return redirect(url_for("students.list_students"))
