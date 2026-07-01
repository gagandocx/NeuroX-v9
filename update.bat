@echo off
setlocal enabledelayedexpansion

:: ------------------------------------------------------------
::  NeuroX v9.4 - Force Update Script
::  1. Force download: always downloads latest ZIP from GitHub
::  2. Copy EA + includes to MT5 terminals
::  3. Compile EA
:: ------------------------------------------------------------

title NeuroX v9.4 - Force Update
color 0B

echo.
echo ============================================================
echo   NeuroX v9.4 - Force Update
echo   Always downloads latest from GitHub (replaces all files)
echo ============================================================
echo.

:: ------------------------------------------------------------
:: CONFIGURATION
:: ------------------------------------------------------------
set "REPO_DIR=%~dp0"
if "!REPO_DIR:~-1!"=="\" set "REPO_DIR=!REPO_DIR:~0,-1!"
set "EA_FILE=NeuroX_EA_v9.mq5"
set "ZIP_URL=https://github.com/gagandocx/NeuroX-v9/archive/refs/heads/main.zip"
set "ZIP_FILE=%TEMP%\neurox_update.zip"
set "ZIP_EXTRACT=%TEMP%\neurox_update"

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
:: STEP 1: Force Download ZIP from GitHub
:: ------------------------------------------------------------
echo [1/3] Force downloading latest version from GitHub...
echo        URL: %ZIP_URL%
echo.

cd /d "%REPO_DIR%"

:: Back up .env if it exists
set "ENV_BACKED_UP=0"
if exist "%REPO_DIR%\.env" (
    copy /Y "%REPO_DIR%\.env" "%TEMP%\neurox_env_backup" >nul 2>&1
    if !ERRORLEVEL! equ 0 (
        set "ENV_BACKED_UP=1"
        echo        [OK] .env file backed up.
    )
)

:: Clean up any previous temp files
if exist "%ZIP_FILE%" del /f /q "%ZIP_FILE%" >nul 2>&1
if exist "%ZIP_EXTRACT%" rd /s /q "%ZIP_EXTRACT%" >nul 2>&1

:: Download ZIP using PowerShell
echo        Downloading...
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%ZIP_URL%' -OutFile '%ZIP_FILE%' -UseBasicParsing; exit 0 } catch { Write-Host $_.Exception.Message; exit 1 }"
if !ERRORLEVEL! neq 0 (
    echo        [ERROR] Failed to download ZIP. Check your internet connection.
    goto :error_exit
)

if not exist "%ZIP_FILE%" (
    echo        [ERROR] ZIP file not found after download.
    goto :error_exit
)

echo        [OK] ZIP downloaded successfully.

:: Extract ZIP using PowerShell
echo        Extracting...
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Expand-Archive -Path '%ZIP_FILE%' -DestinationPath '%ZIP_EXTRACT%' -Force; exit 0 } catch { Write-Host $_.Exception.Message; exit 1 }"
if !ERRORLEVEL! neq 0 (
    echo        [ERROR] Failed to extract ZIP file.
    goto :error_exit
)

:: Verify extracted folder exists
if not exist "%ZIP_EXTRACT%\NeuroX-v9-main" (
    echo        [ERROR] Expected folder 'NeuroX-v9-main' not found in ZIP.
    goto :error_exit
)

echo        [OK] ZIP extracted successfully.

:: Copy all files from extracted folder to REPO_DIR (force overwrite)
echo        Copying files (force overwrite)...
robocopy "%ZIP_EXTRACT%\NeuroX-v9-main" "%REPO_DIR%" /E /IS /IT /NFL /NDL /NJH /NJS >nul 2>&1
:: Robocopy exit codes 0-7 are success (various copy scenarios)
if !ERRORLEVEL! geq 8 (
    echo        [ERROR] Failed to copy files from ZIP.
    goto :error_exit
)

echo        [OK] All files replaced with latest from GitHub.

:: Restore .env if it was backed up
if "!ENV_BACKED_UP!"=="1" (
    copy /Y "%TEMP%\neurox_env_backup" "%REPO_DIR%\.env" >nul 2>&1
    echo        [OK] .env file restored.
    del /f /q "%TEMP%\neurox_env_backup" >nul 2>&1
)

:: Clean up temp files
if exist "%ZIP_FILE%" del /f /q "%ZIP_FILE%" >nul 2>&1
if exist "%ZIP_EXTRACT%" rd /s /q "%ZIP_EXTRACT%" >nul 2>&1

echo.

:: ------------------------------------------------------------
:: STEP 2: Copy EA + Includes to MT5
:: ------------------------------------------------------------
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
