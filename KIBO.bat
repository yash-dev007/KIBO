@echo off
title KIBO
cd /d D:\Projects\KIBO

echo [KIBO] Starting Python backend...
start "KIBO Backend" cmd /k "cd /d D:\Projects\KIBO && uv run python -m src.api.main"

echo [KIBO] Waiting for backend to initialise...
timeout /t 3 /nobreak >nul

echo [KIBO] Starting Electron frontend...
cd frontend
set KIBO_SKIP_PYTHON_BRIDGE=1
npm run dev
