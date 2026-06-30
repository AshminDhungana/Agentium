@echo off
REM =============================================================================
REM Alembic Downgrade Round-Trip Test Runner
REM =============================================================================
REM Prerequisites:
REM   1. Docker Desktop is running
REM   2. Test infrastructure is up: docker compose -f docker-compose.test.yml up -d
REM   3. Backend code is available at ./backend/
REM
REM Usage: scripts\run_downgrade_test.bat
REM =============================================================================

setlocal

REM Use the test postgres running in docker
set DATABASE_URL=postgresql://agentium:agentium@localhost:5432/agentium_test

REM Create the test database if it doesn't exist
psql postgresql://agentium:agentium@localhost:5432/postgres -c "DROP DATABASE IF EXISTS agentium_test; CREATE DATABASE agentium_test;"
if %errorlevel% neq 0 (
    echo ERROR: Failed to set up test database. Make sure docker compose -f docker-compose.test.yml up -d is running.
    exit /b 1
)

echo.
echo ================================================================================
echo Running Alembic downgrade round-trip test
echo ================================================================================
echo.

REM Run the Python test script
cd backend
python tests/alembic/test_downgrade_roundtrip.py
if %errorlevel% neq 0 (
    echo.
    echo ================================================================================
    echo TEST FAILED
    echo ================================================================================
    exit /b 1
)

echo.
echo ================================================================================
echo TEST PASSED
   echo ================================================================================

endlocal