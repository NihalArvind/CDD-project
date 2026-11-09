"""
AttendSync Database Models
--------------------------
Defines the core relational schema for Student entities and daily AttendanceRecords.
Implements one-to-many relationships, cascade deletion, and composite unique constraints.
"""

from datetime import date
from enum import Enum
from app.extensions import db


class AttendanceStatus(str, Enum):
    """
    Standard attendance status enumeration.
    Supports 'Present' and 'Absent'.
    """
    PRESENT = "Present"
    ABSENT = "Absent"


class Student(db.Model):
    """
    Represents an enrolled engineering student.

    Attributes:
        id (int): Primary key identifier.
        usn (str): University Seat Number, unique, indexed, non-nullable.
        name (str): Full student name.
        email (str): Student institution email address, unique and indexed.
        department (str): Academic department (e.g., Computer Science, Mechanical).
        semester (int): Current semester of study (1 through 8).
        section (str): Class section identifier (e.g., 'A', 'B', 'C').
        attendance_records (list): One-to-many relationship referencing AttendanceRecord.
    """
    __tablename__ = "students"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    usn = db.Column(db.String(20), unique=True, nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    department = db.Column(db.String(80), nullable=False)
    semester = db.Column(db.Integer, nullable=False)
    section = db.Column(db.String(10), nullable=False)

    # Relationship: 1 Student -> Many AttendanceRecords
    # cascade="all, delete-orphan": Deleting a student automatically removes all their attendance records
    attendance_records = db.relationship(
        "AttendanceRecord",
        backref="student",
        lazy="select",
        cascade="all, delete-orphan",
        order_by="desc(AttendanceRecord.date)"
    )

    def to_dict(self):
        """Serializes the Student instance into a standard dictionary format."""
        return {
            "id": self.id,
            "usn": self.usn,
            "name": self.name,
            "email": self.email,
            "department": self.department,
            "semester": self.semester,
            "section": self.section,
        }

    def __repr__(self):
        return f"<Student usn='{self.usn}' name='{self.name}' sem={self.semester} sec='{self.section}'>"


class AttendanceRecord(db.Model):
    """
    Represents a single daily attendance entry for a student.

    Attributes:
        id (int): Primary key identifier.
        student_id (int): Foreign key referencing students.id.
        date (date): Calendar date for which attendance is recorded.
        status (str): Attendance status ('Present' or 'Absent').

    Constraints:
        uq_student_date: Composite unique constraint on (student_id, date) ensuring
                         a student cannot have more than one attendance record on the same day.
    """
    __tablename__ = "attendance_records"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    student_id = db.Column(
        db.Integer,
        db.ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    date = db.Column(db.Date, nullable=False, default=date.today, index=True)
    status = db.Column(
        db.String(10),
        nullable=False,
        default=AttendanceStatus.PRESENT.value
    )

    # Database-level composite unique constraint
    __table_args__ = (
        db.UniqueConstraint("student_id", "date", name="uq_student_date"),
    )

    def to_dict(self):
        """Serializes the AttendanceRecord instance into a standard dictionary format."""
        return {
            "id": self.id,
            "student_id": self.student_id,
            "student_usn": self.student.usn if self.student else None,
            "student_name": self.student.name if self.student else None,
            "date": self.date.isoformat() if self.date else None,
            "status": self.status,
        }

    def __repr__(self):
        return f"<AttendanceRecord student_id={self.student_id} date={self.date} status='{self.status}'>"


__all__ = ["Student", "AttendanceRecord", "AttendanceStatus"]
