@echo off
setlocal enabledelayedexpansion

:: ============================================================
::  NeuroX v9.4 - One-Click Run
::  1. Pull latest code from GitHub
::  2. Compile EA + copy to MT5
::  3. Launch NeuroX v9 with watchdog (auto-restart on crash)
:: ============================================================

title NeuroX v9.4 - Pure Momentum Scalper
color 0B
SET PYTHONUNBUFFERED=1
SET PYTHONIOENCODING=utf-8

echo ============================================================
echo   NeuroX v9.4 - Pure Momentum HF Scalper
echo   One-Click: Pull + Compile + Run
echo ============================================================
echo.

:: ══════════════════════════════════════════════════════════════
:: CONFIGURATION
:: ══════════════════════════════════════════════════════════════
set "REPO_DIR=%~dp0"
if "!REPO_DIR:~-1!"=="\" set "REPO_DIR=!REPO_DIR:~0,-1!"
set "WORKING_DIR=%REPO_DIR%"
set "MAX_RESTARTS=10"
set "RESTART_DELAY=5"

:: MT5 Terminal: EA runs here
set "MT5_TERMINAL_ID=930119AA53207C8778B41171FBFFB46F"
set "MT5_BASE=C:\Users\gagan\AppData\Roaming\MetaQuotes\Terminal\%MT5_TERMINAL_ID%"
set "MT5_EXPERTS=%MT5_BASE%\MQL5\Experts\Advisors"
set "MT5_INCLUDE=%MT5_BASE%\MQL5\Include\NeuroX"

:: MetaEditor include resolution terminal (copy includes here too)
set "MT5_EDITOR_ID=D0E8209F77C8CF37AD8BF550E51FF075"
set "MT5_EDITOR_BASE=C:\Users\gagan\AppData\Roaming\MetaQuotes\Terminal\%MT5_EDITOR_ID%"
set "MT5_EDITOR_INCLUDE=%MT5_EDITOR_BASE%\MQL5\Include\NeuroX"

:: ══════════════════════════════════════════════════════════════
:: STEP 1: Pull Latest Code from GitHub
:: ══════════════════════════════════════════════════════════════
echo [1/3] Pulling latest code...
echo.

cd /d "%REPO_DIR%"
git fetch origin main >nul 2>&1
git reset --hard origin/main >nul 2>&1

if !ERRORLEVEL! equ 0 (
    echo        [OK] Code updated to latest.
) else (
    echo        [WARNING] Git pull failed. Continuing with local files.
)
echo.

:: ══════════════════════════════════════════════════════════════
:: STEP 2: Compile EA + Copy to MT5
:: ══════════════════════════════════════════════════════════════
echo [2/3] Compiling NeuroX v9.4 EA...
echo.

set "EA_SOURCE=%REPO_DIR%\NeuroX_EA_v9.mq5"
set "METAEDITOR="

:: Find MetaEditor
for %%P in (
    "C:\Program Files\Fusion Markets MetaTrader 5\metaeditor64.exe"
    "C:\Program Files (x86)\Fusion Markets MetaTrader 5\metaeditor64.exe"
    "C:\Program Files\MetaTrader 5\metaeditor64.exe"
) do (
    if exist %%P set "METAEDITOR=%%~P"
)

if not exist "%EA_SOURCE%" (
    echo        [WARNING] NeuroX_EA_v9.mq5 not found. Skipping compile.
    goto :launch_neurox
)

:: Create directories
if not exist "%MT5_EXPERTS%" mkdir "%MT5_EXPERTS%"
if not exist "%MT5_INCLUDE%" mkdir "%MT5_INCLUDE%"

:: Copy EA to MT5
copy /Y "%EA_SOURCE%" "%MT5_EXPERTS%\" >nul 2>&1
echo        [OK] EA copied to: %MT5_EXPERTS%

:: Copy includes to EA terminal
if exist "%REPO_DIR%\Include\*.mqh" (
    copy /Y "%REPO_DIR%\Include\*.mqh" "%MT5_INCLUDE%\" >nul 2>&1
    echo        [OK] Includes copied to: %MT5_INCLUDE%
)

:: Copy includes to MetaEditor resolution terminal
if not exist "%MT5_EDITOR_INCLUDE%" mkdir "%MT5_EDITOR_INCLUDE%"
if exist "%REPO_DIR%\Include\*.mqh" (
    copy /Y "%REPO_DIR%\Include\*.mqh" "%MT5_EDITOR_INCLUDE%\" >nul 2>&1
    echo        [OK] Includes copied to: %MT5_EDITOR_INCLUDE% (MetaEditor)
)

:: Compile if MetaEditor available
if defined METAEDITOR (
    set "COMPILE_TARGET=%MT5_EXPERTS%\NeuroX_EA_v9.mq5"
    echo        Compiling: !COMPILE_TARGET!
    "%METAEDITOR%" /compile:"!COMPILE_TARGET!" /log
    timeout /t 8 /nobreak >nul

    set "LOG_FILE=%MT5_EXPERTS%\NeuroX_EA_v9.log"
    if exist "!LOG_FILE!" (
        findstr /i " error " "!LOG_FILE!" >nul
        if !errorlevel! equ 0 (
            echo        [WARNING] Compilation has errors.
        ) else (
            echo        [OK] EA compiled successfully.
        )
    )
) else (
    echo        [INFO] MetaEditor not found. Compile manually.
)
echo.

:: ══════════════════════════════════════════════════════════════
:: STEP 3: Launch NeuroX v9.0 with Watchdog
:: ══════════════════════════════════════════════════════════════
:launch_neurox

echo [3/3] Launching NeuroX v9.4...
echo.
echo ============================================================
echo   NeuroX v9.4 - Live Trading Mode
echo   Pure Momentum - 4-Tier Trailing - Fixed 0.10 Lot
echo   Watchdog: auto-restart on crash (max %MAX_RESTARTS% restarts)
echo ============================================================
echo.

cd /d "%WORKING_DIR%"
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Cannot access: %WORKING_DIR%
    pause
    exit /b 1
)

:: Watchdog loop
set "RESTART_COUNT=0"

:watchdog_loop

if !RESTART_COUNT! geq %MAX_RESTARTS% goto :max_restarts

if !RESTART_COUNT! gtr 0 (
    echo.
    echo [WATCHDOG] Restart !RESTART_COUNT!/%MAX_RESTARTS% in %RESTART_DELAY%s...
    timeout /t %RESTART_DELAY% /nobreak >nul
)

:: Run NeuroX v9.0
python -u main.py

:: If clean exit (code 0), don't restart
if !ERRORLEVEL! equ 0 goto :end

:: Crashed - increment counter and retry
set /a RESTART_COUNT+=1
goto :watchdog_loop

:max_restarts
echo.
echo [ERROR] Max restarts reached (%MAX_RESTARTS%). Stopping.
pause
exit /b 1

:end
echo.
echo [OK] NeuroX v9.4 session ended.
pause
