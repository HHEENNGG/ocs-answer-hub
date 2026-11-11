@echo off
setlocal enabledelayedexpansion
title Build OCS AnswerHub EXE
cd /d "%~dp0"

echo.
echo   ============================================================
echo      Build a standalone EXE  (dist\OCS-AnswerHub.exe)
echo   ============================================================
echo.

rem ------------------------------------------ 1. pick a usable Python
rem The build interpreter must be able to import flask, otherwise PyInstaller fails.
set "PYCMD="
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import flask, flask_cors, requests" >nul 2>nul
    if not errorlevel 1 set PYCMD=".venv\Scripts\python.exe"
)
if not defined PYCMD (
    where py >nul 2>nul
    if not errorlevel 1 (
        py -3 -c "import flask, flask_cors, requests" >nul 2>nul
        if not errorlevel 1 set PYCMD=py -3
    )
)
if not defined PYCMD (
    where python >nul 2>nul
    if not errorlevel 1 (
        python -c "import flask, flask_cors, requests" >nul 2>nul
        if not errorlevel 1 set PYCMD=python
    )
)

if not defined PYCMD (
    echo   [ERROR] No Python with flask / flask-cors / requests was found.
    echo.
    echo   Run the launcher bat in this folder once first ^(it prepares the
    echo   environment^), or install manually:
    echo       python -m pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

for /f "delims=" %%v in ('!PYCMD! -c "import sys;print(sys.version.split()[0])"') do set "PYVER=%%v"
echo   Python !PYVER!   ^(!PYCMD!^)
echo.

rem ------------------------------------- 2. PyInstaller must be available
!PYCMD! -c "import PyInstaller" >nul 2>nul
if errorlevel 1 (
    echo   [1/2] Installing PyInstaller ...
    !PYCMD! -m pip install --disable-pip-version-check -q -U pyinstaller
    if errorlevel 1 (
        echo   [WARN] Default index failed, retrying with Tsinghua mirror ...
        !PYCMD! -m pip install --disable-pip-version-check -q -U pyinstaller -i https://pypi.tuna.tsinghua.edu.cn/simple
    )
    !PYCMD! -c "import PyInstaller" >nul 2>nul
    if errorlevel 1 (
        echo.
        echo   [ERROR] PyInstaller is still missing. Run manually:
        echo       !PYCMD! -m pip install -U pyinstaller
        echo.
        pause
        exit /b 1
    )
) else (
    echo   [1/2] PyInstaller already installed.
)

rem ------------------------------------------------ 3. build the exe
echo   [2/2] Building, this may take 1~3 minutes ...
echo.
!PYCMD! build_exe.py
set "CODE=%errorlevel%"

echo.
if not "%CODE%"=="0" (
    echo   [ERROR] Build failed with code %CODE%. Read the log above.
    echo.
    pause
    exit /b %CODE%
)

if exist "dist\OCS-AnswerHub.exe" (
    echo   Done. You can double-click:  dist\OCS-AnswerHub.exe
    echo   The data folder is created next to the exe on first run.
) else (
    echo   [ERROR] Build reported success but dist\OCS-AnswerHub.exe is missing.
)
echo.
pause