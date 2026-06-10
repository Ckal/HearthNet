@echo off
REM HearthNet App Manager - Windows Batch Menu
REM This script provides a menu to start, stop, configure, and manage the HearthNet app

setlocal enabledelayedexpansion
cls
title HearthNet App Manager

:main_menu
cls
echo.
echo ╔════════════════════════════════════════════════════════════════════╗
echo ║                   HearthNet App Manager (Windows)                  ║
echo ╚════════════════════════════════════════════════════════════════════╝
echo.
echo 1. Start HearthNet (CLI Mode)
echo 2. Start HearthNet (Gradio Web UI)
echo 3. Start Multi-Node Demo (2 nodes)
echo 4. Stop HearthNet (All instances)
echo.
echo 5. Install Dependencies
echo 6. Install Dev Dependencies
echo 7. Configure Settings
echo.
echo 8. Run Quality Checks
echo 9. Run Tests
echo A. Generate Screenshots
echo.
echo B. Open Logs
echo C. Open Documentation
echo.
echo 0. Exit
echo.
set /p choice="Select an option (0-C): "

if "%choice%"=="1" goto start_cli
if "%choice%"=="2" goto start_gradio
if "%choice%"=="3" goto start_demo
if "%choice%"=="4" goto stop_app
if "%choice%"=="5" goto install_deps
if "%choice%"=="6" goto install_dev
if "%choice%"=="7" goto configure
if "%choice%"=="8" goto quality_check
if "%choice%"=="9" goto run_tests
if "%choice%"=="A" goto gen_screenshots
if "%choice%"=="B" goto open_logs
if "%choice%"=="C" goto open_docs
if "%choice%"=="0" goto end
if "%choice%"=="a" goto gen_screenshots
if "%choice%"=="b" goto open_logs
if "%choice%"=="c" goto open_docs

echo.
echo ❌ Invalid option. Please try again.
timeout /t 2 /nobreak
goto main_menu

:start_cli
cls
echo.
echo 🚀 Starting HearthNet (CLI Mode)...
echo.
python -m hearthnet.cli run
goto pause_and_menu

:start_gradio
cls
echo.
echo 🚀 Starting HearthNet (Gradio Web UI)...
echo Opening http://localhost:7860 in your browser...
echo.
timeout /t 2 /nobreak
start http://localhost:7860 2>nul
python app.py
goto pause_and_menu

:start_demo
cls
echo.
echo 🚀 Starting Multi-Node Demo (2 nodes)...
echo.
python scripts\demo_two_nodes.py
goto pause_and_menu

:stop_app
cls
echo.
echo 🛑 Stopping HearthNet processes...
taskkill /F /IM python.exe /T 2>nul
if %errorlevel%==0 (
    echo ✅ HearthNet processes stopped.
) else (
    echo ℹ️  No HearthNet processes running.
)
timeout /t 2 /nobreak
goto main_menu

:install_deps
cls
echo.
echo 📦 Installing dependencies...
echo.
pip install -e .
if %errorlevel%==0 (
    echo.
    echo ✅ Dependencies installed successfully!
) else (
    echo.
    echo ❌ Failed to install dependencies.
)
timeout /t 3 /nobreak
goto main_menu

:install_dev
cls
echo.
echo 📦 Installing dev dependencies...
echo.
pip install -r requirements-dev.txt
if %errorlevel%==0 (
    echo.
    echo ✅ Dev dependencies installed successfully!
) else (
    echo.
    echo ❌ Failed to install dev dependencies.
)
timeout /t 3 /nobreak
goto main_menu

:configure
cls
echo.
echo ⚙️  Configuration Options
echo.
echo 1. Edit .env file
echo 2. Edit pyproject.toml
echo 3. View current config
echo 4. Reset to defaults
echo.
set /p config_choice="Select an option (1-4): "

if "%config_choice%"=="1" (
    if exist ".env" (
        notepad .env
    ) else (
        echo. > .env
        echo ℹ️  Created .env file. Please add your configuration.
        timeout /t 2 /nobreak
        notepad .env
    )
)
if "%config_choice%"=="2" notepad pyproject.toml
if "%config_choice%"=="3" type pyproject.toml | more
if "%config_choice%"=="4" (
    echo ℹ️  Resetting to defaults would require re-cloning the repo.
    timeout /t 2 /nobreak
)

goto main_menu

:quality_check
cls
echo.
echo 🔍 Running Quality Checks...
echo.
python scripts\check_quality.py
echo.
timeout /t 3 /nobreak
goto main_menu

:run_tests
cls
echo.
echo 🧪 Running Tests...
echo.
set /p test_choice="Run (1) All tests or (2) Specific test? "
if "%test_choice%"=="1" (
    pytest tests/ -v
) else if "%test_choice%"=="2" (
    echo.
    echo Available tests:
    dir /B tests\test_*.py
    echo.
    set /p test_file="Enter test file (e.g., test_e2e_user_stories.py): "
    pytest tests\!test_file! -v
)
echo.
timeout /t 3 /nobreak
goto main_menu

:gen_screenshots
cls
echo.
echo 📸 Generating Screenshots...
echo.
python scripts\gen_screenshots.py
if %errorlevel%==0 (
    echo.
    echo ✅ Screenshots generated!
    echo 📁 Location: docs\screenshots\
) else (
    echo.
    echo ⚠️  Screenshot generation completed with warnings.
)
timeout /t 3 /nobreak
goto main_menu

:open_logs
cls
echo.
echo 📋 Opening Logs...
echo.
if exist "logs" (
    explorer logs
) else (
    echo ℹ️  No logs directory found.
    timeout /t 2 /nobreak
)
goto main_menu

:open_docs
cls
echo.
echo 📚 Opening Documentation...
echo.
set /p doc_choice="Open (1) README or (2) HOWTO? "
if "%doc_choice%"=="1" start notepad README.md
if "%doc_choice%"=="2" start notepad docs\HOWTO.md
timeout /t 1 /nobreak
goto main_menu

:pause_and_menu
echo.
pause
goto main_menu

:end
cls
echo.
echo 👋 Goodbye!
echo.
endlocal
exit /b 0
