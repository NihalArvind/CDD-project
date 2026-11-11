# AttendSync: Dockerized Attendance Management & Environment Reproducibility System

AttendSync is a production-ready, modular attendance management application built with **Python 3.11 (Flask)**, **SQLAlchemy (SQLite)**, and **Bootstrap 5**. Designed adhering to 12-factor application methodology, it provides high environment reproducibility through automated Docker containerization, non-root security isolation, atomic data upserts, and responsive attendance analytics.

---

## 📁 Project Directory Structure

```text
CDD-project/
├── app/
│   ├── __init__.py               # Application Factory (create_app) & Blueprint registration
│   ├── extensions.py             # SQLAlchemy instance & SQLite PRAGMA listeners
│   ├── models/                   # Core SQLAlchemy models
│   │   └── __init__.py           # Student, AttendanceRecord, AttendanceStatus
│   ├── crud.py                   # High-performance CRUD query helpers & transactions
│   ├── commands.py               # Custom Flask CLI commands (flask init-db, flask seed-db)
│   ├── services/                 # Business logic & domain calculation services
│   │   ├── __init__.py
│   │   └── attendance_service.py # Attendance metrics calculation & shortage analytics
│   ├── routes/                   # Modular Blueprints (MVC Controllers)
│   │   ├── __init__.py
│   │   ├── main.py               # Root ('/') and health check ('/health') routes
│   │   ├── students.py           # Student management (/students, /students/add, /students/<id>/delete)
│   │   └── attendance.py         # Attendance & reports (/attendance/mark, /reports)
│   ├── static/                   # Static web assets
│   │   ├── css/
│   │   │   └── style.css         # Global responsive styles & theme enhancements
│   │   └── js/
│   │       └── main.js           # Client-side validation, bulk toggles & search filters
│   └── templates/                # Jinja2 presentation templates (MVC Views)
│       ├── base.html             # Bootstrap 5 layout skeleton, sticky navbar & alerts
│       ├── index.html            # Dashboard with KPI stat cards & quick actions
│       ├── students/
│       │   └── index.html        # Student directory with search, filter & modal forms
│       ├── attendance/
│       │   └── mark.html         # Bulk daily attendance roster with toggle switches
│       ├── reports/
│       │   └── index.html        # Sortable analytics report & shortage indicator badges
│       └── errors/
│           ├── 404.html          # Custom 404 Not Found error page
│           └── 500.html          # Custom 500 Internal Server Error page
├── instance/                     # Persistent SQLite DB location (/app/instance/attendsync.db)
├── scripts/                      # Automated deployment scripts
│   ├── deploy.sh                 # Single-command Docker deployment for Linux/macOS
│   └── deploy.ps1                # Single-command Docker deployment for Windows PowerShell
├── tests/                        # Automated Pytest suite (37 tests)
│   ├── __init__.py
│   ├── conftest.py               # Pytest fixtures and isolated app factory setup
│   ├── test_health.py            # Baseline health check & error handler tests
│   ├── test_database.py          # Schema, uniqueness, cascade delete & CLI tests
│   ├── test_phase3_endpoints.py  # RESTful routes, atomic upserts & shortage logic
│   └── test_phase4_ui.py         # UI/UX, Bootstrap components & Jinja2 template tests
├── .dockerignore                 # Excludes cache, virtualenvs, local .env, and test DBs
├── .env.example                  # Environment configuration template
├── .gitignore                    # Git exclusions
├── app.py                        # Primary application runner for Flask CLI & Compose
├── config.py                     # 12-Factor environment configs (Dev, Test, Prod)
├── docker-compose.yml            # Single-command service orchestration with named volume
├── Dockerfile                    # Multi-layer cached, non-root Debian containerfile
├── requirements.txt              # Pinned Python package dependencies (Flask, Gunicorn, etc.)
├── wsgi.py                       # WSGI entrypoint for production HTTP servers
└── README.md                     # Comprehensive project documentation
```

---

## 🗄️ Phase 1 & 2: Database Schema & CLI Commands

### 1. Database Schema
- **`Student` (`students`)**:
  - `id`: Integer Primary Key (Autoincrement)
  - `usn`: Unique, indexed String(20) (e.g., `1MS21CS001`)
  - `name`: String(100)
  - `email`: Unique, indexed String(120)
  - `department`: String(80)
  - `semester`: Integer (1–8)
  - `section`: String(10) (e.g., 'A', 'B')
  - `attendance_records`: One-to-many relationship (`cascade="all, delete-orphan"`)
- **`AttendanceRecord` (`attendance_records`)**:
  - `id`: Integer Primary Key (Autoincrement)
  - `student_id`: Foreign Key (`students.id`, `ondelete="CASCADE"`)
  - `date`: `Date` object (defaults to current date)
  - `status`: Enum (`Present` / `Absent`)
  - **Constraint**: `uq_student_date` composite unique constraint on `(student_id, date)` preventing duplicate entries for a student on the same day.

### 2. Database CLI Commands
```bash
# Initialize SQLite database schema
flask init-db

# Optional: Drop and recreate existing tables
flask init-db --drop

# Seed 8 realistic engineering students and attendance records
flask seed-db
```

---

## 🚦 Phase 3: RESTful Routing, Attendance Business Logic & Reporting

- **Student Management (`app/routes/students.py`)**:
  - `GET /students`: Lists enrolled students ordered by USN. Supports HTML rendering and JSON API clients (`Accept: application/json`).
  - `POST /students/add`: Registers a student with strict USN/email uniqueness validation and dismissible flash alerts.
  - `POST /students/<id>/delete`: Cascades student deletion to all associated attendance records.
- **Daily Attendance Marking (`app/routes/attendance.py`)**:
  - `GET /attendance/mark`: Renders the daily attendance marking roster for a selected date (defaults to today). Pre-fills existing statuses if previously recorded.
  - `POST /attendance/mark`: Handles atomic bulk submission of attendance statuses using database transactions (`commit()` / `rollback()`) to eliminate race conditions and unique constraint conflicts.
- **Metrics & Reporting (`app/services/attendance_service.py`)**:
  - `calculate_attendance_summary(student_id=None)`: Calculates total classes held, classes attended, percentage attendance, and flags students below 75% attendance (`is_shortage=True`). Handles zero classes held gracefully without `ZeroDivisionError`.
  - `GET /reports`: Sortable roster by `?sort=lowest`, `?sort=highest`, `?sort=usn`, or `?sort=shortage`.

---

## 🎨 Phase 4: UI/UX & Responsive Frontend Templates

- **Bootstrap 5 Layout (`base.html`)**: Responsive navbar with active page indicators, dismissible alert messages, and mobile-friendly collapsibility.
- **KPI Dashboard (`index.html`)**: Real-time summary stat cards displaying Total Registered Students, Total Classes Held, Overall Attendance Rate, and Shortage Alerts.
- **Student Roster (`students/index.html`)**: Real-time client-side search filtering, department/semester indicators, and an interactive Add Student modal dialog.
- **Bulk Marking Sheet (`attendance/mark.html`)**: Interactive date picker, quick "Mark All Present" / "Mark All Absent" toggles, and individual radio button state management.
- **Analytics Reports (`reports/index.html`)**: Visual badges for attendance health (green badge for $\ge 75\%$, red danger badge for $< 75\%$ shortage), multi-column sorting, and CSV export functionality.

---

## 🐳 Phase 5: Containerization & Environment Reproducibility (Docker)

Phase 5 fulfills the course environment reproducibility requirements by providing container configuration files adhering to industry DevOps best practices:

### 1. Key Architectural Features
- **Base Image**: `python:3.11-slim` provides a lightweight, Debian-based runtime minimizing security vulnerabilities.
- **Multi-Layer Cache Optimization**: `requirements.txt` is copied and installed prior to copying application source code. Modifying application logic does not invalidate or trigger re-download of pip packages.
- **Non-Root User Security**: Creates and runs under an unprivileged user `appuser` (UID/GID 1000) rather than `root`, adhering to the Principle of Least Privilege (PoLP) and CIS container benchmarks.
- **SQLite Database Persistence**: Employs a dedicated named volume (`attendsync_sqlite_data`) mapped to `/app/instance` so SQLite data persists across container rebuilds, updates, and restarts.
- **Live Development Hot-Reloading**: Volume binding (`.:/app`) in `docker-compose.yml` mounts local host files into the container so template and code edits take effect instantly without rebuilding the container.
- **Dual Server Entrypoints**: Supports Gunicorn as the production WSGI server (`CMD ["gunicorn", ...]`) while allowing Docker Compose to override with the Flask hot-reloading development server (`command: flask run --reload`).
- **Native Healthcheck**: Implements a zero-dependency health check probe utilizing Python's built-in `urllib.request` against `/health`.

---

## 🚀 Deployment & Run Guide

### Option 1: Docker Compose (Recommended)

#### 1. Start Services in Detached Mode
```bash
docker-compose up -d --build
```

#### 2. Seed Database Inside Container
```bash
docker-compose exec web flask seed-db
```

#### 3. View Live Logs
```bash
docker-compose logs -f web
```

#### 4. Stop Services
```bash
# Stop containers (preserves database volume)
docker-compose down

# Stop containers AND wipe persistent database volume
docker-compose down -v
```

---

### Option 2: Automated Deployment Scripts

Automated deployment scripts are provided in `scripts/`:

**On Linux / macOS:**
```bash
chmod +x scripts/deploy.sh
./scripts/deploy.sh
```

**On Windows (PowerShell):**
```powershell
.\scripts\deploy.ps1
```

These scripts verify Docker connectivity, build images, boot services detached, run `flask init-db` and `flask seed-db`, and verify the `/health` endpoint automatically.

---

### Option 3: Standalone Docker CLI

```bash
# 1. Build Docker image
docker build -t attendsync:latest .

# 2. Create named volume for SQLite persistence
docker volume create attendsync_sqlite_data

# 3. Run container in detached mode
docker run -d \
  --name attendsync_web \
  -p 5000:5000 \
  --restart unless-stopped \
  -v attendsync_sqlite_data:/app/instance \
  attendsync:latest

# 4. View container logs
docker logs -f attendsync_web

# 5. Seed database inside container
docker exec -it attendsync_web flask seed-db

# 6. Stop and remove container
docker stop attendsync_web
docker rm attendsync_web
```

---

### Option 4: Local Python Environment (Without Docker)

```bash
# 1. Create and activate virtual environment
python -m venv .venv

# On Windows:
.\.venv\Scripts\Activate.ps1
# On Linux/macOS:
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Initialize & seed database
flask init-db
flask seed-db

# 4. Run application
python app.py
```

---

## 🌐 Application URL Reference

Once running (locally or via Docker), access the following endpoints:

| Section | URL | Description |
| :--- | :--- | :--- |
| **Dashboard** | [http://localhost:5000/](http://localhost:5000/) | Class KPI cards & quick-action buttons |
| **Students** | [http://localhost:5000/students](http://localhost:5000/students) | Student directory & registration modal |
| **Mark Attendance** | [http://localhost:5000/attendance/mark](http://localhost:5000/attendance/mark) | Date-based bulk attendance sheet |
| **Reports** | [http://localhost:5000/reports](http://localhost:5000/reports) | Attendance metrics & shortage alerts (<75%) |
| **Health API** | [http://localhost:5000/health](http://localhost:5000/health) | System & database health probe (`JSON`) |

---

## 🧪 Automated Testing Suite

AttendSync features a comprehensive Pytest test suite with **37 passing tests** spanning all 5 phases:

```bash
pytest -v
```

### Coverage Breakdown:
1. **`tests/test_health.py`**:
   - Health check endpoint verification (`/health`)
   - Root dashboard response (`/`)
   - Custom 404 error page handling for both HTML and JSON requests
2. **`tests/test_database.py`**:
   - Student model creation, USN uniqueness, and email uniqueness
   - Composite unique constraint on `(student_id, date)` preventing duplicate marking
   - Foreign key cascading deletion of attendance records
   - High-performance CRUD helpers (`get_all_students_sorted`, `record_attendance`, etc.)
   - Database initialization (`flask init-db`) and sample data seeding (`flask seed-db`)
3. **`tests/test_phase3_endpoints.py`**:
   - Student listing and adding via HTML form and JSON API
   - Daily attendance sheet pre-filling for existing dates
   - Bulk atomic attendance upserts and transaction rollback protection
   - Attendance percentage calculations and shortage boundary checks ($\ge 75\%$ vs $< 75\%$)
   - Graceful fallback for 0 classes held
   - Dynamic report roster sorting (`?sort=lowest`, `?sort=highest`, `?sort=usn`, `?sort=shortage`)
4. **`tests/test_phase4_ui.py`**:
   - Bootstrap 5 CDN integration, sticky navbar, and navigation links
   - Dashboard stat cards and action buttons
   - Students table, search filters, and modal inputs
   - Mark attendance table toggles and bulk mark actions
   - Report table shortage badges and CSV export elements

---

## ⚙️ Environment Variables Reference

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `FLASK_APP` | `app.py` | Flask application entrypoint |
| `FLASK_ENV` | `development` | Active environment configuration (`development`, `testing`, `production`) |
| `FLASK_DEBUG` | `1` | Enables Flask auto-reloading and debug traceback in development |
| `SECRET_KEY` | `dev-secret-key-attendsync...` | Cryptographic secret key for session cookies and flash messages |
| `DATABASE_URL` | `sqlite:///instance/attendsync.db` | SQLite database URI (persisted in `/app/instance`) |
| `PORT` | `5000` | Port on which Gunicorn / Flask listens |
