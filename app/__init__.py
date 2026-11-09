"""
AttendSync Application Factory
------------------------------
Implements the Application Factory pattern (create_app) for modularity,
simplified automated testing, and Docker container lifecycle management.
"""

import os
from flask import Flask, jsonify, render_template, request
from config import config_by_name
from app.extensions import db


def create_app(config_name=None):
    """
    Constructs and configures a Flask application instance.

    Args:
        config_name (str): The configuration environment name ('development', 'testing', 'production').
                          Defaults to FLASK_ENV or 'development'.

    Returns:
        Flask: The configured Flask application instance.
    """
    if config_name is None:
        config_name = os.getenv("FLASK_ENV", "development").lower()

    app = Flask(
        __name__,
        instance_relative_config=True,
        template_folder="templates",
        static_folder="static"
    )

    # 1. Bind configuration
    config_class = config_by_name.get(config_name, config_by_name["default"])
    app.config.from_object(config_class)

    # 2. Ensure instance folder exists for persistent SQLite database
    os.makedirs(app.instance_path, exist_ok=True)

    # 3. Initialize extensions
    db.init_app(app)

    # 4. Register Blueprints
    from app.routes.main import main_bp
    from app.routes.students import students_bp
    from app.routes.attendance import attendance_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(students_bp)
    app.register_blueprint(attendance_bp)

    # 5. Register Error Handlers
    register_error_handlers(app)

    # 6. Register Custom CLI Commands
    from app.commands import register_commands
    register_commands(app)

    # 7. Shell Context for CLI debugging
    @app.shell_context_processor
    def make_shell_context():
        from app.models import Student, AttendanceRecord, AttendanceStatus
        from app import crud
        from app.services import calculate_attendance_summary
        return {
            "db": db,
            "Student": Student,
            "AttendanceRecord": AttendanceRecord,
            "AttendanceStatus": AttendanceStatus,
            "crud": crud,
            "calculate_attendance_summary": calculate_attendance_summary,
        }

    return app


def register_error_handlers(app):
    """Registers standard HTTP error handlers for both HTML and JSON clients."""

    @app.errorhandler(404)
    def handle_not_found(error):
        if request.path.startswith("/api/") or request.is_json:
            return jsonify({"status": "error", "message": "Resource not found", "code": 404}), 404
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def handle_internal_server_error(error):
        if request.path.startswith("/api/") or request.is_json:
            return jsonify({"status": "error", "message": "Internal server error", "code": 500}), 500
        return render_template("errors/500.html"), 500
