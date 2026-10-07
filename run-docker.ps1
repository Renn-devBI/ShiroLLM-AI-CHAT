# SHIRO Docker Runner Script
# Cara pakai: .\run-docker.ps1

param(
    [Parameter(Mandatory=$false)]
    [ValidateSet("start", "stop", "restart", "logs", "build", "status")]
    [string]$Command = "start"
)

Write-Host "╔═══════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║      SHIRO v5 LLMA Docker Runner      ║" -ForegroundColor Cyan
Write-Host "╚═══════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# Check if Docker is installed
try {
    $dockerVersion = docker --version 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Docker not installed"
    }
} catch {
    Write-Host "❌ Error: Docker Desktop is not installed or not running" -ForegroundColor Red
    Write-Host "📥 Download: https://www.docker.com/products/docker-desktop" -ForegroundColor Yellow
    exit 1
}

Write-Host "✅ Docker found: $dockerVersion" -ForegroundColor Green
Write-Host ""

switch ($Command) {
    "start" {
        Write-Host "🚀 Starting SHIRO Docker container..." -ForegroundColor Green
        docker-compose up -d
        
        if ($LASTEXITCODE -eq 0) {
            Start-Sleep -Seconds 3
            Write-Host ""
            Write-Host "✅ Container started successfully!" -ForegroundColor Green
            Write-Host "📍 Access at: http://localhost:7474" -ForegroundColor Cyan
            Write-Host "📋 View logs: docker-compose logs -f" -ForegroundColor Yellow
            Write-Host ""
        } else {
            Write-Host "❌ Failed to start container" -ForegroundColor Red
            exit 1
        }
    }
    
    "stop" {
        Write-Host "🛑 Stopping SHIRO Docker container..." -ForegroundColor Yellow
        docker-compose down
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host "✅ Container stopped" -ForegroundColor Green
        } else {
            Write-Host "❌ Failed to stop container" -ForegroundColor Red
        }
    }
    
    "restart" {
        Write-Host "🔄 Restarting SHIRO Docker container..." -ForegroundColor Green
        docker-compose restart
        
        if ($LASTEXITCODE -eq 0) {
            Start-Sleep -Seconds 2
            Write-Host "✅ Container restarted" -ForegroundColor Green
            Write-Host "📍 Access at: http://localhost:7474" -ForegroundColor Cyan
        } else {
            Write-Host "❌ Failed to restart container" -ForegroundColor Red
        }
    }
    
    "logs" {
        Write-Host "📋 Showing live logs (Ctrl+C to stop)..." -ForegroundColor Green
        docker-compose logs -f
    }
    
    "build" {
        Write-Host "🔨 Rebuilding Docker image..." -ForegroundColor Green
        docker-compose up --build -d
        
        if ($LASTEXITCODE -eq 0) {
            Start-Sleep -Seconds 3
            Write-Host ""
            Write-Host "✅ Image rebuilt and container started!" -ForegroundColor Green
            Write-Host "📍 Access at: http://localhost:7474" -ForegroundColor Cyan
        } else {
            Write-Host "❌ Failed to rebuild image" -ForegroundColor Red
        }
    }
    
    "status" {
        Write-Host "📊 Container Status:" -ForegroundColor Cyan
        Write-Host ""
        docker-compose ps
        Write-Host ""
        Write-Host "📊 Resource Usage:" -ForegroundColor Cyan
        docker stats shiro-llma --no-stream
    }
    
    default {
        Write-Host "Usage: .\run-docker.ps1 [command]" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "Available commands:" -ForegroundColor Cyan
        Write-Host "  start      - Start container (default)" -ForegroundColor Green
        Write-Host "  stop       - Stop container" -ForegroundColor Yellow
        Write-Host "  restart    - Restart container" -ForegroundColor Cyan
        Write-Host "  logs       - View live logs" -ForegroundColor Magenta
        Write-Host "  build      - Rebuild and start" -ForegroundColor Blue
        Write-Host "  status     - Show container status" -ForegroundColor DarkCyan
        Write-Host ""
        Write-Host "Examples:" -ForegroundColor Yellow
        Write-Host "  .\run-docker.ps1" -ForegroundColor Gray
        Write-Host "  .\run-docker.ps1 logs" -ForegroundColor Gray
        Write-Host "  .\run-docker.ps1 stop" -ForegroundColor Gray
    }
}
