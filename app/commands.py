"""
AttendSync Custom Flask CLI Commands
------------------------------------
Provides CLI management commands for database lifecycle and test data seeding:
- `flask init-db`: Creates/recreates database tables
- `flask seed-db`: Populates the database with realistic sample student & attendance data
"""

from datetime import date, timedelta
import click
from flask import Flask
from app.extensions import db
from app.models import AttendanceRecord, AttendanceStatus, Student


SAMPLE_STUDENTS = [
    {
        "usn": "1MS21CS001",
        "name": "Aarav Sharma",
        "email": "aarav.cs21@college.edu",
        "department": "Computer Science & Engineering",
        "semester": 6,
        "section": "A",
    },
    {
        "usn": "1MS21CS042",
        "name": "Ananya Iyer",
        "email": "ananya.cs21@college.edu",
        "department": "Computer Science & Engineering",
        "semester": 6,
        "section": "A",
    },
    {
        "usn": "1MS22IS015",
        "name": "Rohan Verma",
        "email": "rohan.is22@college.edu",
        "department": "Information Science & Engineering",
        "semester": 4,
        "section": "B",
    },
    {
        "usn": "1MS22EC028",
        "name": "Priya Nair",
        "email": "priya.ec22@college.edu",
        "department": "Electronics & Communication Engineering",
        "semester": 4,
        "section": "A",
    },
    {
        "usn": "1MS23AI005",
        "name": "Karthik Raghavan",
        "email": "karthik.ai23@college.edu",
        "department": "Artificial Intelligence & Data Science",
        "semester": 2,
        "section": "C",
    },
    {
        "usn": "1MS21ME012",
        "name": "Sneha Patil",
        "email": "sneha.me21@college.edu",
        "department": "Mechanical Engineering",
        "semester": 6,
        "section": "B",
    },
    {
        "usn": "1MS22CS089",
        "name": "Devansh Gupta",
        "email": "devansh.cs22@college.edu",
        "department": "Computer Science & Engineering",
        "semester": 4,
        "section": "B",
    },
    {
        "usn": "1MS23EC044",
        "name": "Meera Nambiar",
        "email": "meera.ec23@college.edu",
        "department": "Electronics & Communication Engineering",
        "semester": 2,
        "section": "A",
    },
]


def register_commands(app: Flask):
    """Registers custom CLI commands with the Flask application instance."""

    @app.cli.command("init-db")
    @click.option(
        "--drop",
        is_flag=True,
        help="Drop all existing tables before recreating them."
    )
    def init_db_command(drop):
        """Creates all database tables defined by SQLAlchemy models."""
        if drop:
            click.confirm(
                "Are you sure you want to drop all existing tables and data?",
                abort=True
            )
            db.drop_all()
            click.echo("Dropped existing database tables.")

        db.create_all()
        click.secho("[OK] Database initialized successfully. All tables created.", fg="green", bold=True)

    @app.cli.command("seed-db")
    def seed_db_command():
        """Seeds the database with realistic sample students and attendance records."""
        # Ensure tables exist
        db.create_all()

        added_students = 0
        skipped_students = 0

        created_student_instances = []

        for data in SAMPLE_STUDENTS:
            existing = Student.query.filter_by(usn=data["usn"]).first()
            if existing:
                skipped_students += 1
                created_student_instances.append(existing)
            else:
                student = Student(**data)
                db.session.add(student)
                created_student_instances.append(student)
                added_students += 1

        db.session.commit()

        # Seed sample attendance records across recent dates (e.g., today and previous 2 days)
        today = date.today()
        dates_to_seed = [today - timedelta(days=2), today - timedelta(days=1), today]

        added_records = 0
        skipped_records = 0

        for s_idx, student in enumerate(created_student_instances):
            for d_idx, day in enumerate(dates_to_seed):
                # Deterministic presence pattern for realistic testing
                status = (
                    AttendanceStatus.ABSENT.value
                    if (s_idx + d_idx) % 4 == 0
                    else AttendanceStatus.PRESENT.value
                )

                existing_record = AttendanceRecord.query.filter_by(
                    student_id=student.id,
                    date=day
                ).first()

                if existing_record:
                    skipped_records += 1
                else:
                    rec = AttendanceRecord(
                        student_id=student.id,
                        date=day,
                        status=status
                    )
                    db.session.add(rec)
                    added_records += 1

        db.session.commit()

        click.echo("--------------------------------------------------")
        click.secho("[OK] AttendSync Database Seeding Completed!", fg="green", bold=True)
        click.echo(f"Students   : {added_students} inserted, {skipped_students} already existed")
        click.echo(f"Attendance : {added_records} records inserted, {skipped_records} already existed")
        click.echo("--------------------------------------------------")
