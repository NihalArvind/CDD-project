"""
AttendSync Offline Report Generation & Attendance Verification Test Suite
========================================================================
File: tests/test_attendance.py

Automated test suite using pytest and Flask's test client configured with
an isolated in-memory SQLite database (sqlite:///:memory:).

Verifies:
  a) Student creation succeeds and duplicate USN creation throws a 400 / IntegrityError.
  b) Marking attendance records updates database entries correctly (insert & upsert).
  c) Composite unique constraint prevents duplicate attendance records for the same student on the same date.
  d) Percentage calculation accurately computes values and handles 0 total classes without ZeroDivisionError.
  e) CSV export route (/reports/export) returns HTTP 200, valid headers, and streamed CSV content.
"""

import csv
from datetime import date, timedelta
import io
import re
import pytest
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import AttendanceRecord, AttendanceStatus, Student
from app.crud import create_student, record_attendance, get_student_attendance_summary
from app.services.attendance_service import calculate_attendance_summary


# ==============================================================================
# a) Student Creation & Duplicate USN Verification
# ==============================================================================

def test_student_creation_succeeds_orm(app):
    """
    Verify student creation succeeds at the database/ORM layer with all required attributes.
    """
    with app.app_context():
        student = create_student(
            usn="1MS21CS001",
            name="Alice Walker",
            email="alice.walker@college.edu",
            department="Computer Science & Engineering",
            semester=6,
            section="A"
        )
        assert student.id is not None
        assert student.usn == "1MS21CS001"
        assert student.name == "Alice Walker"
        assert student.email == "alice.walker@college.edu"
        assert student.department == "Computer Science & Engineering"
        assert student.semester == 6
        assert student.section == "A"

        # Verify query retrieval
        persisted = Student.query.filter_by(usn="1MS21CS001").first()
        assert persisted is not None
        assert persisted.id == student.id


def test_student_duplicate_usn_throws_integrity_error_orm(app):
    """
    Verify that attempting to create a student with a duplicate USN at the ORM layer
    triggers an IntegrityError due to the unique column constraint on Student.usn.
    """
    with app.app_context():
        # First creation succeeds
        create_student(
            usn="1MS21CS002",
            name="Bob Smith",
            email="bob.smith@college.edu",
            department="Information Science & Engineering",
            semester=6,
            section="B"
        )

        # Second creation with identical USN must raise IntegrityError
        with pytest.raises(IntegrityError):
            duplicate_student = Student(
                usn="1MS21CS002",
                name="Imposter Bob",
                email="imposter.bob@college.edu",
                department="Computer Science & Engineering",
                semester=6,
                section="A"
            )
            db.session.add(duplicate_student)
            db.session.commit()

        db.session.rollback()


def test_student_creation_succeeds_http(client, app):
    """
    Verify student registration succeeds via HTTP POST /students/add with JSON payload (HTTP 201).
    """
    payload = {
        "usn": "1MS21EC010",
        "name": "Catherine Green",
        "email": "catherine.ec@college.edu",
        "department": "Electronics & Communication Engineering",
        "semester": 4,
        "section": "A"
    }

    response = client.post("/students/add", json=payload)
    assert response.status_code == 201
    data = response.get_json()
    assert data["status"] == "success"
    assert data["data"]["usn"] == "1MS21EC010"
    assert data["data"]["name"] == "Catherine Green"

    # Confirm record is in in-memory database
    with app.app_context():
        student = Student.query.filter_by(usn="1MS21EC010").first()
        assert student is not None
        assert student.email == "catherine.ec@college.edu"


def test_student_duplicate_usn_throws_400_http(client, app):
    """
    Verify that registering a student with an already-existing USN returns HTTP 400 Bad Request
    via the Flask test client.
    """
    with app.app_context():
        create_student(
            usn="1MS21ME020",
            name="David Miller",
            email="david.me@college.edu",
            department="Mechanical Engineering",
            semester=6,
            section="A"
        )

    # Attempt to post duplicate USN via JSON
    dup_payload = {
        "usn": "1MS21ME020",
        "name": "David Duplicate",
        "email": "david.dup@college.edu",
        "department": "Mechanical Engineering",
        "semester": 6,
        "section": "A"
    }
    response_json = client.post("/students/add", json=dup_payload)
    assert response_json.status_code == 400
    json_data = response_json.get_json()
    assert json_data["status"] == "error"
    assert "already registered" in json_data["message"].lower()

    # Attempt to post duplicate USN via Form submission
    response_form = client.post("/students/add", data=dup_payload, follow_redirects=True)
    assert response_form.status_code == 200
    html_text = response_form.get_data(as_text=True)
    assert "already registered" in html_text.lower()


# ==============================================================================
# b) Marking Attendance Records Updates Database Entries Correctly
# ==============================================================================

def test_marking_attendance_creates_and_updates_database_records(app):
    """
    Verify marking attendance creates records and subsequent marks update existing
    records correctly without creating spurious rows.
    """
    with app.app_context():
        student = create_student(
            usn="1MS21CS030",
            name="Ethan Hunt",
            email="ethan.hunt@college.edu",
            department="CSE",
            semester=6,
            section="A"
        )
        test_date = date(2026, 11, 10)

        # 1. Initial marking as Present
        rec1 = record_attendance(usn=student.usn, record_date=test_date, status=AttendanceStatus.PRESENT)
        assert rec1.id is not None
        assert rec1.status == "Present"
        assert rec1.student_id == student.id

        # Verify database entry
        persisted = AttendanceRecord.query.filter_by(student_id=student.id, date=test_date).first()
        assert persisted is not None
        assert persisted.status == "Present"

        # 2. Update marking on the same date to Absent (upsert)
        rec2 = record_attendance(usn=student.usn, record_date=test_date, status=AttendanceStatus.ABSENT)
        assert rec2.id == rec1.id  # Same record ID updated in-place
        assert rec2.status == "Absent"

        # Verify database record updated and count is exactly 1
        records_count = AttendanceRecord.query.filter_by(student_id=student.id, date=test_date).count()
        assert records_count == 1
        updated = AttendanceRecord.query.filter_by(student_id=student.id, date=test_date).first()
        assert updated.status == "Absent"


def test_marking_attendance_bulk_endpoint_updates_database(client, app):
    """
    Verify bulk attendance marking via HTTP POST /attendance/mark updates entries in the database.
    """
    with app.app_context():
        s1 = create_student("1MS21CS031", "Student One", "s1@test.edu", "CSE", 6, "A")
        s2 = create_student("1MS21CS032", "Student Two", "s2@test.edu", "CSE", 6, "A")
        sid1, sid2 = s1.id, s2.id

    target_date = "2026-11-12"

    # Step 1: Initial submission (s1=Present, s2=Absent)
    payload_1 = {
        "date": target_date,
        "records": [
            {"student_id": sid1, "status": "Present"},
            {"student_id": sid2, "status": "Absent"}
        ]
    }
    res1 = client.post("/attendance/mark", json=payload_1)
    assert res1.status_code == 200
    res1_data = res1.get_json()
    assert res1_data["status"] == "success"
    assert res1_data["inserted"] == 2

    with app.app_context():
        d_obj = date(2026, 11, 12)
        r1 = AttendanceRecord.query.filter_by(student_id=sid1, date=d_obj).first()
        r2 = AttendanceRecord.query.filter_by(student_id=sid2, date=d_obj).first()
        assert r1.status == "Present"
        assert r2.status == "Absent"

    # Step 2: Update submission for same date (s1=Absent, s2=Present)
    payload_2 = {
        "date": target_date,
        "records": [
            {"student_id": sid1, "status": "Absent"},
            {"student_id": sid2, "status": "Present"}
        ]
    }
    res2 = client.post("/attendance/mark", json=payload_2)
    assert res2.status_code == 200
    res2_data = res2.get_json()
    assert res2_data["updated"] == 2

    with app.app_context():
        # Verify database entries updated correctly and no duplicate rows created
        total_for_day = AttendanceRecord.query.filter_by(date=d_obj).count()
        assert total_for_day == 2
        r1_updated = AttendanceRecord.query.filter_by(student_id=sid1, date=d_obj).first()
        r2_updated = AttendanceRecord.query.filter_by(student_id=sid2, date=d_obj).first()
        assert r1_updated.status == "Absent"
        assert r2_updated.status == "Present"


# ==============================================================================
# c) Composite Unique Constraint Prevents Duplicate Records on Same Date
# ==============================================================================

def test_composite_unique_constraint_student_date(app):
    """
    Verify the database-level composite unique constraint (uq_student_date)
    strictly prevents duplicate attendance records for the same student on the same date.
    """
    with app.app_context():
        student = create_student(
            usn="1MS21CS040",
            name="Constraint Test Student",
            email="constraint@college.edu",
            department="CSE",
            semester=6,
            section="A"
        )
        record_date = date(2026, 11, 14)

        # First insert succeeds
        rec1 = AttendanceRecord(student_id=student.id, date=record_date, status="Present")
        db.session.add(rec1)
        db.session.commit()

        # Second insert for identical (student_id, date) must trigger IntegrityError
        rec2 = AttendanceRecord(student_id=student.id, date=record_date, status="Absent")
        db.session.add(rec2)
        with pytest.raises(IntegrityError):
            db.session.commit()

        db.session.rollback()

        # Verify only the initial single record is in the database
        records = AttendanceRecord.query.filter_by(student_id=student.id, date=record_date).all()
        assert len(records) == 1
        assert records[0].status == "Present"


def test_attendance_records_allowed_on_distinct_dates(app):
    """
    Verify that attendance records for the same student on DIFFERENT calendar dates
    are stored successfully without violating the composite unique constraint.
    """
    with app.app_context():
        student = create_student("1MS21CS041", "Distinct Dates Student", "distinct@test.edu", "CSE", 6, "A")
        d1 = date(2026, 11, 1)
        d2 = date(2026, 11, 2)
        d3 = date(2026, 11, 3)

        rec1 = AttendanceRecord(student_id=student.id, date=d1, status="Present")
        rec2 = AttendanceRecord(student_id=student.id, date=d2, status="Absent")
        rec3 = AttendanceRecord(student_id=student.id, date=d3, status="Present")

        db.session.add_all([rec1, rec2, rec3])
        db.session.commit()

        records = AttendanceRecord.query.filter_by(student_id=student.id).all()
        assert len(records) == 3


# ==============================================================================
# d) Percentage Calculation Accuracy & Zero Classes Handling
# ==============================================================================

def test_percentage_calculation_zero_total_classes_without_crashing(app):
    """
    Verify the percentage calculation logic gracefully handles 0 total classes held
    without throwing a ZeroDivisionError and safely defaults to 0.0%.
    """
    with app.app_context():
        student = create_student(
            usn="1MS21CS050",
            name="Zero Classes Student",
            email="zero.classes@college.edu",
            department="CSE",
            semester=6,
            section="A"
        )

        # 1. Test single student metric calculation
        summary = calculate_attendance_summary(student_id=student.id)
        assert summary is not None
        assert summary["total_classes_held"] == 0
        assert summary["classes_attended"] == 0
        assert summary["classes_absent"] == 0
        assert summary["attendance_percentage"] == 0.0
        assert summary["percentage"] == 0.0
        assert isinstance(summary["is_shortage"], bool)

        # 2. Test class-wide summary calculation when no classes have occurred
        all_summaries = calculate_attendance_summary(student_id=None)
        assert len(all_summaries) >= 1
        st_summary = next(s for s in all_summaries if s["usn"] == "1MS21CS050")
        assert st_summary["total_classes_held"] == 0
        assert st_summary["attendance_percentage"] == 0.0

        # 3. Test CRUD summary helper fallback
        crud_summary = get_student_attendance_summary("1MS21CS050")
        assert crud_summary["total_classes"] == 0
        assert crud_summary["attendance_percentage"] == 0.0


def test_percentage_calculation_accurately_computes_values(app):
    """
    Verify percentage calculation logic accurately computes values across different attendance rates:
    - 100.0% attendance (Eligible, is_shortage=False)
    - 75.0% boundary attendance (Eligible, is_shortage=False)
    - 50.0% attendance (Shortage, is_shortage=True)
    - 0.0% attendance with classes held (Shortage, is_shortage=True)
    """
    with app.app_context():
        # Setup 4 distinct class dates
        d1 = date(2026, 11, 1)
        d2 = date(2026, 11, 2)
        d3 = date(2026, 11, 3)
        d4 = date(2026, 11, 4)

        # Student 1: 4/4 Present (100.0%)
        s1 = create_student("1MS21CS051", "Student Full", "s100@test.edu", "CSE", 6, "A")
        # Student 2: 3/4 Present (75.0% - institutional threshold)
        s2 = create_student("1MS21CS052", "Student Threshold", "s75@test.edu", "CSE", 6, "A")
        # Student 3: 2/4 Present (50.0% - shortage)
        s3 = create_student("1MS21CS053", "Student Low", "s50@test.edu", "CSE", 6, "A")
        # Student 4: 0/4 Present (0.0% - shortage)
        s4 = create_student("1MS21CS054", "Student None", "s0@test.edu", "CSE", 6, "A")

        db.session.add_all([
            # Student 1: 4 Present
            AttendanceRecord(student_id=s1.id, date=d1, status="Present"),
            AttendanceRecord(student_id=s1.id, date=d2, status="Present"),
            AttendanceRecord(student_id=s1.id, date=d3, status="Present"),
            AttendanceRecord(student_id=s1.id, date=d4, status="Present"),
            # Student 2: 3 Present, 1 Absent
            AttendanceRecord(student_id=s2.id, date=d1, status="Present"),
            AttendanceRecord(student_id=s2.id, date=d2, status="Present"),
            AttendanceRecord(student_id=s2.id, date=d3, status="Present"),
            AttendanceRecord(student_id=s2.id, date=d4, status="Absent"),
            # Student 3: 2 Present, 2 Absent
            AttendanceRecord(student_id=s3.id, date=d1, status="Present"),
            AttendanceRecord(student_id=s3.id, date=d2, status="Absent"),
            AttendanceRecord(student_id=s3.id, date=d3, status="Present"),
            AttendanceRecord(student_id=s3.id, date=d4, status="Absent"),
            # Student 4: 0 Present, 4 Absent
            AttendanceRecord(student_id=s4.id, date=d1, status="Absent"),
            AttendanceRecord(student_id=s4.id, date=d2, status="Absent"),
            AttendanceRecord(student_id=s4.id, date=d3, status="Absent"),
            AttendanceRecord(student_id=s4.id, date=d4, status="Absent"),
        ])
        db.session.commit()

        # Evaluate Student 1 (100.0%)
        m1 = calculate_attendance_summary(s1.id)
        assert m1["total_classes_held"] == 4
        assert m1["classes_attended"] == 4
        assert m1["attendance_percentage"] == 100.0
        assert m1["is_shortage"] is False

        # Evaluate Student 2 (75.0% - boundary case, not shortage)
        m2 = calculate_attendance_summary(s2.id)
        assert m2["total_classes_held"] == 4
        assert m2["classes_attended"] == 3
        assert m2["attendance_percentage"] == 75.0
        assert m2["is_shortage"] is False

        # Evaluate Student 3 (50.0% - shortage)
        m3 = calculate_attendance_summary(s3.id)
        assert m3["total_classes_held"] == 4
        assert m3["classes_attended"] == 2
        assert m3["attendance_percentage"] == 50.0
        assert m3["is_shortage"] is True

        # Evaluate Student 4 (0.0% - shortage)
        m4 = calculate_attendance_summary(s4.id)
        assert m4["total_classes_held"] == 4
        assert m4["classes_attended"] == 0
        assert m4["attendance_percentage"] == 0.0
        assert m4["is_shortage"] is True


# ==============================================================================
# e) CSV Export Route (/reports/export) Verification
# ==============================================================================

def test_csv_export_returns_200_and_headers(client, app):
    """
    Verify GET /reports/export returns HTTP 200, Content-Type: text/csv, and
    Content-Disposition: attachment; filename=attendance_report_<date>.csv.
    """
    with app.app_context():
        create_student("1MS21CS060", "CSV Header Test", "csvhead@college.edu", "CSE", 6, "A")

    response = client.get("/reports/export")
    assert response.status_code == 200

    # 1. Content-Type check
    content_type = response.headers.get("Content-Type", "")
    assert "text/csv" in content_type

    # 2. Content-Disposition check
    disposition = response.headers.get("Content-Disposition", "")
    assert "attachment" in disposition
    assert "filename=" in disposition
    assert "attendance_report_" in disposition
    assert disposition.endswith(".csv") or ".csv" in disposition

    # Verify <date> pattern in filename (e.g. YYYY-MM-DD or YYYYMMDD)
    filename_match = re.search(r"filename=[\"']?attendance_report_([^\"';]+)\.csv", disposition)
    assert filename_match is not None, f"Filename header malformed: {disposition}"


def test_csv_export_content_structure_and_values(client, app):
    """
    Verify CSV export streams valid CSV content, contains required headers:
    'USN, Name, Total Classes, Attended Classes, Percentage, Status (Eligible / Shortage)'
    and correctly formats student data rows with Eligible/Shortage statuses.
    """
    with app.app_context():
        # Setup test data with 2 students
        s_eligible = create_student("1MS21CS070", "Eligible Student", "elig@college.edu", "CSE", 6, "A")
        s_shortage = create_student("1MS21CS071", "Shortage Student", "short@college.edu", "CSE", 6, "A")

        d1 = date(2026, 11, 1)
        d2 = date(2026, 11, 2)
        d3 = date(2026, 11, 3)
        d4 = date(2026, 11, 4)

        # Eligible student: 3/4 (75.0%)
        # Shortage student: 1/4 (25.0%)
        db.session.add_all([
            AttendanceRecord(student_id=s_eligible.id, date=d1, status="Present"),
            AttendanceRecord(student_id=s_eligible.id, date=d2, status="Present"),
            AttendanceRecord(student_id=s_eligible.id, date=d3, status="Present"),
            AttendanceRecord(student_id=s_eligible.id, date=d4, status="Absent"),

            AttendanceRecord(student_id=s_shortage.id, date=d1, status="Present"),
            AttendanceRecord(student_id=s_shortage.id, date=d2, status="Absent"),
            AttendanceRecord(student_id=s_shortage.id, date=d3, status="Absent"),
            AttendanceRecord(student_id=s_shortage.id, date=d4, status="Absent"),
        ])
        db.session.commit()

    response = client.get("/reports/export")
    assert response.status_code == 200

    csv_text = response.get_data(as_text=True)
    assert len(csv_text.strip()) > 0

    # Parse CSV using Python's built-in csv module
    reader = list(csv.reader(io.StringIO(csv_text)))
    assert len(reader) >= 3  # Header + 2 student rows

    # Verify Header row:
    header = reader[0]
    expected_header = [
        "USN",
        "Name",
        "Total Classes",
        "Attended Classes",
        "Percentage",
        "Status (Eligible / Shortage)"
    ]
    assert header == expected_header

    # Parse with DictReader to verify column associations and data accuracy
    dict_reader = list(csv.DictReader(io.StringIO(csv_text)))
    row_map = {row["USN"]: row for row in dict_reader}

    assert "1MS21CS070" in row_map
    assert "1MS21CS071" in row_map

    # Validate Eligible Student row
    row_elig = row_map["1MS21CS070"]
    assert row_elig["Name"] == "Eligible Student"
    assert int(row_elig["Total Classes"]) == 4
    assert int(row_elig["Attended Classes"]) == 3
    assert "75" in row_elig["Percentage"]
    assert row_elig["Status (Eligible / Shortage)"] == "Eligible"

    # Validate Shortage Student row
    row_short = row_map["1MS21CS071"]
    assert row_short["Name"] == "Shortage Student"
    assert int(row_short["Total Classes"]) == 4
    assert int(row_short["Attended Classes"]) == 1
    assert "25" in row_short["Percentage"]
    assert row_short["Status (Eligible / Shortage)"] == "Shortage"


def test_csv_export_with_zero_classes_held(client, app):
    """
    Verify CSV export works without crashing when no attendance records exist (0 classes conducted).
    """
    with app.app_context():
        create_student("1MS21CS080", "Empty Ledger Student", "empty@college.edu", "CSE", 6, "A")

    response = client.get("/reports/export")
    assert response.status_code == 200

    csv_text = response.get_data(as_text=True)
    reader = list(csv.DictReader(io.StringIO(csv_text)))
    assert len(reader) == 1

    row = reader[0]
    assert row["USN"] == "1MS21CS080"
    assert row["Name"] == "Empty Ledger Student"
    assert int(row["Total Classes"]) == 0
    assert int(row["Attended Classes"]) == 0
    assert "0" in row["Percentage"]
    assert row["Status (Eligible / Shortage)"] == "Shortage"
