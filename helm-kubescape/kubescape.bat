@echo off
REM Kubescape Helm Plugin for Windows
REM This is a basic Windows batch wrapper that calls the main shell script

REM Check if WSL is available and use it to run the shell script
where wsl >nul 2>nul
if %ERRORLEVEL% == 0 (
    echo [INFO] Running kubescape plugin via WSL...
    wsl bash "%HELM_PLUGIN_DIR%/kubescape.sh" %*
) else (
    echo [ERROR] This plugin requires WSL (Windows Subsystem for Linux) on Windows
    echo [INFO] Please install WSL or use the plugin from a Linux/macOS environment
    echo [INFO] WSL installation guide: https://docs.microsoft.com/en-us/windows/wsl/install
    exit /b 1
)