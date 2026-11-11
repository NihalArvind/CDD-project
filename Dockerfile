# ==============================================================================
# AttendSync Dockerfile
# Stage: Single-stage production & development container
# Base image: Official Python 3.11 slim Debian-based image
# ==============================================================================

FROM python:3.11-slim

# Metadata labels
LABEL maintainer="AttendSync Engineering Team"
LABEL description="AttendSync Attendance Management and Environment Reproducibility"

# Standard Python environment variables:
# - PYTHONDONTWRITEBYTECODE=1: Disables writing .pyc files to disk
# - PYTHONUNBUFFERED=1: Sends stdout/stderr straight to terminal without buffering
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_APP=app.py \
    PORT=5000

# Set standard working directory
WORKDIR /app

# Multi-layer caching:
# Copy and install dependencies first to leverage Docker build cache
COPY requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Security Best Practice: Create a dedicated non-root user and group
# SQLite database files will be created in /app/instance, which needs write access
RUN groupadd -g 1000 appgroup && \
    useradd -u 1000 -g appgroup -s /bin/bash -m -d /home/appuser appuser && \
    mkdir -p /app/instance && \
    chown -R appuser:appgroup /app

# Copy the rest of the application source code with appropriate ownership
COPY --chown=appuser:appgroup . /app

# Ensure permissions on the persistent SQLite instance directory
RUN mkdir -p /app/instance && \
    chown -R appuser:appgroup /app/instance

# Switch from root to non-root user
USER appuser

# Expose the Flask/Gunicorn listening port
EXPOSE 5000

# Container healthcheck using Python's built-in urllib (no extra curl package needed)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/health')" || exit 1

# Standard production WSGI entrypoint using Gunicorn
# (Can be overridden in docker-compose.yml for Flask development auto-reloading)
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--threads", "2", "--access-logfile", "-", "--error-logfile", "-", "wsgi:app"]
