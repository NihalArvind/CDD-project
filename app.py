"""
AttendSync Application Server Entry Point (app.py)
--------------------------------------------------
Exposes the top-level application instance 'app' for the Flask CLI
(`FLASK_APP=app.py`), Gunicorn, and containerized development environments.
"""

import os
from app import create_app, db

# Determine active environment configuration
env_name = os.getenv("FLASK_ENV", "development")
app = create_app(env_name)

if __name__ == "__main__":
    # Ensure database schema is initialized for local execution
    with app.app_context():
        db.create_all()

    # Port and host configurations
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 5000))
    debug = app.config.get("DEBUG", True)

    print(f"\n==================================================")
    print(f" AttendSync Application Starting (app.py)")
    print(f" Environment : {env_name}")
    print(f" Listening on: http://{host}:{port}")
    print(f" Health check: http://{host}:{port}/health")
    print(f"==================================================\n")

    app.run(host=host, port=port, debug=debug)
