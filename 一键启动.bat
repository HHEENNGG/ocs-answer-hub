@echo off
setlocal enabledelayedexpansion
title OCS AnswerHub
cd /d "%~dp0"

echo.
echo   ============================================================
echo      OCS AnswerHub  -  local question bank + AI fallback
echo   ============================================================
echo.

rem ------------------------------------------------- 1. find python
set "PYBOOT="
where py >nul 2>nul
if not errorlevel 1 set "PYBOOT=py -3"
if not defined PYBOOT (
    where python >nul 2>nul
    if not errorlevel 1 set "PYBOOT=python"
)
if not defined PYBOOT (
    echo   [ERROR] Python not found.
    echo.
    echo   Please install Python 3.9+ from:
    echo       https://www.python.org/downloads/
    echo   Tick "Add python.exe to PATH" during setup, then run this file again.
    echo.
    pause
    exit /b 1
)

%PYBOOT% -c "import sys" >nul 2>nul
if errorlevel 1 (
    echo   [ERROR] The detected Python cannot run. Please install the official build.
    pause
    exit /b 1
)
for /f "delims=" %%v in ('%PYBOOT% -c "import sys;print(sys.version.split()[0])"') do set "PYVER=%%v"
echo   Python !PYVER!

rem --------------- 2. prefer any python that already has the dependencies
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import flask, flask_cors, requests" >nul 2>nul
    if not errorlevel 1 (
        set PYCMD=".venv\Scripts\python.exe"
        goto :run
    )
)
%PYBOOT% -c "import flask, flask_cors, requests" >nul 2>nul
if not errorlevel 1 (
    set PYCMD=%PYBOOT%
    goto :run
)
where python >nul 2>nul
if not errorlevel 1 (
    python -c "import flask, flask_cors, requests" >nul 2>nul
    if not errorlevel 1 (
        set PYCMD=python
        goto :run
    )
)

rem ------------------------------------------ 3. create / repair a venv
echo   [1/3] Preparing isolated environment .venv ...
if not exist ".venv\Scripts\python.exe" (
    %PYBOOT% -m venv .venv >nul 2>nul
)
if exist ".venv\Scripts\python.exe" (
    set PYCMD=".venv\Scripts\python.exe"
) else (
    echo   [WARN] venv unavailable, falling back to system Python.
    set PYCMD=%PYBOOT%
)

echo   [2/3] Installing dependencies flask / flask-cors / requests ...
!PYCMD! -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 (
    echo   [WARN] Default index failed, retrying with Tsinghua mirror ...
    !PYCMD! -m pip install --disable-pip-version-check -q -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
)
!PYCMD! -c "import flask, flask_cors, requests" >nul 2>nul
if errorlevel 1 (
    echo.
    echo   [ERROR] Dependency installation failed. Check your network and try again.
    echo   Manual command:  !PYCMD! -m pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

rem ------------------------------------------------- 4. start server
:run
echo.
echo   [3/3] Starting server, the browser will open automatically.
echo   First start imports the bundled question banks automatically.
echo   Close this window or press Ctrl+C to stop the service.
echo.
!PYCMD! -m app.main --open-browser
set "CODE=%errorlevel%"

echo.
if not "%CODE%"=="0" (
    echo   [ERROR] Server exited with code %CODE%.
) else (
    echo   Server stopped.
)
echo.
pause