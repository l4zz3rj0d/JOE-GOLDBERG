@echo off
echo.
echo   installing joe...
echo.

pip install -e . --quiet
pip install sherlock-project maigret --quiet

where ollama >nul 2>&1
if %errorlevel% neq 0 (
    echo   install ollama from: https://ollama.com/download/windows
    echo   then re-run this script.
    pause
    exit /b 1
)

ollama list 2>nul | findstr /i "mistral" >nul 2>&1
if %errorlevel% equ 0 (
    echo   mistral already downloaded — skipping.
) else (
    echo   pulling mistral:7b-instruct...
    ollama pull mistral:7b-instruct
)

echo.
echo   done. run: joe
echo.