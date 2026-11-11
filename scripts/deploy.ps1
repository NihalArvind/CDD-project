# ==============================================================================
# AttendSync - Automated Docker Deployment & Setup Script (Windows PowerShell)
# ==============================================================================

$ErrorActionPreference = "Stop"

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host " AttendSync: Phase 5 Docker Deployment Pipeline" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

# Check if docker is installed
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error "Docker is not installed or not found in system PATH."
    exit 1
}

# Determine docker compose invocation
$ComposeCmd = "docker-compose"
try {
    docker compose version *> $null
    if ($LASTEXITCODE -eq 0) {
        $ComposeCmd = "docker compose"
    }
} catch {
    $ComposeCmd = "docker-compose"
}

Write-Host "`n[1/4] Building Docker container image..." -ForegroundColor Yellow
if ($ComposeCmd -eq "docker compose") {
    docker compose build --no-cache
} else {
    docker-compose build --no-cache
}

Write-Host "`n[2/4] Starting AttendSync container in detached mode..." -ForegroundColor Yellow
if ($ComposeCmd -eq "docker compose") {
    docker compose up -d
} else {
    docker-compose up -d
}

Write-Host "`n[3/4] Initializing and seeding database..." -ForegroundColor Yellow
Start-Sleep -Seconds 3

if ($ComposeCmd -eq "docker compose") {
    docker compose exec web flask init-db
    docker compose exec web flask seed-db
} else {
    docker-compose exec web flask init-db
    docker-compose exec web flask seed-db
}

Write-Host "`n[4/4] Verifying container status..." -ForegroundColor Yellow
if ($ComposeCmd -eq "docker compose") {
    docker compose ps
} else {
    docker-compose ps
}

Write-Host "`n==================================================" -ForegroundColor Green
Write-Host " AttendSync is running successfully!" -ForegroundColor Green
Write-Host " Dashboard : http://localhost:5000" -ForegroundColor Green
Write-Host " Health    : http://localhost:5000/health" -ForegroundColor Green
Write-Host " Logs      : $ComposeCmd logs -f web" -ForegroundColor Green
Write-Host " Stop      : $ComposeCmd down" -ForegroundColor Green
Write-Host "==================================================" -ForegroundColor Green
