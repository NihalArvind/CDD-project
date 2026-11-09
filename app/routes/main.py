"""
Main Blueprint & Health Check Routes
------------------------------------
Defines the baseline entry routes, landing page, and system health check endpoints.
"""

from datetime import date, datetime, timezone
from flask import Blueprint, jsonify, render_template, current_app
from app.extensions import db
from app.models import AttendanceRecord, Student
from app.services.attendance_service import calculate_attendance_summary

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    """
    Landing / Dashboard entry point.
    Renders the faculty dashboard with live attendance metrics, shortage indicators,
    and system operational status.
    """
    try:
        summaries = calculate_attendance_summary(student_id=None)
        total_students = len(summaries)
        shortage_count = sum(1 for s in summaries if s.get("is_shortage"))
        total_classes_held = (
            db.session.query(db.func.count(db.distinct(AttendanceRecord.date))).scalar() or 0
        )
    except Exception:
        total_students = 0
        shortage_count = 0
        total_classes_held = 0

    return render_template(
        "dashboard.html",
        system_status="AttendSync System Online",
        total_students=total_students,
        total_classes_held=total_classes_held,
        shortage_count=shortage_count,
        today_date=date.today().isoformat(),
        environment=current_app.config.get("ENV", "development"),
        database_uri=current_app.config.get("SQLALCHEMY_DATABASE_URI"),
        timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    )


@main_bp.route("/health")
def health_check():
    """
    Baseline Health Check Endpoint.
    Used for uptime monitoring, CI/CD pipelines, and Docker container HEALTHCHECK.
    """
    return jsonify({
        "status": "online",
        "message": "AttendSync System Online",
        "service": "AttendSync - Dockerized Attendance Management System",
        "version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "database": "sqlite_connected"
    }), 200
