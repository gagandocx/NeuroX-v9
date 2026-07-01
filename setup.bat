@echo off
setlocal enabledelayedexpansion

:: ============================================================
::  NeuroX v9.4 - COMPLETE Fresh PC Setup (Single File)
::  Download this ONE file and double-click. It does everything:
::    1. Auto-elevates to Administrator
::    2. Installs Git (via winget or direct download)
::    3. Installs Python 3.12 (via winget or direct download)
::    4. Downloads NeuroX v9 repo via ZIP (no git needed)
::    5. Installs Python packages (numpy, pandas, pytest)
::    6. Copies EA + Include files to MT5 terminals
::    7. Compiles EA if MetaEditor found
::    8. Verifies everything works
:: ============================================================

:: ============================================================
:: SELF-ELEVATE TO ADMIN (required for silent installs)
:: ============================================================
net session >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo Requesting Administrator privileges...
    echo Set UAC = CreateObject^("Shell.Application"^) > "%TEMP%\neurox_getadmin.vbs"
    echo UAC.ShellExecute "%~f0", "", "", "runas", 1 >> "%TEMP%\neurox_getadmin.vbs"
    "%TEMP%\neurox_getadmin.vbs"
    del "%TEMP%\neurox_getadmin.vbs"
    exit /b
)

:: Ensure working directory is the script's location (admin elevation changes cwd to System32)
cd /d "%~dp0"

title NeuroX v9.4 - Fresh PC Setup (Administrator)
color 0B

echo.
echo ============================================================
echo   NeuroX v9.4 - COMPLETE Fresh PC Setup
echo   Running as Administrator - All installs will work
echo ============================================================
echo.
echo   This script will install and configure:
echo     [1] Git (for version control)
echo     [2] Python 3.12 (for trading logic)
echo     [3] NeuroX v9 repository (via ZIP download)
echo     [4] Python packages: numpy, pandas, pytest
echo     [5] Copy EA + includes to MetaTrader 5
echo     [6] Compile EA (if MetaEditor found)
echo     [7] Verify everything
echo.
echo   Target: F:\Automation\EA Testing\NeuroX\NeuroX v9.0
echo.
echo ============================================================
echo.

:: ============================================================
:: CONFIGURATION
:: ============================================================
set "INSTALL_DIR=F:\Automation\EA Testing\NeuroX\NeuroX v9.0"
set "ZIP_URL=https://github.com/gagandocx/NeuroX-v9/archive/refs/heads/main.zip"
set "ZIP_FILE=%TEMP%\neurox_setup_repo.zip"
set "ZIP_EXTRACT=%TEMP%\neurox_setup_extract"
set "TEMP_DIR=%TEMP%\neurox_setup"

:: MT5 Terminal: EA runs here
set "MT5_TERMINAL_ID=930119AA53207C8778B41171FBFFB46F"
set "MT5_BASE=C:\Users\gagan\AppData\Roaming\MetaQuotes\Terminal\%MT5_TERMINAL_ID%"
set "MT5_EXPERTS=%MT5_BASE%\MQL5\Experts\Advisors"
set "MT5_INCLUDE=%MT5_BASE%\MQL5\Include\NeuroX"

:: MetaEditor include resolution terminal
set "MT5_EDITOR_ID=D0E8209F77C8CF37AD8BF550E51FF075"
set "MT5_EDITOR_BASE=C:\Users\gagan\AppData\Roaming\MetaQuotes\Terminal\%MT5_EDITOR_ID%"
set "MT5_EDITOR_INCLUDE=%MT5_EDITOR_BASE%\MQL5\Include\NeuroX"

:: Create temp directory
if not exist "%TEMP_DIR%" mkdir "%TEMP_DIR%"


:: ============================================================
:: STEP 1: INSTALL GIT
:: ============================================================
echo [1/7] Installing Git...
echo.

:: Force verify Git actually works (not just exists in PATH)
set "GIT_WORKS=0"
where git >nul 2>&1
if %ERRORLEVEL% equ 0 (
    git --version >nul 2>&1
    if !ERRORLEVEL! equ 0 (
        for /f "tokens=*" %%v in ('git --version') do echo        [OK] %%v already working.
        set "GIT_WORKS=1"
    )
)

if "!GIT_WORKS!"=="1" goto :git_done

echo        Git not working. Force installing...
echo.

:: Try winget first
where winget >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo        [INFO] Installing Git via winget...
    winget install --id Git.Git -e --silent --accept-package-agreements --accept-source-agreements
    if !ERRORLEVEL! equ 0 (
        echo        [OK] Git installed via winget.
        goto :git_refresh_path
    )
    echo        [INFO] winget failed. Trying direct download...
)

:: Direct download fallback
echo        [INFO] Downloading Git installer directly...
set "GIT_INSTALLER=%TEMP_DIR%\git-installer.exe"
powershell -NoProfile -ExecutionPolicy Bypass -Command "& { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; try { $rel = Invoke-RestMethod -Uri 'https://api.github.com/repos/git-for-windows/git/releases/latest'; $url = ($rel.assets | Where-Object { $_.name -match '64-bit.exe$' -and $_.name -match '^Git-' } | Select-Object -First 1).browser_download_url; if (-not $url) { $url = 'https://github.com/git-for-windows/git/releases/download/v2.47.1.windows.1/Git-2.47.1-64-bit.exe' }; Write-Host \"Downloading: $url\"; Invoke-WebRequest -Uri $url -OutFile '%GIT_INSTALLER%' -UseBasicParsing; exit 0 } catch { Write-Host $_.Exception.Message; exit 1 } }"

if not exist "%GIT_INSTALLER%" (
    echo        [WARNING] Failed to download Git. Will continue without it.
    echo        (Repo will be downloaded via ZIP instead)
    goto :git_done
)

echo        [INFO] Running Git installer (silent)...
start "" /wait "%GIT_INSTALLER%" /VERYSILENT /NORESTART /NOCANCEL /SP- /CLOSEAPPLICATIONS /RESTARTAPPLICATIONS /COMPONENTS="icons,ext\reg\shellhere,assoc,assoc_sh"

if !ERRORLEVEL! neq 0 (
    echo        [WARNING] Git installer returned error. Continuing anyway.
)

:git_refresh_path
:: Force refresh PATH to include Git
set "PATH=%PATH%;C:\Program Files\Git\bin;C:\Program Files\Git\cmd"
for /f "tokens=2*" %%a in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path 2^>nul') do set "SYS_PATH=%%b"
for /f "tokens=2*" %%a in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "USR_PATH=%%b"
if defined SYS_PATH set "PATH=!SYS_PATH!;!USR_PATH!;%PATH%"

where git >nul 2>&1
if %ERRORLEVEL% equ 0 (
    for /f "tokens=*" %%v in ('git --version') do echo        [OK] Installed: %%v
) else (
    echo        [INFO] Git installed but PATH not refreshed. Not a problem - using ZIP download.
)

:git_done
echo.


:: ============================================================
:: STEP 2: INSTALL PYTHON
:: ============================================================
echo [2/7] Installing Python 3.12...
echo.

:: Force verify Python actually works
set "PYTHON_WORKS=0"
set "PYTHON_CMD="
where python >nul 2>&1
if %ERRORLEVEL% equ 0 (
    python --version >nul 2>&1
    if !ERRORLEVEL! equ 0 (
        for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo        [OK] %%v already working.
        set "PYTHON_WORKS=1"
        set "PYTHON_CMD=python"
    )
)

if "!PYTHON_WORKS!"=="0" (
    where py >nul 2>&1
    if !ERRORLEVEL! equ 0 (
        py --version >nul 2>&1
        if !ERRORLEVEL! equ 0 (
            for /f "tokens=*" %%v in ('py --version 2^>^&1') do echo        [OK] %%v already working (py launcher).
            set "PYTHON_WORKS=1"
            set "PYTHON_CMD=py"
        )
    )
)

if "!PYTHON_WORKS!"=="1" goto :python_done

echo        Python not working. Force installing...
echo.

:: Try winget first
where winget >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo        [INFO] Installing Python 3.12 via winget...
    winget install --id Python.Python.3.12 -e --silent --accept-package-agreements --accept-source-agreements
    if !ERRORLEVEL! equ 0 (
        echo        [OK] Python installed via winget.
        goto :python_refresh_path
    )
    echo        [INFO] winget failed. Trying direct download...
)

:: Direct download fallback
echo        [INFO] Downloading Python 3.12 installer...
set "PYTHON_INSTALLER=%TEMP_DIR%\python-installer.exe"
set "PYTHON_URL=https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe"
powershell -NoProfile -ExecutionPolicy Bypass -Command "& { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; try { Invoke-WebRequest -Uri '%PYTHON_URL%' -OutFile '%PYTHON_INSTALLER%' -UseBasicParsing; exit 0 } catch { Write-Host $_.Exception.Message; exit 1 } }"

if not exist "%PYTHON_INSTALLER%" (
    echo        [ERROR] Failed to download Python installer.
    echo        Please install manually from: https://www.python.org/downloads/
    echo.
    pause
    goto :python_done
)

echo        [INFO] Running Python installer (silent, all users, add to PATH)...
start "" /wait "%PYTHON_INSTALLER%" /quiet InstallAllUsers=1 PrependPath=1 Include_test=0 Include_launcher=1
if !ERRORLEVEL! neq 0 (
    echo        [WARNING] Python installer returned error code. Continuing...
)

echo        [OK] Python installer completed.

:python_refresh_path
:: Force refresh PATH for Python
set "PATH=%PATH%;C:\Program Files\Python312;C:\Program Files\Python312\Scripts"
set "PATH=%PATH%;C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python312;C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python312\Scripts"
set "PATH=%PATH%;%LOCALAPPDATA%\Programs\Python\Python312;%LOCALAPPDATA%\Programs\Python\Python312\Scripts"
for /f "tokens=2*" %%a in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path 2^>nul') do set "SYS_PATH=%%b"
for /f "tokens=2*" %%a in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "USR_PATH=%%b"
if defined SYS_PATH set "PATH=!SYS_PATH!;!USR_PATH!;%PATH%"

:: Determine which python command works
set "PYTHON_CMD="
where python >nul 2>&1
if %ERRORLEVEL% equ 0 (
    set "PYTHON_CMD=python"
    for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo        [OK] Verified: %%v
) else (
    where py >nul 2>&1
    if !ERRORLEVEL! equ 0 (
        set "PYTHON_CMD=py"
        for /f "tokens=*" %%v in ('py --version 2^>^&1') do echo        [OK] Verified: %%v (py launcher)
    ) else (
        echo        [WARNING] Python installed but not in PATH yet.
        echo        Will try standard locations for pip install step.
        set "PYTHON_CMD=C:\Program Files\Python312\python.exe"
    )
)

:python_done
echo.


:: ============================================================
:: STEP 3: DOWNLOAD NEUROX v9 REPOSITORY (via ZIP - no git needed)
:: ============================================================
echo [3/7] Downloading NeuroX v9 repository...
echo        Target: %INSTALL_DIR%
echo        Source: %ZIP_URL%
echo.

:: Create target directory
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"

:: Clean up any previous temp files
if exist "%ZIP_FILE%" del /f /q "%ZIP_FILE%" >nul 2>&1
if exist "%ZIP_EXTRACT%" rd /s /q "%ZIP_EXTRACT%" >nul 2>&1

:: Download ZIP using PowerShell (works on any Windows 10+ PC, no git needed)
echo        Downloading ZIP from GitHub...
powershell -NoProfile -ExecutionPolicy Bypass -Command "& { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; try { Invoke-WebRequest -Uri '%ZIP_URL%' -OutFile '%ZIP_FILE%' -UseBasicParsing; Write-Host 'Download complete.'; exit 0 } catch { Write-Host \"ERROR: $($_.Exception.Message)\"; exit 1 } }"

if !ERRORLEVEL! neq 0 (
    echo        [ERROR] Failed to download repository ZIP.
    echo        Check your internet connection and try again.
    echo.
    pause
    goto :repo_done
)

if not exist "%ZIP_FILE%" (
    echo        [ERROR] ZIP file not found after download.
    echo.
    pause
    goto :repo_done
)

echo        [OK] ZIP downloaded.

:: Extract ZIP
echo        Extracting...
powershell -NoProfile -ExecutionPolicy Bypass -Command "& { try { Expand-Archive -Path '%ZIP_FILE%' -DestinationPath '%ZIP_EXTRACT%' -Force; exit 0 } catch { Write-Host $_.Exception.Message; exit 1 } }"

if !ERRORLEVEL! neq 0 (
    echo        [ERROR] Failed to extract ZIP.
    echo.
    pause
    goto :repo_done
)

:: Verify extraction
if not exist "%ZIP_EXTRACT%\NeuroX-v9-main" (
    echo        [ERROR] Expected folder 'NeuroX-v9-main' not found in ZIP.
    echo.
    pause
    goto :repo_done
)

echo        [OK] ZIP extracted.

:: Copy all files to target (force overwrite)
echo        Installing files to: %INSTALL_DIR%
robocopy "%ZIP_EXTRACT%\NeuroX-v9-main" "%INSTALL_DIR%" /E /IS /IT /NFL /NDL /NJH /NJS >nul 2>&1
:: Robocopy exit codes 0-7 are success
if !ERRORLEVEL! geq 8 (
    echo        [ERROR] Failed to copy files.
    echo.
    pause
    goto :repo_done
)

echo        [OK] NeuroX v9 installed to: %INSTALL_DIR%

:: Clean up temp files
if exist "%ZIP_FILE%" del /f /q "%ZIP_FILE%" >nul 2>&1
if exist "%ZIP_EXTRACT%" rd /s /q "%ZIP_EXTRACT%" >nul 2>&1

:repo_done
echo.


:: ============================================================
:: STEP 4: INSTALL PYTHON PACKAGES
:: ============================================================
echo [4/7] Installing Python packages (numpy, pandas, pytest)...
echo.

if not defined PYTHON_CMD (
    echo        [ERROR] Python is not available. Cannot install packages.
    echo        Please restart this script after Python installation completes.
    echo.
    pause
    goto :packages_done
)

:: Upgrade pip first
echo        Upgrading pip...
%PYTHON_CMD% -m pip install --upgrade pip >nul 2>&1

:: Install from requirements.txt if it exists in target
set "REQ_FILE=%INSTALL_DIR%\requirements.txt"
if exist "%REQ_FILE%" (
    echo        Installing from requirements.txt...
    %PYTHON_CMD% -m pip install -r "%REQ_FILE%"
    if !ERRORLEVEL! equ 0 (
        echo        [OK] All packages installed from requirements.txt.
    ) else (
        echo        [WARNING] Some packages failed. Trying individually...
        %PYTHON_CMD% -m pip install numpy
        %PYTHON_CMD% -m pip install pandas
        %PYTHON_CMD% -m pip install pytest
    )
) else (
    echo        [INFO] requirements.txt not found. Installing packages directly...
    %PYTHON_CMD% -m pip install numpy pandas pytest
    if !ERRORLEVEL! equ 0 (
        echo        [OK] Packages installed.
    ) else (
        echo        [WARNING] Some packages may have failed.
        echo        Try manually: pip install numpy pandas pytest
    )
)

:packages_done
echo.


:: ============================================================
:: STEP 5: COPY EA + INCLUDES TO MT5 TERMINALS
:: ============================================================
echo [5/7] Copying EA files to MetaTrader 5 terminals...
echo.

set "EA_SOURCE=%INSTALL_DIR%\NeuroX_EA_v9.mq5"
set "STANDALONE_SOURCE=%INSTALL_DIR%\NeuroX_Standalone_v9.mq5"

if not exist "%EA_SOURCE%" (
    echo        [WARNING] NeuroX_EA_v9.mq5 not found in %INSTALL_DIR%
    echo        Skipping MT5 file copy.
    goto :mt5_done
)

:: Create MT5 directories
if not exist "%MT5_EXPERTS%" mkdir "%MT5_EXPERTS%"
if not exist "%MT5_INCLUDE%" mkdir "%MT5_INCLUDE%"
if not exist "%MT5_EDITOR_INCLUDE%" mkdir "%MT5_EDITOR_INCLUDE%"

:: Copy main EA to MT5 Experts
copy /Y "%EA_SOURCE%" "%MT5_EXPERTS%\" >nul 2>&1
if !ERRORLEVEL! equ 0 (
    echo        [OK] NeuroX_EA_v9.mq5 copied to: %MT5_EXPERTS%
) else (
    echo        [WARNING] Failed to copy EA to Experts folder.
)

:: Copy standalone EA if exists
if exist "%STANDALONE_SOURCE%" (
    copy /Y "%STANDALONE_SOURCE%" "%MT5_EXPERTS%\" >nul 2>&1
    if !ERRORLEVEL! equ 0 (
        echo        [OK] NeuroX_Standalone_v9.mq5 copied to: %MT5_EXPERTS%
    )
)

:: Copy all Include (.mqh) files to EA terminal
if exist "%INSTALL_DIR%\Include\*.mqh" (
    copy /Y "%INSTALL_DIR%\Include\*.mqh" "%MT5_INCLUDE%\" >nul 2>&1
    if !ERRORLEVEL! equ 0 (
        echo        [OK] Include files copied to: %MT5_INCLUDE%
    ) else (
        echo        [WARNING] Failed to copy Include files to EA terminal.
    )
) else (
    echo        [INFO] No .mqh files found in Include folder.
)

:: Copy all Include (.mqh) files to MetaEditor resolution terminal
if exist "%INSTALL_DIR%\Include\*.mqh" (
    copy /Y "%INSTALL_DIR%\Include\*.mqh" "%MT5_EDITOR_INCLUDE%\" >nul 2>&1
    if !ERRORLEVEL! equ 0 (
        echo        [OK] Include files copied to: %MT5_EDITOR_INCLUDE% (MetaEditor)
    ) else (
        echo        [WARNING] Failed to copy Include files to MetaEditor terminal.
    )
)

:mt5_done
echo.


:: ============================================================
:: STEP 6: COMPILE EA (if MetaEditor found)
:: ============================================================
echo [6/7] Compiling EA...
echo.

set "METAEDITOR="
for %%P in (
    "C:\Program Files\Fusion Markets MetaTrader 5\metaeditor64.exe"
    "C:\Program Files (x86)\Fusion Markets MetaTrader 5\metaeditor64.exe"
    "C:\Program Files\MetaTrader 5\metaeditor64.exe"
) do (
    if exist %%P set "METAEDITOR=%%~P"
)

if not defined METAEDITOR (
    echo        [INFO] MetaEditor not found.
    echo        Install MetaTrader 5 first, then compile manually (F7 in MetaEditor).
    echo        Or re-run this script after installing MT5.
    goto :compile_done
)

echo        MetaEditor found: %METAEDITOR%

:: Compile main EA
if exist "%MT5_EXPERTS%\NeuroX_EA_v9.mq5" (
    echo        Compiling NeuroX_EA_v9.mq5...
    "%METAEDITOR%" /compile:"%MT5_EXPERTS%\NeuroX_EA_v9.mq5" /log >nul 2>&1
    timeout /t 10 /nobreak >nul

    set "LOG_FILE=%MT5_EXPERTS%\NeuroX_EA_v9.log"
    if exist "!LOG_FILE!" (
        findstr /i " error " "!LOG_FILE!" >nul
        if !errorlevel! equ 0 (
            echo        [WARNING] Compilation has errors. Check MetaEditor.
        ) else (
            echo        [OK] NeuroX_EA_v9.mq5 compiled successfully.
        )
    ) else (
        echo        [OK] Compile command sent.
    )
)

:: Compile standalone EA
if exist "%MT5_EXPERTS%\NeuroX_Standalone_v9.mq5" (
    echo        Compiling NeuroX_Standalone_v9.mq5...
    "%METAEDITOR%" /compile:"%MT5_EXPERTS%\NeuroX_Standalone_v9.mq5" /log >nul 2>&1
    timeout /t 10 /nobreak >nul
    echo        [OK] Standalone EA compile command sent.
)

:compile_done
echo.


:: ============================================================
:: STEP 7: VERIFY EVERYTHING
:: ============================================================
echo [7/7] Verifying installation...
echo.

set "ALL_GOOD=1"
set "PASS_COUNT=0"
set "FAIL_COUNT=0"

:: Check Git
where git >nul 2>&1
if %ERRORLEVEL% equ 0 (
    for /f "tokens=*" %%v in ('git --version') do echo        [PASS] Git: %%v
    set /a PASS_COUNT+=1
) else (
    echo        [FAIL] Git not found in PATH
    set "ALL_GOOD=0"
    set /a FAIL_COUNT+=1
)

:: Check Python
set "PY_VERIFIED=0"
if defined PYTHON_CMD (
    %PYTHON_CMD% --version >nul 2>&1
    if !ERRORLEVEL! equ 0 (
        for /f "tokens=*" %%v in ('%PYTHON_CMD% --version 2^>^&1') do echo        [PASS] Python: %%v
        set "PY_VERIFIED=1"
        set /a PASS_COUNT+=1
    )
)
if "!PY_VERIFIED!"=="0" (
    echo        [FAIL] Python not working
    set "ALL_GOOD=0"
    set /a FAIL_COUNT+=1
)

:: Check Python packages
if defined PYTHON_CMD (
    %PYTHON_CMD% -c "import numpy; print(f'        [PASS] numpy {numpy.__version__}')" 2>nul
    if !ERRORLEVEL! equ 0 (
        set /a PASS_COUNT+=1
    ) else (
        echo        [FAIL] numpy not installed
        set "ALL_GOOD=0"
        set /a FAIL_COUNT+=1
    )
    %PYTHON_CMD% -c "import pandas; print(f'        [PASS] pandas {pandas.__version__}')" 2>nul
    if !ERRORLEVEL! equ 0 (
        set /a PASS_COUNT+=1
    ) else (
        echo        [FAIL] pandas not installed
        set "ALL_GOOD=0"
        set /a FAIL_COUNT+=1
    )
    %PYTHON_CMD% -c "import pytest; print(f'        [PASS] pytest {pytest.__version__}')" 2>nul
    if !ERRORLEVEL! equ 0 (
        set /a PASS_COUNT+=1
    ) else (
        echo        [FAIL] pytest not installed
        set "ALL_GOOD=0"
        set /a FAIL_COUNT+=1
    )
)

:: Check repository files
if exist "%INSTALL_DIR%\main.py" (
    echo        [PASS] NeuroX v9 repository installed
    set /a PASS_COUNT+=1
) else (
    echo        [FAIL] NeuroX v9 repository not found
    set "ALL_GOOD=0"
    set /a FAIL_COUNT+=1
)

:: Check EA file
if exist "%INSTALL_DIR%\NeuroX_EA_v9.mq5" (
    echo        [PASS] NeuroX_EA_v9.mq5 present
    set /a PASS_COUNT+=1
) else (
    echo        [FAIL] NeuroX_EA_v9.mq5 missing
    set "ALL_GOOD=0"
    set /a FAIL_COUNT+=1
)

:: Check Include files
if exist "%INSTALL_DIR%\Include\NeuroX_Types.mqh" (
    echo        [PASS] Include files present (NeuroX_Types.mqh etc.)
    set /a PASS_COUNT+=1
) else (
    echo        [FAIL] Include .mqh files missing
    set "ALL_GOOD=0"
    set /a FAIL_COUNT+=1
)

:: Check Standalone EA
if exist "%INSTALL_DIR%\NeuroX_Standalone_v9.mq5" (
    echo        [PASS] NeuroX_Standalone_v9.mq5 present
    set /a PASS_COUNT+=1
) else (
    echo        [INFO] NeuroX_Standalone_v9.mq5 not found (optional)
)

:: Check MT5 EA was copied
if exist "%MT5_EXPERTS%\NeuroX_EA_v9.mq5" (
    echo        [PASS] EA copied to MT5 terminal
    set /a PASS_COUNT+=1
) else (
    echo        [INFO] EA not in MT5 terminal (MT5 may not be installed yet)
)

:: Check MetaTrader 5
set "MT5_FOUND=0"
for %%P in (
    "C:\Program Files\Fusion Markets MetaTrader 5\terminal64.exe"
    "C:\Program Files (x86)\Fusion Markets MetaTrader 5\terminal64.exe"
    "C:\Program Files\MetaTrader 5\terminal64.exe"
) do (
    if exist %%P set "MT5_FOUND=1"
)
if "!MT5_FOUND!"=="1" (
    echo        [PASS] MetaTrader 5 detected
    set /a PASS_COUNT+=1
) else (
    echo        [INFO] MetaTrader 5 not detected (install separately)
)

:: Check essential Python modules exist
if exist "%INSTALL_DIR%\bridge.py" (
    echo        [PASS] bridge.py (Python-EA communication)
    set /a PASS_COUNT+=1
) else (
    echo        [FAIL] bridge.py missing
    set /a FAIL_COUNT+=1
)

if exist "%INSTALL_DIR%\config.py" (
    echo        [PASS] config.py (configuration)
    set /a PASS_COUNT+=1
) else (
    echo        [FAIL] config.py missing
    set /a FAIL_COUNT+=1
)


echo.
echo ============================================================
echo.

if "!ALL_GOOD!"=="1" (
    color 0A
    echo   SETUP COMPLETE - ALL CHECKS PASSED! (!PASS_COUNT! passed)
    echo.
    echo   Everything is installed and ready.
    echo.
    echo   Location: %INSTALL_DIR%
    echo.
    echo   Files installed:
    echo     - NeuroX_EA_v9.mq5     (main EA with Python bridge)
    echo     - NeuroX_Standalone_v9.mq5 (standalone, no Python needed)
    echo     - Include\*.mqh         (EA modules: Types, Execution, Position, etc.)
    echo     - main.py, bridge.py    (Python trading logic)
    echo     - config.py             (settings)
    echo     - Start.bat             (one-click run)
    echo     - update.bat            (pull latest updates)
    echo.
    echo   NEXT STEPS:
    echo     1. Make sure MetaTrader 5 (Fusion Markets) is installed and running
    echo     2. Open MetaTrader 5 and attach NeuroX_EA_v9 to a chart
    echo     3. To start the Python side: double-click Start.bat
    echo     4. For standalone (no Python): attach NeuroX_Standalone_v9 to chart
    echo.
) else (
    color 0E
    echo   SETUP PARTIALLY COMPLETE (!PASS_COUNT! passed, !FAIL_COUNT! failed)
    echo.
    echo   Some components need attention (see FAIL items above).
    echo   You may need to:
    echo     - Restart your computer to refresh PATH
    echo     - Re-run this script
    echo     - Install MetaTrader 5 manually
    echo.
)

echo ============================================================
echo.
echo   Essential files in this project:
echo   ---------------------------------------------------------------
echo   EA FILES (go in MT5/MQL5/Experts/Advisors/):
echo     NeuroX_EA_v9.mq5           - Main EA (needs Python running)
echo     NeuroX_Standalone_v9.mq5   - Standalone EA (no Python)
echo.
echo   INCLUDE FILES (go in MT5/MQL5/Include/NeuroX/):
echo     NeuroX_Types.mqh           - Types, structs, globals
echo     NeuroX_Execution.mqh       - Order execution engine
echo     NeuroX_Position.mqh        - Position management + trailing
echo     NeuroX_Dashboard.mqh       - On-chart dashboard
echo     NeuroX_Pipe.mqh            - High-speed bridge communication
echo     NeuroX_Reconciliation.mqh  - State recovery on restart
echo.
echo   PYTHON FILES (run via Start.bat):
echo     main.py                    - Entry point
echo     bridge.py                  - EA communication layer
echo     config.py                  - Configuration
echo     momentum.py                - Momentum detection
echo     intelligence.py            - Signal intelligence
echo     performance.py             - Performance tracking
echo     trailing_stop.py           - Trailing stop logic
echo     optimizer.py               - Self-optimization
echo     mtf_confluence.py          - Multi-timeframe confluence
echo     liquidity_sweep.py         - Liquidity sweep detection
echo     tick_frequency.py          - Tick frequency analysis
echo     tick_collector.py          - Tick data collection
echo     cumulative_delta.py        - Cumulative delta
echo     spread_signal.py           - Spread-as-signal
echo     support_resistance.py      - Support/resistance zones
echo     backtest.py                - Backtesting engine
echo.
echo   BATCH FILES:
echo     setup.bat                  - This file (fresh PC setup)
echo     Start.bat                  - One-click run (pull + compile + run)
echo     update.bat                 - Force update from GitHub
echo   ---------------------------------------------------------------
echo.

:: Cleanup temp directory
if exist "%TEMP_DIR%" rd /s /q "%TEMP_DIR%" 2>nul

:: ============================================================
:: NEVER CLOSE WITHOUT USER SEEING RESULTS
:: ============================================================
echo.
echo Press any key to close this window...
pause >nul
exit /b 0
