@echo off
setlocal enabledelayedexpansion

:: ============================================================
::  NeuroX v9 - Fresh PC Setup
::  Automatically installs all dependencies:
::    1. Git (via winget or direct download)
::    2. Python 3.x (via winget or direct download)
::    3. Clone the NeuroX v9 repository
::    4. Install Python packages (numpy, pandas, pytest)
::    5. Verify everything is working
::
::  NOTE: MetaTrader 5 must be installed separately.
::        Run this script as Administrator for best results.
:: ============================================================

title NeuroX v9 - Fresh PC Setup
color 0B

echo.
echo ============================================================
echo   NeuroX v9 - Fresh PC Setup
echo   This will install everything needed to run NeuroX v9
echo ============================================================
echo.
echo   What will be installed:
echo     - Git (for pulling updates)
echo     - Python 3.x (for trading logic)
echo     - Python packages: numpy, pandas, pytest
echo     - NeuroX v9 repository
echo.
echo   NOTE: MetaTrader 5 (Fusion Markets) must be installed
echo         separately if not already present.
echo.
echo ============================================================
echo.

:: Check for admin privileges
net session >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [WARNING] Not running as Administrator.
    echo           Some installations may fail without admin rights.
    echo           Right-click this file and select "Run as administrator"
    echo.
    pause
)

:: Target installation directory
set "INSTALL_DIR=F:\Automation\EA Testing\NeuroX\NeuroX v9.0"
set "REPO_URL=https://github.com/gagandocx/NeuroX-v9.git"
set "BRANCH=main"

:: Temp directory for downloads
set "TEMP_DIR=%TEMP%\neurox_setup"
if not exist "%TEMP_DIR%" mkdir "%TEMP_DIR%"

:: ============================================================
:: STEP 1: Install Git
:: ============================================================
echo [1/5] Checking for Git...
echo.

where git >nul 2>&1
if %ERRORLEVEL% equ 0 (
    for /f "tokens=*" %%v in ('git --version') do echo        [OK] %%v already installed.
    goto :git_done
)

echo        Git not found. Installing...
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
    echo        [WARNING] winget install failed. Trying direct download...
)

:: Direct download fallback
echo        [INFO] Downloading Git installer...
set "GIT_INSTALLER=%TEMP_DIR%\git-installer.exe"
powershell -Command "& { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; $url = (Invoke-RestMethod -Uri 'https://api.github.com/repos/git-for-windows/git/releases/latest').assets | Where-Object { $_.name -match '64-bit.exe$' -and $_.name -match 'Git-' } | Select-Object -First 1 -ExpandProperty browser_download_url; if (-not $url) { $url = 'https://github.com/git-for-windows/git/releases/download/v2.47.1.windows.1/Git-2.47.1-64-bit.exe' }; Write-Host \"Downloading: $url\"; Invoke-WebRequest -Uri $url -OutFile '%GIT_INSTALLER%' -UseBasicParsing }" 2>nul

if not exist "%GIT_INSTALLER%" (
    echo        [ERROR] Failed to download Git installer.
    echo        Please download Git manually from: https://git-scm.com/download/win
    echo.
    pause
    goto :git_done
)

echo        [INFO] Running Git installer (silent)...
"%GIT_INSTALLER%" /VERYSILENT /NORESTART /NOCANCEL /SP- /CLOSEAPPLICATIONS /RESTARTAPPLICATIONS /COMPONENTS="icons,ext\reg\shellhere,assoc,assoc_sh"
if !ERRORLEVEL! neq 0 (
    echo        [ERROR] Git installation failed.
    echo        Please install Git manually from: https://git-scm.com/download/win
    goto :git_done
)

echo        [OK] Git installed successfully.

:git_refresh_path
:: Refresh PATH to pick up new installations
echo        [INFO] Refreshing PATH...
set "PATH=%PATH%;C:\Program Files\Git\bin;C:\Program Files\Git\cmd"

:: Also try to pick up from registry
for /f "tokens=2*" %%a in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path 2^>nul') do set "SYS_PATH=%%b"
for /f "tokens=2*" %%a in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "USR_PATH=%%b"
if defined SYS_PATH set "PATH=!SYS_PATH!;!USR_PATH!;%PATH%"

where git >nul 2>&1
if %ERRORLEVEL% equ 0 (
    for /f "tokens=*" %%v in ('git --version') do echo        [OK] Verified: %%v
) else (
    echo        [WARNING] Git installed but not in PATH yet.
    echo        You may need to restart this script after installation completes.
)

:git_done
echo.

:: ============================================================
:: STEP 2: Install Python
:: ============================================================
echo [2/5] Checking for Python...
echo.

where python >nul 2>&1
if %ERRORLEVEL% equ 0 (
    for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo        [OK] %%v already installed.
    goto :python_done
)

:: Also check py launcher
where py >nul 2>&1
if %ERRORLEVEL% equ 0 (
    for /f "tokens=*" %%v in ('py --version 2^>^&1') do echo        [OK] %%v already installed (py launcher).
    goto :python_done
)

echo        Python not found. Installing...
echo.

:: Try winget first
where winget >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo        [INFO] Installing Python via winget...
    winget install --id Python.Python.3.12 -e --silent --accept-package-agreements --accept-source-agreements
    if !ERRORLEVEL! equ 0 (
        echo        [OK] Python installed via winget.
        goto :python_refresh_path
    )
    echo        [WARNING] winget install failed. Trying direct download...
)

:: Direct download fallback
echo        [INFO] Downloading Python installer...
set "PYTHON_INSTALLER=%TEMP_DIR%\python-installer.exe"
set "PYTHON_URL=https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe"
powershell -Command "& { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%PYTHON_URL%' -OutFile '%PYTHON_INSTALLER%' -UseBasicParsing }" 2>nul

if not exist "%PYTHON_INSTALLER%" (
    echo        [ERROR] Failed to download Python installer.
    echo        Please download Python manually from: https://www.python.org/downloads/
    echo        IMPORTANT: Check "Add Python to PATH" during installation!
    echo.
    pause
    goto :python_done
)

echo        [INFO] Running Python installer (silent)...
"%PYTHON_INSTALLER%" /quiet InstallAllUsers=1 PrependPath=1 Include_test=0 Include_launcher=1
if !ERRORLEVEL! neq 0 (
    echo        [ERROR] Python installation failed.
    echo        Please install Python manually from: https://www.python.org/downloads/
    echo        IMPORTANT: Check "Add Python to PATH" during installation!
    goto :python_done
)

echo        [OK] Python installed successfully.

:python_refresh_path
:: Refresh PATH for Python
echo        [INFO] Refreshing PATH...
set "PATH=%PATH%;C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python312;C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python312\Scripts"
set "PATH=%PATH%;C:\Program Files\Python312;C:\Program Files\Python312\Scripts"
set "PATH=%PATH%;%LOCALAPPDATA%\Programs\Python\Python312;%LOCALAPPDATA%\Programs\Python\Python312\Scripts"

:: Also try to pick up from registry
for /f "tokens=2*" %%a in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path 2^>nul') do set "SYS_PATH=%%b"
for /f "tokens=2*" %%a in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "USR_PATH=%%b"
if defined SYS_PATH set "PATH=!SYS_PATH!;!USR_PATH!;%PATH%"

where python >nul 2>&1
if %ERRORLEVEL% equ 0 (
    for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo        [OK] Verified: %%v
) else (
    where py >nul 2>&1
    if !ERRORLEVEL! equ 0 (
        for /f "tokens=*" %%v in ('py --version 2^>^&1') do echo        [OK] Verified: %%v (py launcher)
    ) else (
        echo        [WARNING] Python installed but not in PATH yet.
        echo        You may need to restart this script after installation completes.
    )
)

:python_done
echo.

:: ============================================================
:: STEP 3: Clone Repository
:: ============================================================
echo [3/5] Setting up NeuroX v9 repository...
echo.

:: Check if already in the repo directory (script run from repo)
if exist "%~dp0.git" (
    echo        [OK] Already running from the NeuroX v9 repository.
    set "INSTALL_DIR=%~dp0"
    if "!INSTALL_DIR:~-1!"=="\" set "INSTALL_DIR=!INSTALL_DIR:~0,-1!"
    goto :repo_done
)

:: Check if target directory already has the repo
if exist "%INSTALL_DIR%\.git" (
    echo        [OK] Repository already exists at: %INSTALL_DIR%
    goto :repo_done
)

:: Clone the repository
where git >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo        [ERROR] Git is not available. Cannot clone repository.
    echo        Please restart this script after Git installation completes.
    goto :repo_done
)

echo        Cloning to: %INSTALL_DIR%
echo.

:: Create parent directory if needed
for %%I in ("%INSTALL_DIR%") do set "PARENT_DIR=%%~dpI"
if not exist "%PARENT_DIR%" mkdir "%PARENT_DIR%"

git clone --branch %BRANCH% "%REPO_URL%" "%INSTALL_DIR%"
if !ERRORLEVEL! neq 0 (
    echo.
    echo        [ERROR] Failed to clone repository.
    echo        Check your internet connection and try again.
    goto :repo_done
)

echo        [OK] Repository cloned successfully.

:repo_done
echo.

:: ============================================================
:: STEP 4: Install Python Packages
:: ============================================================
echo [4/5] Installing Python packages...
echo.

:: Determine which python command to use
set "PYTHON_CMD="
where python >nul 2>&1
if %ERRORLEVEL% equ 0 (
    set "PYTHON_CMD=python"
) else (
    where py >nul 2>&1
    if !ERRORLEVEL! equ 0 (
        set "PYTHON_CMD=py"
    )
)

if not defined PYTHON_CMD (
    echo        [ERROR] Python is not available. Cannot install packages.
    echo        Please restart this script after Python installation completes.
    goto :packages_done
)

:: Upgrade pip first
echo        Upgrading pip...
%PYTHON_CMD% -m pip install --upgrade pip >nul 2>&1

:: Install requirements
set "REQ_FILE=%INSTALL_DIR%\requirements.txt"
if exist "%REQ_FILE%" (
    echo        Installing from requirements.txt...
    %PYTHON_CMD% -m pip install -r "%REQ_FILE%"
    if !ERRORLEVEL! equ 0 (
        echo.
        echo        [OK] All packages installed successfully.
    ) else (
        echo.
        echo        [WARNING] Some packages may have failed to install.
        echo        Try running manually: pip install numpy pandas pytest
    )
) else (
    echo        [INFO] requirements.txt not found. Installing packages directly...
    %PYTHON_CMD% -m pip install numpy pandas pytest
    if !ERRORLEVEL! equ 0 (
        echo        [OK] Packages installed.
    ) else (
        echo        [WARNING] Package installation had issues.
    )
)

:packages_done
echo.

:: ============================================================
:: STEP 5: Verify Installation
:: ============================================================
echo [5/5] Verifying installation...
echo.

set "ALL_GOOD=1"

:: Check Git
where git >nul 2>&1
if %ERRORLEVEL% equ 0 (
    for /f "tokens=*" %%v in ('git --version') do echo        [PASS] Git: %%v
) else (
    echo        [FAIL] Git not found in PATH
    set "ALL_GOOD=0"
)

:: Check Python
set "PY_VERIFIED=0"
where python >nul 2>&1
if %ERRORLEVEL% equ 0 (
    for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo        [PASS] Python: %%v
    set "PY_VERIFIED=1"
) else (
    where py >nul 2>&1
    if !ERRORLEVEL! equ 0 (
        for /f "tokens=*" %%v in ('py --version 2^>^&1') do echo        [PASS] Python: %%v
        set "PY_VERIFIED=1"
    )
)
if "!PY_VERIFIED!"=="0" (
    echo        [FAIL] Python not found in PATH
    set "ALL_GOOD=0"
)

:: Check Python packages
if defined PYTHON_CMD (
    %PYTHON_CMD% -c "import numpy; print(f'        [PASS] numpy: {numpy.__version__}')" 2>nul
    if !ERRORLEVEL! neq 0 (
        echo        [FAIL] numpy not installed
        set "ALL_GOOD=0"
    )
    %PYTHON_CMD% -c "import pandas; print(f'        [PASS] pandas: {pandas.__version__}')" 2>nul
    if !ERRORLEVEL! neq 0 (
        echo        [FAIL] pandas not installed
        set "ALL_GOOD=0"
    )
    %PYTHON_CMD% -c "import pytest; print(f'        [PASS] pytest: {pytest.__version__}')" 2>nul
    if !ERRORLEVEL! neq 0 (
        echo        [FAIL] pytest not installed
        set "ALL_GOOD=0"
    )
)

:: Check repository
if exist "%INSTALL_DIR%\main.py" (
    echo        [PASS] NeuroX v9 repository: %INSTALL_DIR%
) else (
    echo        [FAIL] NeuroX v9 repository not found at expected location
    set "ALL_GOOD=0"
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
) else (
    echo        [INFO] MetaTrader 5 not detected (install separately if needed)
)

echo.
echo ============================================================

if "!ALL_GOOD!"=="1" (
    color 0A
    echo.
    echo   SETUP COMPLETE - All checks passed!
    echo.
    echo   You're ready to run NeuroX v9.
    echo   Next steps:
    echo     1. Make sure MetaTrader 5 (Fusion Markets) is running
    echo     2. Double-click "Start.bat" to launch NeuroX v9
    echo.
    echo   Location: %INSTALL_DIR%
    echo.
) else (
    color 0E
    echo.
    echo   SETUP PARTIALLY COMPLETE
    echo.
    echo   Some components need attention (see FAIL items above).
    echo   You may need to:
    echo     - Restart your computer to refresh PATH
    echo     - Re-run this script after restart
    echo     - Install failed components manually
    echo.
)

echo ============================================================
echo.

:: Cleanup temp files
if exist "%TEMP_DIR%" rd /s /q "%TEMP_DIR%" 2>nul

pause
exit /b 0
