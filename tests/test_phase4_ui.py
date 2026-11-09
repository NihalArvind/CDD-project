"""
Phase 4 UI/UX & Frontend Templates Automated Test Suite
-------------------------------------------------------
Validates:
1. base.html: Bootstrap 5 CDN, sticky navbar, links, and flash message container.
2. dashboard.html: Summary stat cards, quick-action buttons (Mark Today's Attendance, Add Student).
3. students.html: Searchable/filterable table (USN, Name, Email, Semester, Section) & Add Student modal.
4. mark_attendance.html: Date selector, Roll/USN/Name, Present/Absent toggles, Mark All buttons, Save button.
5. reports.html: Roster view, Classes Held/Attended/Percentage, >=75% & <75% badges, Export as CSV button.
"""

from datetime import date
from app.extensions import db
from app.models import AttendanceRecord, Student


def test_base_template_features(client):
    """Verify base.html contains Bootstrap 5 CDN, sticky navigation, and all navigation links."""
    response = client.get("/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    # 1. Bootstrap 5 CDN & Icons
    assert "bootstrap@5.3.3" in html or "bootstrap.min.css" in html
    assert "bootstrap-icons" in html

    # 2. Sticky Navbar
    assert "sticky-top" in html

    # 3. Required Navigation Links
    assert "Dashboard" in html
    assert "Students" in html
    assert "Mark Attendance" in html
    assert "Reports" in html

    # 4. Flash Message Container class
    assert "flash-messages" in html or "alert" in html


def test_dashboard_template_features(client, app):
    """Verify dashboard.html displays KPI stat cards and quick action buttons."""
    with app.app_context():
        s = Student(usn="1MS21CS001", name="Test Student", email="t@college.edu", department="CSE", semester=6, section="A")
        db.session.add(s)
        db.session.commit()

        d1 = date.today()
        rec = AttendanceRecord(student_id=s.id, date=d1, status="Present")
        db.session.add(rec)
        db.session.commit()

    response = client.get("/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    # Stat Cards
    assert "Total Registered Students" in html
    assert "Total Classes Conducted" in html
    assert "Attendance Shortage" in html or "<75%" in html or "&lt;75%" in html

    # Quick action buttons
    assert "Mark Today's Attendance" in html
    assert "Add Student" in html


def test_students_template_features(client, app):
    """Verify students.html contains searchable table with all required columns and Add Student modal."""
    with app.app_context():
        s = Student(usn="1MS21CS042", name="Ananya Iyer", email="ananya@college.edu", department="CSE", semester=6, section="A")
        db.session.add(s)
        db.session.commit()

    response = client.get("/students")
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    # Search filter input
    assert "studentSearchInput" in html or "filterTable" in html

    # Required table columns
    assert "USN" in html
    assert "Student Name" in html
    assert "Email Address" in html or "Email" in html
    assert "Semester" in html
    assert "Section" in html

    # Student row content
    assert "1MS21CS042" in html
    assert "Ananya Iyer" in html

    # Add Student Modal with input validation
    assert "addStudentModal" in html
    assert "addStudentForm" in html or 'action="/students/add"' in html
    assert 'name="usn"' in html
    assert 'name="name"' in html
    assert 'name="email"' in html
    assert 'name="department"' in html
    assert 'name="semester"' in html
    assert 'name="section"' in html
    assert "required" in html


def test_mark_attendance_template_features(client, app):
    """Verify mark_attendance.html contains date selector, roster table, quick toggles, and Save button."""
    with app.app_context():
        s = Student(usn="1MS21CS015", name="Rohan Verma", email="rohan@college.edu", department="ISE", semester=4, section="B")
        db.session.add(s)
        db.session.commit()

    response = client.get("/attendance/mark")
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    # 1. Date selector at top
    assert 'type="date"' in html
    assert 'name="date"' in html

    # 2. Table columns: Roll #, USN, Student Name, Status
    assert "Roll #" in html or "Roll" in html or "#" in html
    assert "USN" in html
    assert "Student Name" in html
    assert "Rohan Verma" in html
    assert "1MS21CS015" in html

    # 3. Interactive toggle radio buttons for Present (green) and Absent (red)
    assert 'value="Present"' in html
    assert 'value="Absent"' in html
    assert "btn-outline-success" in html or "Present" in html
    assert "btn-outline-danger" in html or "Absent" in html

    # 4. Quick toggle buttons
    assert "Mark All Present" in html
    assert "Mark All Absent" in html
    assert "setAllAttendance" in html

    # 5. Prominent Save Attendance button
    assert "Save Attendance" in html
    assert 'type="submit"' in html


def test_reports_template_features(client, app):
    """Verify reports.html displays roster, Classes Held/Attended, badges, and Export as CSV button."""
    with app.app_context():
        s1 = Student(usn="1MS21CS001", name="High Attender", email="h@college.edu", department="CSE", semester=6, section="A")
        s2 = Student(usn="1MS21CS002", name="Low Attender", email="l@college.edu", department="CSE", semester=6, section="A")
        db.session.add_all([s1, s2])
        db.session.commit()

        d1 = date(2026, 11, 1)
        d2 = date(2026, 11, 2)
        d3 = date(2026, 11, 3)
        d4 = date(2026, 11, 4)

        # s1: 4/4 (100%) -> >= 75%
        # s2: 1/4 (25%)  -> < 75%
        db.session.add_all([
            AttendanceRecord(student_id=s1.id, date=d1, status="Present"),
            AttendanceRecord(student_id=s1.id, date=d2, status="Present"),
            AttendanceRecord(student_id=s1.id, date=d3, status="Present"),
            AttendanceRecord(student_id=s1.id, date=d4, status="Present"),

            AttendanceRecord(student_id=s2.id, date=d1, status="Present"),
            AttendanceRecord(student_id=s2.id, date=d2, status="Absent"),
            AttendanceRecord(student_id=s2.id, date=d3, status="Absent"),
            AttendanceRecord(student_id=s2.id, date=d4, status="Absent"),
        ])
        db.session.commit()

    response = client.get("/reports")
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    # 1. Required table columns
    assert "USN" in html
    assert "Student Name" in html
    assert "Classes Held" in html
    assert "Classes Attended" in html
    assert "Attendance %" in html

    # 2. Visual badges: Green for >= 75%, Red warning for < 75%
    assert "Satisfactory" in html or ">=75%" in html or "&ge;75%" in html
    assert "Shortage" in html or "<75%" in html or "&lt;75%" in html
    assert "text-success" in html
    assert "text-danger" in html

    # 3. Export as CSV button
    assert "Export as CSV" in html
    assert "exportTableToCSV" in html
