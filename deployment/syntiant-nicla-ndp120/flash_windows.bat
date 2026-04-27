@ECHO OFF
SETLOCAL ENABLEDELAYEDEXPANSION
setlocal
REM go to the folder where this bat script is located
cd /d %~dp0

CALL flash_windows_mcu
echo Please wait target to reboot
timeout /t 5 /nobreak
CALL flash_windows_model
echo Flash done