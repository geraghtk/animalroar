@ECHO OFF
SETLOCAL ENABLEDELAYEDEXPANSION
setlocal
REM go to the folder where this bat script is located
cd /d %~dp0

FOR %%i in (`DIR /b /s "." ^| find "ei_model*.bin") do SET BIN_FILE=%%i

FOR %%I IN (.) DO SET DIRECTORY_NAME=%%~nI%%~xI

echo Format external flash
echo Finding Nicla Voice...

set COM_PORT=""

for /f "tokens=1" %%i in ('arduino-cli board list ^| findstr "Nicla Voice" ^| findstr "COM"') do (
    set COM_PORT=%%i
)

IF %COM_PORT% == "" (
    GOTO NOTCONNECTED
)

cd ndp120
:NOPARAM
echo Formatting external memory
python ei_uploader.py -s %COM_PORT% -f
cd ..

IF %ERRORLEVEL% NEQ 0 (
    GOTO :FLASHINGFAILEDERROR
)

echo Format OK

@pause
exit /b 0

:NOTCONNECTED
echo Cannot find a connected Nicla Voice development board via 'arduino-cli board list'
@pause
exit /b 1

:FLASHINGFAILEDERROR
echo Error in format external memory
@pause
exit /b 1
