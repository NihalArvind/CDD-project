"""
AttendSync Attendance & Metrics Service Layer
---------------------------------------------
Implements domain business logic for calculating class attendance metrics,
tracking attendance percentages, and detecting student attendance shortages.
"""

from typing import Any, Dict, List, Optional, Union
from app.extensions import db
from app.models import AttendanceRecord, AttendanceStatus, Student


def calculate_attendance_summary(student_id: Optional[int] = None) -> Union[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Calculates detailed attendance metrics and shortage indicators.

    Metrics calculated per student:
    - Total classes held (distinct calendar dates recorded in AttendanceRecord).
    - Total classes attended (records with status 'Present').
    - Total classes absent (records with status 'Absent' or difference).
    - Attendance percentage: (Classes Present / Total Classes Held) * 100.
    - Shortage indicator flag: boolean `is_shortage` True if percentage < 75.0%.
    - Graceful fallback when total classes held is 0 (returns 0.0% instead of ZeroDivisionError).

    Args:
        student_id (Optional[int]): Target student primary key ID. If None,
                                    computes metrics for all registered students.

    Returns:
        Union[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
            - If student_id is provided: Dictionary of metrics for that student,
              or None if the student does not exist.
            - If student_id is None: List of summary dictionaries for all students,
              ordered alphabetically by USN.
    """
    # 1. Total classes held across the system (distinct calendar dates recorded)
    total_classes_held: int = (
        db.session.query(db.func.count(db.distinct(AttendanceRecord.date))).scalar() or 0
    )

    def _build_summary_for_student(student: Student) -> Dict[str, Any]:
        """Helper to compute metrics for a single Student instance."""
        # Classes attended (status == 'Present')
        attended_count: int = (
            AttendanceRecord.query.filter_by(
                student_id=student.id,
                status=AttendanceStatus.PRESENT.value
            ).count()
        )

        # Classes absent (status == 'Absent')
        absent_count: int = (
            AttendanceRecord.query.filter_by(
                student_id=student.id,
                status=AttendanceStatus.ABSENT.value
            ).count()
        )

        # Attendance percentage calculation with ZeroDivisionError fallback
        if total_classes_held > 0:
            percentage: float = round((attended_count / total_classes_held) * 100, 2)
        else:
            percentage = 0.0

        # Shortage indicator flag: True if percentage < 75%
        is_shortage: bool = percentage < 75.0

        return {
            "student_id": student.id,
            "id": student.id,
            "student": student.to_dict(),
            "usn": student.usn,
            "name": student.name,
            "email": student.email,
            "department": student.department,
            "semester": student.semester,
            "section": student.section,
            # Total classes metrics
            "total_classes": total_classes_held,
            "total_classes_held": total_classes_held,
            "classes_held": total_classes_held,
            # Attended & absent metrics
            "classes_attended": attended_count,
            "total_classes_attended": attended_count,
            "present_count": attended_count,
            "classes_absent": absent_count,
            "absent_count": absent_count,
            # Percentage & shortage
            "attendance_percentage": percentage,
            "percentage": percentage,
            "is_shortage": is_shortage,
        }

    # Case A: Single student requested
    if student_id is not None:
        try:
            sid = int(student_id)
        except (ValueError, TypeError):
            return None

        student = db.session.get(Student, sid) if hasattr(db.session, "get") else Student.query.get(sid)
        if not student:
            return None
        return _build_summary_for_student(student)

    # Case B: All students requested (student_id is None)
    all_students = Student.query.order_by(Student.usn.asc()).all()
    return [_build_summary_for_student(s) for s in all_students]
