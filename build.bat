@echo off
chcp 65001 > nul
title YangEraDB — Build & Package System
color 0A

echo.
echo  ╔══════════════════════════════════════════════════════╗
echo  ║     قنادی تیموریان — ERP Builder       ║
echo  ║              Designed by YangEra                     ║
echo  ╚══════════════════════════════════════════════════════╝
echo.

:: ─── STEP 1: Check Python ─────────────────────────────────────────────────
echo [1/7] Checking Python 3.11...
python --version 2>nul | findstr /i "3.11" > nul
if errorlevel 1 (
    echo.
    echo  ERROR: Python 3.11 not found or not in PATH.
    echo  Please install Python 3.11 and try again.
    echo.
    pause
    exit /b 1
)
echo  OK — Python 3.11 found.
echo.

:: ─── STEP 2: Install / upgrade dependencies ───────────────────────────────
echo [2/7] Installing required packages...
python -m pip install --upgrade pip --quiet
python -m pip install pyinstaller --upgrade --quiet
python -m pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo.
    echo  ERROR: Failed to install packages from requirements.txt
    echo  Check your requirements.txt file and internet connection.
    echo.
    pause
    exit /b 1
)
echo  OK — All packages installed.
echo.

:: ─── STEP 3: Run Django migrations ───────────────────────────────────────
echo [3/7] Running Django migrations...
python manage.py migrate --run-syncdb
if errorlevel 1 (
    echo  WARNING: Migration had issues. Continuing anyway...
)
echo  OK — Migrations complete.
echo.

:: ─── STEP 4: Collect static files ────────────────────────────────────────
echo [4/7] Collecting static files...
python manage.py collectstatic --noinput
if errorlevel 1 (
    echo  WARNING: Collectstatic had issues. Continuing anyway...
)
echo  OK — Static files collected.
echo.

:: ─── STEP 5: Clean previous build ────────────────────────────────────────
echo [5/7] Cleaning previous build...
if exist "dist\YangEraDB" (
    rmdir /s /q "dist\YangEraDB"
    echo  OK — Previous dist cleaned.
) else (
    echo  OK — No previous dist found.
)
if exist "build" (
    rmdir /s /q "build"
)
echo.

:: ─── STEP 6: Run PyInstaller ──────────────────────────────────────────────
echo [6/7] Building executable with PyInstaller...
echo  (This may take 5-15 minutes, please wait...)
echo.
pyinstaller taimourian_erp.spec --noconfirm
if errorlevel 1 (
    echo.
    echo  ERROR: PyInstaller build failed!
    echo  Check the error messages above.
    echo.
    pause
    exit /b 1
)
echo.
echo  OK — Executable built successfully.
echo  Location: dist\YangEraDB\YangEraDB.exe
echo.

:: ─── STEP 7: Open dist folder ────────────────────────────────────────────
echo [7/7] Opening output folder...
explorer dist\YangEraDB
echo.

echo  ╔══════════════════════════════════════════════════════╗
echo  ║              BUILD COMPLETE!                         ║
echo  ║                                                      ║
echo  ║  EXE is ready in:  dist\YangEraDB\                  ║
echo  ║                                                      ║
echo  ║  NEXT STEP:                                          ║
echo  ║  Open taimourian_erp_installer.iss in Inno Setup          ║
echo  ║  Press Ctrl+F9 to create the .exe installer          ║
echo  ║                                                      ║
echo  ║  Default Login:  admin / admin123                    ║
echo  ╚══════════════════════════════════════════════════════╝
echo.
pause
