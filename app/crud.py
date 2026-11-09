"""
AttendSync CRUD Helper Utilities
--------------------------------
Provides reusable, modular query functions and business operations for:
- Student directory management
- Daily attendance queries
- Historical attendance tracking
"""

from datetime import date, datetime
from typing import List, Optional, Tuple, Union

from sqlalchemy.exc import IntegrityError
from app.extensions import db
from app.models import AttendanceRecord, AttendanceStatus, Student


def get_all_students_sorted() -> List[Student]:
    """
    Fetches all enrolled students ordered alphabetically by their USN.

    Returns:
        List[Student]: A list of Student model instances sorted by USN in ascending order.
    """
    return Student.query.order_by(Student.usn.asc()).all()


def get_student_by_usn(usn: str) -> Optional[Student]:
    """
    Retrieves a single student by their University Seat Number (case-insensitive).

    Args:
        usn (str): The student's unique USN.

    Returns:
        Optional[Student]: The Student instance if found, otherwise None.
    """
    if not usn:
        return None
    return Student.query.filter(Student.usn.ilike(usn.strip())).first()


def parse_date(date_val: Union[date, datetime, str]) -> date:
    """
    Normalizes a date input (date, datetime, or ISO string) to a standard datetime.date object.

    Args:
        date_val: Date object, datetime object, or 'YYYY-MM-DD' formatted string.

    Returns:
        date: Normalized calendar date object.

    Raises:
        ValueError: If a string input does not match expected ISO date format.
    """
    if isinstance(date_val, datetime):
        return date_val.date()
    if isinstance(date_val, date):
        return date_val
    if isinstance(date_val, str):
        return datetime.strptime(date_val.strip(), "%Y-%m-%d").date()
    raise ValueError(f"Unsupported date format: {type(date_val)}")


def get_attendance_by_date(target_date: Union[date, datetime, str]) -> List[AttendanceRecord]:
    """
    Fetches all student attendance records for a specific calendar date.

    Args:
        target_date: Calendar date (as datetime.date, datetime, or 'YYYY-MM-DD' string).

    Returns:
        List[AttendanceRecord]: List of attendance records for the given date,
                               joined with Student details and sorted by student USN.
    """
    query_date = parse_date(target_date)
    return (
        AttendanceRecord.query
        .filter(AttendanceRecord.date == query_date)
        .join(Student)
        .order_by(Student.usn.asc())
        .all()
    )


def get_student_attendance_history(usn: str) -> Tuple[Optional[Student], List[AttendanceRecord]]:
    """
    Fetches the complete historical attendance records for a single student by USN.

    Args:
        usn (str): University Seat Number of the student.

    Returns:
        Tuple[Optional[Student], List[AttendanceRecord]]:
            - The Student instance (or None if student does not exist)
            - A list of AttendanceRecord instances ordered chronologically (newest first).
    """
    student = get_student_by_usn(usn)
    if not student:
        return None, []

    records = (
        AttendanceRecord.query
        .filter(AttendanceRecord.student_id == student.id)
        .order_by(AttendanceRecord.date.desc())
        .all()
    )
    return student, records


def record_attendance(
    usn: str,
    record_date: Union[date, datetime, str],
    status: Union[AttendanceStatus, str] = AttendanceStatus.PRESENT
) -> AttendanceRecord:
    """
    Records or updates attendance for a student on a specific date.
    Respects the composite unique constraint (student_id, date) by updating
    an existing record if one is already present for that day.

    Args:
        usn (str): Student USN.
        record_date: Target date.
        status: Attendance status ('Present' or 'Absent').

    Returns:
        AttendanceRecord: The persisted or updated AttendanceRecord.

    Raises:
        ValueError: If student with given USN is not found or invalid status provided.
    """
    student = get_student_by_usn(usn)
    if not student:
        raise ValueError(f"Student with USN '{usn}' not found.")

    target_date = parse_date(record_date)
    status_str = status.value if isinstance(status, AttendanceStatus) else str(status).capitalize()
    if status_str not in {AttendanceStatus.PRESENT.value, AttendanceStatus.ABSENT.value}:
        raise ValueError(f"Invalid attendance status: '{status}'. Must be 'Present' or 'Absent'.")

    # Check if a record already exists for (student_id, date)
    existing_record = AttendanceRecord.query.filter_by(
        student_id=student.id,
        date=target_date
    ).first()

    if existing_record:
        existing_record.status = status_str
        db.session.commit()
        return existing_record

    new_record = AttendanceRecord(
        student_id=student.id,
        date=target_date,
        status=status_str
    )
    db.session.add(new_record)
    db.session.commit()
    return new_record


def create_student(
    usn: str,
    name: str,
    email: str,
    department: str,
    semester: int,
    section: str
) -> Student:
    """
    Registers a new student into the system.

    Args:
        usn (str): University Seat Number.
        name (str): Full student name.
        email (str): Student email.
        department (str): Engineering department.
        semester (int): Semester (1-8).
        section (str): Section ('A', 'B', etc.).

    Returns:
        Student: The created student record.

    Raises:
        IntegrityError: If USN or email is already registered.
    """
    student = Student(
        usn=usn.strip().upper(),
        name=name.strip(),
        email=email.strip().lower(),
        department=department.strip(),
        semester=int(semester),
        section=section.strip().upper(),
    )
    db.session.add(student)
    db.session.commit()
    return student


def get_student_attendance_summary(usn: str) -> Optional[dict]:
    """
    Calculates attendance percentage and metrics for a student.

    Args:
        usn (str): Student USN.

    Returns:
        Optional[dict]: Summary dictionary containing total_classes, present_count,
                       absent_count, and attendance_percentage.
    """
    student, records = get_student_attendance_history(usn)
    if not student:
        return None

    total_classes = len(records)
    present_count = sum(1 for r in records if r.status == AttendanceStatus.PRESENT.value)
    absent_count = total_classes - present_count
    percentage = round((present_count / total_classes * 100), 2) if total_classes > 0 else 0.0

    return {
        "student": student.to_dict(),
        "total_classes": total_classes,
        "present_count": present_count,
        "absent_count": absent_count,
        "attendance_percentage": percentage,
    }


# Service helper re-export for Phase 3 metrics calculation
from app.services.attendance_service import calculate_attendance_summary
