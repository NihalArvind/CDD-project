"""
Services package initialization.
Exposes domain service functions for attendance and metrics calculations.
"""

from app.services.attendance_service import calculate_attendance_summary

__all__ = ["calculate_attendance_summary"]
