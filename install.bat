@echo off
setlocal

echo.
echo   installing joe goldberg...
echo.

SET INSTALL_DIR=%~dp0

REM Python deps
pip install -e . --quiet
pip install sherlock-project maigret --quiet

REM Ollama
where ollama >nul 2>&1
if %errorlevel% neq 0 (
    echo   ollama not found.
    echo   download from: https://ollama.com/download/windows
    echo   install it then re-run this script.
    pause
    exit /b 1
)

REM Pull model
ollama list | findstr "llama3.2:3b" >nul 2>&1
if %errorlevel% neq 0 (
    echo   pulling llama3.2:3b...
    ollama pull llama3.2:3b
)

REM System command wrapper
echo @echo off > "%INSTALL_DIR%joe.bat"
echo cd /d "%INSTALL_DIR%" >> "%INSTALL_DIR%joe.bat"
echo python "%INSTALL_DIR%joe.py" %%* >> "%INSTALL_DIR%joe.bat"

REM Add to PATH if not already there
echo %PATH% | findstr /i "%INSTALL_DIR%" >nul 2>&1
if %errorlevel% neq 0 (
    setx PATH "%PATH%;%INSTALL_DIR%" /M >nul 2>&1
)

REM Start Menu shortcut
set SHORTCUT_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs
powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%SHORTCUT_DIR%\Joe Goldberg.lnk'); $s.TargetPath = 'python'; $s.Arguments = '%INSTALL_DIR%joe.py'; $s.IconLocation = '%INSTALL_DIR%assets\joe.jpeg'; $s.WorkingDirectory = '%INSTALL_DIR%'; $s.Save()" 2>nul

echo.
echo   done.
echo   joe is registered as a system command — open a new terminal and run: joe
echo   Joe Goldberg shortcut added to Start Menu
echo.
echo   set your Gemini API key for fast narration:
echo   (free key at https://aistudio.google.com/apikey)
echo.
echo   setx GEMINI_API_KEY "your_key_here"
echo.
pause