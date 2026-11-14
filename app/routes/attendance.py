"""
Daily Attendance & Reports Routes
---------------------------------
Handles daily attendance marking, idempotent bulk submissions with atomic transactions,
and class-wide attendance summary reports with dynamic sorting and shortage indicators.
"""

import csv
from datetime import date, datetime
import io
from typing import Dict, List, Optional
from flask import Blueprint, Response, flash, jsonify, redirect, render_template, request, stream_with_context, url_for
from app.extensions import db
from app.models import AttendanceRecord, AttendanceStatus, Student
from app.services.attendance_service import calculate_attendance_summary

attendance_bp = Blueprint("attendance", __name__)


def _is_json_request() -> bool:
    """Helper to detect if incoming client request expects JSON response."""
    return request.is_json or request.headers.get("Accept") == "application/json"


def _parse_target_date(raw_date: Optional[str]) -> tuple[date, bool]:
    """
    Safely parses an ISO date string ('YYYY-MM-DD').
    Falls back to current calendar date if omitted or invalid.

    Returns:
        tuple[date, bool]: (parsed_date, is_fallback_due_to_error)
    """
    if not raw_date or not str(raw_date).strip():
        return date.today(), False

    try:
        parsed = datetime.strptime(str(raw_date).strip(), "%Y-%m-%d").date()
        return parsed, False
    except (ValueError, TypeError):
        return date.today(), True


@attendance_bp.route("/attendance", methods=["GET"])
@attendance_bp.route("/attendance/", methods=["GET"])
def attendance_index():
    """Redirects /attendance base URL to the mark attendance sheet."""
    return redirect(url_for("attendance.mark_attendance"))


@attendance_bp.route("/attendance/mark", methods=["GET"])
def mark_attendance():
    """
    GET /attendance/mark
    Renders the daily attendance marking sheet for a selected date (defaults to today).
    Loads all enrolled students and pre-fills existing attendance statuses if records
    for that calendar date were previously submitted.
    """
    date_arg = request.args.get("date")
    target_date, had_parse_error = _parse_target_date(date_arg)

    if had_parse_error:
        flash(f"Invalid date format '{date_arg}'. Defaulted to today's date ({target_date.isoformat()}).", "warning")

    # Fetch all students ordered alphabetically by USN
    students = Student.query.order_by(Student.usn.asc()).all()

    # Query any existing attendance records for the chosen date
    existing_records = AttendanceRecord.query.filter_by(date=target_date).all()
    attendance_map: Dict[int, str] = {rec.student_id: rec.status for rec in existing_records}
    has_existing_records: bool = len(existing_records) > 0

    if _is_json_request():
        return jsonify({
            "status": "success",
            "date": target_date.isoformat(),
            "has_existing_records": has_existing_records,
            "total_students": len(students),
            "marked_records_count": len(existing_records),
            "records": [
                {
                    "student_id": s.id,
                    "usn": s.usn,
                    "name": s.name,
                    "status": attendance_map.get(s.id, AttendanceStatus.PRESENT.value),
                    "already_recorded": s.id in attendance_map
                }
                for s in students
            ]
        }), 200

    return render_template(
        "mark_attendance.html",
        students=students,
        selected_date=target_date.isoformat(),
        today_date=date.today().isoformat(),
        attendance_map=attendance_map,
        has_existing_records=has_existing_records
    )


@attendance_bp.route("/attendance/mark", methods=["POST"])
def submit_attendance():
    """
    POST /attendance/mark
    Handles bulk submission of attendance statuses (Present/Absent) for all students on a given date.
    Executes an atomic database transaction (commit / rollback) ensuring all student records
    are either safely inserted/updated together or cleanly rolled back on any exception.
    """
    is_json = request.is_json
    payload = request.get_json(silent=True) if is_json else request.form

    raw_date = payload.get("date")
    target_date, had_parse_error = _parse_target_date(raw_date)

    if had_parse_error and not raw_date:
        target_date = date.today()

    # Parse student statuses from form data or JSON payload
    student_status_map: Dict[int, str] = {}

    if is_json and payload:
        # JSON structure 1: {"date": "...", "records": [{"student_id": 1, "status": "Present"}]}
        if "records" in payload and isinstance(payload["records"], list):
            for item in payload["records"]:
                if isinstance(item, dict) and "student_id" in item and "status" in item:
                    try:
                        student_status_map[int(item["student_id"])] = str(item["status"]).strip().capitalize()
                    except (ValueError, TypeError):
                        pass

        # JSON structure 2: {"date": "...", "attendance": {"1": "Present", "2": "Absent"}}
        elif "attendance" in payload and isinstance(payload["attendance"], dict):
            for sid_str, status_val in payload["attendance"].items():
                try:
                    student_status_map[int(sid_str)] = str(status_val).strip().capitalize()
                except (ValueError, TypeError):
                    pass

    # HTML Form Data: e.g. status_1=Present, status_2=Absent, or attendance_1=Present
    if not student_status_map:
        for key, value in request.form.items():
            if key.startswith("status_"):
                sid_str = key.replace("status_", "")
                try:
                    student_status_map[int(sid_str)] = str(value).strip().capitalize()
                except ValueError:
                    pass
            elif key.startswith("attendance_"):
                sid_str = key.replace("attendance_", "")
                try:
                    student_status_map[int(sid_str)] = str(value).strip().capitalize()
                except ValueError:
                    pass

    if not student_status_map:
        error_msg = "Validation Error: No attendance statuses were provided in the submission."
        flash(error_msg, "danger")
        if _is_json_request():
            return jsonify({"status": "error", "message": error_msg}), 400
        return redirect(url_for("attendance.mark_attendance", date=target_date.isoformat()))

    # Atomic transaction execution (commit / rollback)
    try:
        updated_count = 0
        inserted_count = 0

        # Pre-fetch existing records for target_date for efficient upserting
        existing_records = {
            rec.student_id: rec
            for rec in AttendanceRecord.query.filter_by(date=target_date).all()
        }

        valid_statuses = {AttendanceStatus.PRESENT.value, AttendanceStatus.ABSENT.value}

        for sid, raw_status in student_status_map.items():
            # Normalize status to 'Present' or 'Absent'
            clean_status = (
                AttendanceStatus.PRESENT.value
                if raw_status == AttendanceStatus.PRESENT.value
                else AttendanceStatus.ABSENT.value
            )

            if sid in existing_records:
                existing_record = existing_records[sid]
                if existing_record.status != clean_status:
                    existing_record.status = clean_status
                    updated_count += 1
            else:
                new_record = AttendanceRecord(
                    student_id=sid,
                    date=target_date,
                    status=clean_status
                )
                db.session.add(new_record)
                inserted_count += 1

        db.session.commit()

        success_msg = (
            f"Attendance for {target_date.strftime('%d %b %Y')} successfully saved: "
            f"{inserted_count} recorded, {updated_count} updated."
        )
        flash(success_msg, "success")

        if _is_json_request():
            return jsonify({
                "status": "success",
                "message": success_msg,
                "date": target_date.isoformat(),
                "inserted": inserted_count,
                "updated": updated_count,
                "total_processed": len(student_status_map)
            }), 200

        return redirect(url_for("attendance.mark_attendance", date=target_date.isoformat()))

    except Exception as exc:
        db.session.rollback()
        error_msg = f"Database Transaction Error: Failed to save attendance. {str(exc)}"
        flash(error_msg, "danger")
        if _is_json_request():
            return jsonify({"status": "error", "message": error_msg}), 500
        return redirect(url_for("attendance.mark_attendance", date=target_date.isoformat()))


@attendance_bp.route("/reports", methods=["GET"])
@attendance_bp.route("/attendance/reports", methods=["GET"])
def reports():
    """
    GET /reports
    Returns attendance summaries for the entire class with dynamic sorting capability
    (e.g., sort by lowest attendance first to highlight students with shortage).
    """
    # Fetch all student summaries using dedicated service function
    summaries = calculate_attendance_summary(student_id=None)

    # Dynamic Sorting Logic
    sort_param = request.args.get("sort", "lowest").lower().strip()

    if sort_param in {"lowest", "asc", "attendance_asc"}:
        # Lowest attendance first (default for identifying shortage)
        summaries.sort(key=lambda x: (x["attendance_percentage"], x["usn"]))
    elif sort_param in {"highest", "desc", "attendance_desc"}:
        # Highest attendance first
        summaries.sort(key=lambda x: (-x["attendance_percentage"], x["usn"]))
    elif sort_param in {"usn", "usn_asc"}:
        # Sort alphabetically by USN
        summaries.sort(key=lambda x: x["usn"])
    elif sort_param in {"name", "name_asc"}:
        # Sort alphabetically by Student Name
        summaries.sort(key=lambda x: x["name"].lower())
    elif sort_param in {"shortage", "shortage_first"}:
        # Shortage students (<75%) first, then lowest percentage
        summaries.sort(key=lambda x: (not x["is_shortage"], x["attendance_percentage"]))
    else:
        # Fallback to lowest first
        summaries.sort(key=lambda x: (x["attendance_percentage"], x["usn"]))

    total_classes_held: int = (
        db.session.query(db.func.count(db.distinct(AttendanceRecord.date))).scalar() or 0
    )
    shortage_count: int = sum(1 for s in summaries if s["is_shortage"])
    total_students: int = len(summaries)
    avg_percentage: float = (
        round(sum(s["attendance_percentage"] for s in summaries) / total_students, 2)
        if total_students > 0
        else 0.0
    )

    if _is_json_request():
        return jsonify({
            "status": "success",
            "total_students": total_students,
            "total_classes_held": total_classes_held,
            "shortage_count": shortage_count,
            "average_attendance": avg_percentage,
            "sort": sort_param,
            "reports": summaries
        }), 200

    return render_template(
        "reports.html",
        summaries=summaries,
        total_classes_held=total_classes_held,
        shortage_count=shortage_count,
        total_students=total_students,
        avg_percentage=avg_percentage,
        current_sort=sort_param
    )


@attendance_bp.route("/reports/export", methods=["GET"])
@attendance_bp.route("/attendance/reports/export", methods=["GET"])
def export_attendance_csv():
    """
    GET /reports/export
    Queries the attendance summary table and streams a downloadable .csv file directly to the browser.

    Headers:
        USN, Name, Total Classes, Attended Classes, Percentage, Status (Eligible / Shortage)

    Response Headers:
        Content-Disposition: attachment; filename=attendance_report_<date>.csv
        Content-Type: text/csv; charset=utf-8
    """
    # 1. Fetch attendance summaries
    summaries = calculate_attendance_summary(student_id=None)

    # 2. Support optional sort parameter matching the reports view
    sort_param = request.args.get("sort", "usn").lower().strip()
    if sort_param in {"lowest", "asc", "attendance_asc"}:
        summaries.sort(key=lambda x: (x["attendance_percentage"], x["usn"]))
    elif sort_param in {"highest", "desc", "attendance_desc"}:
        summaries.sort(key=lambda x: (-x["attendance_percentage"], x["usn"]))
    elif sort_param in {"name", "name_asc"}:
        summaries.sort(key=lambda x: x["name"].lower())
    elif sort_param in {"shortage", "shortage_first"}:
        summaries.sort(key=lambda x: (not x["is_shortage"], x["attendance_percentage"]))
    else:
        summaries.sort(key=lambda x: x["usn"])

    # 3. Determine report date for filename
    date_arg = request.args.get("date")
    if date_arg and date_arg.strip():
        try:
            report_date = datetime.strptime(date_arg.strip(), "%Y-%m-%d").date().isoformat()
        except (ValueError, TypeError):
            report_date = date.today().isoformat()
    else:
        report_date = date.today().isoformat()

    filename = f"attendance_report_{report_date}.csv"

    # 4. Stream CSV generation using Python's built-in csv and io.StringIO
    def generate():
        output = io.StringIO()
        writer = csv.writer(output)

        # Header row: USN, Name, Total Classes, Attended Classes, Percentage, Status (Eligible / Shortage)
        writer.writerow([
            "USN",
            "Name",
            "Total Classes",
            "Attended Classes",
            "Percentage",
            "Status (Eligible / Shortage)",
        ])
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)

        # Data rows
        for item in summaries:
            status_label = "Shortage" if item.get("is_shortage") else "Eligible"
            percentage_val = f"{item.get('attendance_percentage', 0.0)}%"
            writer.writerow([
                item.get("usn", ""),
                item.get("name", ""),
                item.get("total_classes_held", 0),
                item.get("classes_attended", 0),
                percentage_val,
                status_label,
            ])
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)

    return Response(
        stream_with_context(generate()),
        mimetype="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "Content-Type": "text/csv; charset=utf-8",
        },
    )
