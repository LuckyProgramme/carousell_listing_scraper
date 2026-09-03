@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\deal-finder.exe" (
    ".venv\Scripts\deal-finder.exe"
) else (
    uv run deal-finder
)

set "EXIT_CODE=%ERRORLEVEL%"
echo.
if "%EXIT_CODE%"=="0" (
    echo Deal finder completed successfully.
) else (
    echo Deal finder failed. See logs\deal_finder.log for details.
)
pause
exit /b %EXIT_CODE%
