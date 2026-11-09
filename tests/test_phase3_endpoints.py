"""
Phase 3 Route Handlers & Business Logic Automated Test Suite
------------------------------------------------------------
Validates:
1. Student Management Endpoints (GET /students, POST /students/add, POST /students/<id>/delete)
2. Daily Attendance Endpoints (GET /attendance/mark, POST /attendance/mark, bulk upsert, atomic transactions)
3. Metrics & Reporting Service (calculate_attendance_summary, distinct dates, shortage flag, zero-division fallback)
4. Reports Endpoint (GET /reports, sorting capabilities by lowest attendance first, USN, name, shortage)
"""

from datetime import date, timedelta
import pytest
from app.extensions import db
from app.models import AttendanceRecord, AttendanceStatus, Student
from app.services.attendance_service import calculate_attendance_summary


# ==============================================================================
# 1. Student Management Endpoints Tests
# ==============================================================================

def test_get_students_html(client, app):
    """Verify GET /students renders HTML with all registered students."""
    with app.app_context():
        s1 = Student(usn="1MS21CS001", name="Alice", email="alice@test.edu", department="CSE", semester=6, section="A")
        s2 = Student(usn="1MS21CS002", name="Bob", email="bob@test.edu", department="CSE", semester=6, section="B")
        db.session.add_all([s1, s2])
        db.session.commit()

    response = client.get("/students")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Student Management" in html
    assert "1MS21CS001" in html
    assert "Alice" in html
    assert "1MS21CS002" in html
    assert "Bob" in html


def test_get_students_json(client, app):
    """Verify GET /students returns JSON list of students when requested."""
    with app.app_context():
        s = Student(usn="1MS21CS010", name="Charlie", email="charlie@test.edu", department="ISE", semester=4, section="A")
        db.session.add(s)
        db.session.commit()

    response = client.get("/students", headers={"Accept": "application/json"})
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "success"
    assert data["count"] == 1
    assert data["students"][0]["usn"] == "1MS21CS010"
    assert data["students"][0]["name"] == "Charlie"


def test_post_students_add_success_form(client, app):
    """Verify POST /students/add accepts form data and successfully creates a new student."""
    form_data = {
        "usn": "1ms21ec040",  # lowercase, should be normalized to uppercase
        "name": "Devika Pillai",
        "email": "devika.ec@college.edu",
        "department": "Electronics & Communication Engineering",
        "semester": "4",
        "section": "b"
    }

    response = client.post("/students/add", data=form_data, follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "successfully registered" in html
    assert "1MS21EC040" in html
    assert "Devika Pillai" in html

    with app.app_context():
        student = Student.query.filter_by(usn="1MS21EC040").first()
        assert student is not None
        assert student.name == "Devika Pillai"
        assert student.semester == 4
        assert student.section == "B"


def test_post_students_add_success_json(client, app):
    """Verify POST /students/add accepts JSON and returns HTTP 201."""
    json_data = {
        "usn": "1MS21ME050",
        "name": "Manoj Kumar",
        "email": "manoj.me@college.edu",
        "department": "Mechanical Engineering",
        "semester": 6,
        "section": "A"
    }

    response = client.post("/students/add", json=json_data)
    assert response.status_code == 201
    res_data = response.get_json()
    assert res_data["status"] == "success"
    assert res_data["data"]["usn"] == "1MS21ME050"


def test_post_students_add_usn_uniqueness_validation(client, app):
    """Verify USN uniqueness validation rejects duplicate USN and flashes error."""
    with app.app_context():
        existing = Student(usn="1MS21CS001", name="Existing User", email="exist@test.edu", department="CSE", semester=6, section="A")
        db.session.add(existing)
        db.session.commit()

    # Attempt to add student with identical USN
    dup_data = {
        "usn": "1MS21CS001",
        "name": "New Imposter",
        "email": "imposter@test.edu",
        "department": "CSE",
        "semester": "6",
        "section": "A"
    }
    response = client.post("/students/add", data=dup_data, follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "already registered" in html.lower()

    # Verify JSON client receives 400 error
    json_resp = client.post("/students/add", json=dup_data)
    assert json_resp.status_code == 400
    assert "already registered" in json_resp.get_json()["message"]


def test_post_students_add_email_uniqueness_validation(client, app):
    """Verify duplicate email is rejected gracefully."""
    with app.app_context():
        existing = Student(usn="1MS21CS001", name="User One", email="shared@college.edu", department="CSE", semester=6, section="A")
        db.session.add(existing)
        db.session.commit()

    dup_email_data = {
        "usn": "1MS21CS002",
        "name": "User Two",
        "email": "shared@college.edu",
        "department": "CSE",
        "semester": "6",
        "section": "A"
    }
    response = client.post("/students/add", data=dup_email_data, follow_redirects=True)
    assert response.status_code == 200
    assert "already in use" in response.get_data(as_text=True).lower()


def test_post_students_add_field_validations(client, app):
    """Verify validation errors for missing fields and invalid semester numbers."""
    # Missing USN
    res1 = client.post("/students/add", data={"name": "No USN", "email": "a@b.com", "department": "CSE", "semester": "6", "section": "A"}, follow_redirects=True)
    assert "Missing required fields: USN" in res1.get_data(as_text=True)

    # Invalid semester > 8
    res2 = client.post("/students/add", data={"usn": "1MS21CS999", "name": "Bad Sem", "email": "bad@b.com", "department": "CSE", "semester": "9", "section": "A"}, follow_redirects=True)
    assert "Must be an integer between 1 and 8" in res2.get_data(as_text=True)

    # Invalid semester non-numeric
    res3 = client.post("/students/add", data={"usn": "1MS21CS999", "name": "Bad Sem", "email": "bad@b.com", "department": "CSE", "semester": "xyz", "section": "A"}, follow_redirects=True)
    assert "Must be an integer between 1 and 8" in res3.get_data(as_text=True)


def test_post_students_delete_success(client, app):
    """Verify deleting a student removes student and cascades to their attendance records."""
    today = date.today()
    with app.app_context():
        student = Student(usn="1MS21CS777", name="Delete Me", email="delete@test.edu", department="CSE", semester=6, section="A")
        db.session.add(student)
        db.session.commit()
        sid = student.id

        # Add attendance records
        rec1 = AttendanceRecord(student_id=sid, date=today, status="Present")
        rec2 = AttendanceRecord(student_id=sid, date=today - timedelta(days=1), status="Absent")
        db.session.add_all([rec1, rec2])
        db.session.commit()

        assert AttendanceRecord.query.filter_by(student_id=sid).count() == 2

    # Perform POST delete
    response = client.post(f"/students/{sid}/delete", follow_redirects=True)
    assert response.status_code == 200
    assert "successfully deleted" in response.get_data(as_text=True).lower()

    with app.app_context():
        # Verify student is gone
        assert db.session.get(Student, sid) is None
        # Verify attendance records cascaded
        assert AttendanceRecord.query.filter_by(student_id=sid).count() == 0


def test_post_students_delete_not_found(client, app):
    """Verify attempting to delete non-existent student returns 404 / flashes error."""
    response = client.post("/students/99999/delete", follow_redirects=True)
    assert response.status_code == 200
    assert "was not found" in response.get_data(as_text=True).lower()

    json_resp = client.post("/students/99999/delete", headers={"Accept": "application/json"})
    assert json_resp.status_code == 404


# ==============================================================================
# 2. Daily Attendance Endpoints Tests
# ==============================================================================

def test_get_attendance_mark_defaults_to_today(client, app):
    """Verify GET /attendance/mark defaults to today's date when no date parameter is passed."""
    today_iso = date.today().isoformat()
    response = client.get("/attendance/mark")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert f'value="{today_iso}"' in html


def test_get_attendance_mark_prefills_existing_records(client, app):
    """Verify GET /attendance/mark pre-fills existing marks for previously recorded date."""
    target_date = date(2026, 11, 5)
    with app.app_context():
        s1 = Student(usn="1MS21CS001", name="Alice", email="alice@test.edu", department="CSE", semester=6, section="A")
        s2 = Student(usn="1MS21CS002", name="Bob", email="bob@test.edu", department="CSE", semester=6, section="A")
        db.session.add_all([s1, s2])
        db.session.commit()

        # Mark s1 Present, s2 Absent
        db.session.add_all([
            AttendanceRecord(student_id=s1.id, date=target_date, status="Present"),
            AttendanceRecord(student_id=s2.id, date=target_date, status="Absent"),
        ])
        db.session.commit()

    # Query the date
    response = client.get(f"/attendance/mark?date={target_date.isoformat()}")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Records Already Submitted" in html
    assert "value=\"Present\" checked" in html
    assert "value=\"Absent\" checked" in html

    # Query via JSON API
    json_resp = client.get(f"/attendance/mark?date={target_date.isoformat()}", headers={"Accept": "application/json"})
    assert json_resp.status_code == 200
    data = json_resp.get_json()
    assert data["has_existing_records"] is True
    assert data["marked_records_count"] == 2


def test_post_attendance_mark_bulk_submission_and_upsert(client, app):
    """
    Verify POST /attendance/mark performs bulk insertion, handles updates (upsert)
    without raising IntegrityError, and maintains atomic state.
    """
    target_date = date(2026, 11, 6)
    with app.app_context():
        s1 = Student(usn="1MS21CS001", name="Student 1", email="s1@t.com", department="CSE", semester=6, section="A")
        s2 = Student(usn="1MS21CS002", name="Student 2", email="s2@t.com", department="CSE", semester=6, section="A")
        s3 = Student(usn="1MS21CS003", name="Student 3", email="s3@t.com", department="CSE", semester=6, section="A")
        db.session.add_all([s1, s2, s3])
        db.session.commit()
        id1, id2, id3 = s1.id, s2.id, s3.id

    # 1. Initial bulk submission via Form data
    form_data = {
        "date": target_date.isoformat(),
        f"status_{id1}": "Present",
        f"status_{id2}": "Absent",
        f"status_{id3}": "Present",
    }
    resp1 = client.post("/attendance/mark", data=form_data, follow_redirects=True)
    assert resp1.status_code == 200
    assert "successfully saved" in resp1.get_data(as_text=True)

    with app.app_context():
        records = AttendanceRecord.query.filter_by(date=target_date).all()
        assert len(records) == 3
        status_map = {r.student_id: r.status for r in records}
        assert status_map[id1] == "Present"
        assert status_map[id2] == "Absent"
        assert status_map[id3] == "Present"

    # 2. Update submission for same date (Upsert check): Change Student 2 from Absent to Present
    update_data = {
        "date": target_date.isoformat(),
        f"status_{id1}": "Present",
        f"status_{id2}": "Present",  # Updated!
        f"status_{id3}": "Absent",   # Updated!
    }
    resp2 = client.post("/attendance/mark", data=update_data, follow_redirects=True)
    assert resp2.status_code == 200

    with app.app_context():
        # Ensure count is still exactly 3 (no duplicate rows created for same day)
        records_after = AttendanceRecord.query.filter_by(date=target_date).all()
        assert len(records_after) == 3
        status_map_after = {r.student_id: r.status for r in records_after}
        assert status_map_after[id2] == "Present"
        assert status_map_after[id3] == "Absent"


def test_post_attendance_mark_json_submission(client, app):
    """Verify bulk attendance submission using JSON API."""
    target_date = "2026-11-07"
    with app.app_context():
        s = Student(usn="1MS21CS099", name="JSON Tester", email="json@t.com", department="CSE", semester=6, section="A")
        db.session.add(s)
        db.session.commit()
        sid = s.id

    json_payload = {
        "date": target_date,
        "records": [
            {"student_id": sid, "status": "Present"}
        ]
    }
    response = client.post("/attendance/mark", json=json_payload)
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "success"
    assert data["inserted"] == 1


# ==============================================================================
# 3. Metrics & Reporting Logic Tests
# ==============================================================================

def test_calculate_attendance_summary_single_student(app):
    """Verify calculate_attendance_summary(student_id) computes correct metrics and shortage flag."""
    with app.app_context():
        student = Student(usn="1MS21CS100", name="Metrics Student", email="metrics@t.com", department="CSE", semester=6, section="A")
        db.session.add(student)
        db.session.commit()
        sid = student.id

        d1 = date(2026, 11, 1)
        d2 = date(2026, 11, 2)
        d3 = date(2026, 11, 3)
        d4 = date(2026, 11, 4)

        # 4 distinct class dates: Present for 3, Absent for 1 -> 75.0% attendance
        db.session.add_all([
            AttendanceRecord(student_id=sid, date=d1, status="Present"),
            AttendanceRecord(student_id=sid, date=d2, status="Present"),
            AttendanceRecord(student_id=sid, date=d3, status="Present"),
            AttendanceRecord(student_id=sid, date=d4, status="Absent"),
        ])
        db.session.commit()

        summary = calculate_attendance_summary(sid)
        assert summary is not None
        assert summary["total_classes_held"] == 4
        assert summary["classes_attended"] == 3
        assert summary["classes_absent"] == 1
        assert summary["attendance_percentage"] == 75.0
        assert summary["is_shortage"] is False  # 75.0% is not strictly < 75%

        # Add a 5th class date where student was Absent -> 3 / 5 = 60.0% -> Shortage!
        d5 = date(2026, 11, 5)
        db.session.add(AttendanceRecord(student_id=sid, date=d5, status="Absent"))
        db.session.commit()

        summary2 = calculate_attendance_summary(sid)
        assert summary2["total_classes_held"] == 5
        assert summary2["classes_attended"] == 3
        assert summary2["classes_absent"] == 2
        assert summary2["attendance_percentage"] == 60.0
        assert summary2["is_shortage"] is True  # 60.0% < 75.0%


def test_calculate_attendance_summary_zero_classes_held_fallback(app):
    """Verify graceful fallback returning 0.0% instead of ZeroDivisionError when no classes held."""
    with app.app_context():
        student = Student(usn="1MS21CS200", name="Zero Class Student", email="zero@t.com", department="CSE", semester=6, section="A")
        db.session.add(student)
        db.session.commit()

        summary = calculate_attendance_summary(student.id)
        assert summary is not None
        assert summary["total_classes_held"] == 0
        assert summary["classes_attended"] == 0
        assert summary["attendance_percentage"] == 0.0
        assert isinstance(summary["is_shortage"], bool)


def test_calculate_attendance_summary_all_students(app):
    """Verify calculate_attendance_summary(student_id=None) returns metrics for all students."""
    with app.app_context():
        s1 = Student(usn="1MS21CS001", name="Alpha", email="a@t.com", department="CSE", semester=6, section="A")
        s2 = Student(usn="1MS21CS002", name="Beta", email="b@t.com", department="CSE", semester=6, section="A")
        db.session.add_all([s1, s2])
        db.session.commit()

        day = date(2026, 11, 1)
        db.session.add_all([
            AttendanceRecord(student_id=s1.id, date=day, status="Present"),
            AttendanceRecord(student_id=s2.id, date=day, status="Absent"),
        ])
        db.session.commit()

        all_summaries = calculate_attendance_summary(student_id=None)
        assert len(all_summaries) == 2
        assert all_summaries[0]["usn"] == "1MS21CS001"
        assert all_summaries[0]["attendance_percentage"] == 100.0
        assert all_summaries[0]["is_shortage"] is False

        assert all_summaries[1]["usn"] == "1MS21CS002"
        assert all_summaries[1]["attendance_percentage"] == 0.0
        assert all_summaries[1]["is_shortage"] is True


# ==============================================================================
# 4. Reports Endpoint & Sorting Tests
# ==============================================================================

def test_get_reports_html_and_sorting(client, app):
    """Verify GET /reports returns class metrics and correctly sorts by lowest attendance first."""
    with app.app_context():
        # Create 3 students
        s_low = Student(usn="1MS21CS001", name="Low Attendance", email="low@t.com", department="CSE", semester=6, section="A")
        s_mid = Student(usn="1MS21CS002", name="Mid Attendance", email="mid@t.com", department="CSE", semester=6, section="A")
        s_high = Student(usn="1MS21CS003", name="High Attendance", email="high@t.com", department="CSE", semester=6, section="A")
        db.session.add_all([s_low, s_mid, s_high])
        db.session.commit()

        d1 = date(2026, 11, 1)
        d2 = date(2026, 11, 2)
        d3 = date(2026, 11, 3)

        # s_low: 0/3 (0%)
        # s_mid: 2/3 (66.67%)
        # s_high: 3/3 (100%)
        db.session.add_all([
            AttendanceRecord(student_id=s_low.id, date=d1, status="Absent"),
            AttendanceRecord(student_id=s_low.id, date=d2, status="Absent"),
            AttendanceRecord(student_id=s_low.id, date=d3, status="Absent"),

            AttendanceRecord(student_id=s_mid.id, date=d1, status="Present"),
            AttendanceRecord(student_id=s_mid.id, date=d2, status="Present"),
            AttendanceRecord(student_id=s_mid.id, date=d3, status="Absent"),

            AttendanceRecord(student_id=s_high.id, date=d1, status="Present"),
            AttendanceRecord(student_id=s_high.id, date=d2, status="Present"),
            AttendanceRecord(student_id=s_high.id, date=d3, status="Present"),
        ])
        db.session.commit()

    # 1. Default / lowest first sort
    res_default = client.get("/reports?sort=lowest", headers={"Accept": "application/json"})
    assert res_default.status_code == 200
    data_lowest = res_default.get_json()["reports"]
    assert data_lowest[0]["usn"] == "1MS21CS001"  # 0%
    assert data_lowest[1]["usn"] == "1MS21CS002"  # 66.67%
    assert data_lowest[2]["usn"] == "1MS21CS003"  # 100%

    # 2. Highest first sort
    res_highest = client.get("/reports?sort=highest", headers={"Accept": "application/json"})
    assert res_highest.status_code == 200
    data_highest = res_highest.get_json()["reports"]
    assert data_highest[0]["usn"] == "1MS21CS003"  # 100%
    assert data_highest[1]["usn"] == "1MS21CS002"  # 66.67%
    assert data_highest[2]["usn"] == "1MS21CS001"  # 0%

    # 3. HTML view check
    res_html = client.get("/reports")
    assert res_html.status_code == 200
    html = res_html.get_data(as_text=True)
    assert "Attendance Summary &amp; Metrics" in html or "Attendance Summary & Metrics" in html
    assert "Shortage (<75%)" in html or "Shortage (&lt;75%)" in html
    assert "Low Attendance" in html
    assert "High Attendance" in html
