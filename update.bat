@echo off
setlocal enabledelayedexpansion

:: ------------------------------------------------------------
::  NeuroX v9.4 - Clean Update Script
::  1. Clean download: replace ALL files from GitHub
::  2. Copy EA + includes to MT5 terminals
::  3. Compile EA
:: ------------------------------------------------------------

title NeuroX v9.4 - Clean Update
color 0B

echo.
echo ============================================================
echo   NeuroX v9.4 - Clean Update
echo   Full download from GitHub (replaces all files)
echo ============================================================
echo.

:: ------------------------------------------------------------
:: CONFIGURATION
:: ------------------------------------------------------------
set "REPO_DIR=%~dp0"
if "!REPO_DIR:~-1!"=="\" set "REPO_DIR=!REPO_DIR:~0,-1!"
set "EA_FILE=NeuroX_EA_v9.mq5"
set "BRANCH=main"
set "REPO_URL=https://github.com/gagandocx/NeuroX-v9.git"

:: MT5 Terminal: EA runs here
set "MT5_TERMINAL_ID=930119AA53207C8778B41171FBFFB46F"
set "MT5_BASE=C:\Users\gagan\AppData\Roaming\MetaQuotes\Terminal\%MT5_TERMINAL_ID%"
set "MT5_EXPERTS=%MT5_BASE%\MQL5\Experts\Advisors"
set "MT5_INCLUDE=%MT5_BASE%\MQL5\Include\NeuroX"

:: MetaEditor include resolution terminal (copy includes here too)
set "MT5_EDITOR_ID=D0E8209F77C8CF37AD8BF550E51FF075"
set "MT5_EDITOR_BASE=C:\Users\gagan\AppData\Roaming\MetaQuotes\Terminal\%MT5_EDITOR_ID%"
set "MT5_EDITOR_INCLUDE=%MT5_EDITOR_BASE%\MQL5\Include\NeuroX"

:: Find MetaEditor
set "METAEDITOR="
for %%P in (
    "C:\Program Files\Fusion Markets MetaTrader 5\metaeditor64.exe"
    "C:\Program Files (x86)\Fusion Markets MetaTrader 5\metaeditor64.exe"
    "C:\Program Files\MetaTrader 5\metaeditor64.exe"
) do (
    if exist %%P set "METAEDITOR=%%~P"
)

:: ------------------------------------------------------------
:: STEP 1: Clean Download from GitHub
:: ------------------------------------------------------------
echo [1/3] Downloading latest version from GitHub...
echo        Branch: %BRANCH%
echo.

cd /d "%REPO_DIR%"

:: Check if this is a git repository
if not exist "%REPO_DIR%\.git" (
    echo        [INFO] No git repository found. Cloning fresh...
    for %%I in ("%REPO_DIR%") do set "PARENT_DIR=%%~dpI"
    if "!PARENT_DIR:~-1!"=="\" set "PARENT_DIR=!PARENT_DIR:~0,-1!"
    cd /d "!PARENT_DIR!"
    git clone --depth 1 --branch %BRANCH% "%REPO_URL%" "%REPO_DIR%" >nul 2>&1
    if !ERRORLEVEL! neq 0 (
        echo        [ERROR] Failed to clone from GitHub. Check internet connection.
        goto :error_exit
    )
    cd /d "%REPO_DIR%"
    echo        [OK] Fresh clone complete.
    goto :step2
)

:: Fetch latest from remote (handle shallow clones)
git fetch --depth 1 origin %BRANCH% >nul 2>&1
if !ERRORLEVEL! neq 0 (
    echo        [INFO] Shallow fetch failed, trying unshallow...
    git fetch --unshallow origin >nul 2>&1
    if !ERRORLEVEL! neq 0 (
        echo        [ERROR] Failed to fetch from GitHub. Check internet connection.
        goto :error_exit
    )
    git fetch origin %BRANCH% >nul 2>&1
    if !ERRORLEVEL! neq 0 (
        echo        [ERROR] Failed to fetch branch after unshallow. Check internet connection.
        goto :error_exit
    )
)

:: Reset all tracked files to match remote exactly
git reset --hard origin/%BRANCH% >nul 2>&1
if !ERRORLEVEL! neq 0 (
    echo        [ERROR] Failed to reset files. Repository may be corrupted.
    goto :error_exit
)

:: Remove ALL untracked and ignored files (clean download)
:: This ensures no stale/deleted files linger from old versions
:: Exclude .env to protect local environment configuration
git clean -fdx --exclude=.env >nul 2>&1

echo        [OK] All files replaced with latest from GitHub.
echo        No stale files remaining.
echo.

:: ------------------------------------------------------------
:: STEP 2: Copy EA + Includes to MT5
:: ------------------------------------------------------------
:step2
echo [2/3] Copying files to MT5 terminals...
echo.

set "EA_SOURCE=%REPO_DIR%\%EA_FILE%"

if not exist "%EA_SOURCE%" (
    echo        [WARNING] %EA_FILE% not found. Skipping copy.
    goto :skip_copy
)

:: Create directories
if not exist "%MT5_EXPERTS%" mkdir "%MT5_EXPERTS%"
if not exist "%MT5_INCLUDE%" mkdir "%MT5_INCLUDE%"
if not exist "%MT5_EDITOR_INCLUDE%" mkdir "%MT5_EDITOR_INCLUDE%"

:: Copy EA to MT5
copy /Y "%EA_SOURCE%" "%MT5_EXPERTS%\" >nul 2>&1
echo        [OK] EA copied to: %MT5_EXPERTS%

:: Copy includes to EA terminal
if exist "%REPO_DIR%\Include\*.mqh" (
    copy /Y "%REPO_DIR%\Include\*.mqh" "%MT5_INCLUDE%\" >nul 2>&1
    echo        [OK] Includes copied to: %MT5_INCLUDE%
)

:: Copy includes to MetaEditor resolution terminal
if exist "%REPO_DIR%\Include\*.mqh" (
    copy /Y "%REPO_DIR%\Include\*.mqh" "%MT5_EDITOR_INCLUDE%\" >nul 2>&1
    echo        [OK] Includes copied to: %MT5_EDITOR_INCLUDE% (MetaEditor)
)

:skip_copy
echo.

:: ------------------------------------------------------------
:: STEP 3: Compile EA
:: ------------------------------------------------------------
echo [3/3] Compiling...
echo.

if not defined METAEDITOR (
    echo        [INFO] MetaEditor not found. Open MetaEditor and press F7 to compile manually.
    goto :done
)

if not exist "%MT5_EXPERTS%\%EA_FILE%" (
    echo        [WARNING] EA not in Experts folder. Skipping compile.
    goto :done
)

set "COMPILE_TARGET=%MT5_EXPERTS%\%EA_FILE%"
echo        Compiling: !COMPILE_TARGET!
"%METAEDITOR%" /compile:"!COMPILE_TARGET!" /log >nul 2>&1
timeout /t 8 /nobreak >nul

set "LOG_FILE=%MT5_EXPERTS%\NeuroX_EA_v9.log"
if exist "!LOG_FILE!" (
    findstr /i " error " "!LOG_FILE!" >nul
    if !errorlevel! equ 0 (
        echo        [WARNING] Compilation has errors. Check log.
    ) else (
        echo        [OK] EA compiled successfully.
    )
) else (
    echo        [OK] Compile complete.
)

:done
echo.
echo ============================================================
echo   Update Complete!
echo   All files replaced with latest v9.4 from GitHub.
echo   Attach EA to chart and trade.
echo ============================================================
echo.
pause
exit /b 0

:error_exit
echo.
echo ============================================================
echo   Update Failed! Check errors above.
echo ============================================================
echo.
pause
exit /b 1
