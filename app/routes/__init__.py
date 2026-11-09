"""
Routes package initialization.
Exposes modular Blueprints for clean application factory registration.
"""

from app.routes.attendance import attendance_bp
from app.routes.main import main_bp
from app.routes.students import students_bp

__all__ = ["main_bp", "students_bp", "attendance_bp"]
