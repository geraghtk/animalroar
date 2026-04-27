@ECHO OFF
SETLOCAL ENABLEDELAYEDEXPANSION
setlocal
REM go to the folder where this bat script is located
cd /d %~dp0

set /A EXPECTED_CLI_MAJOR=0
set /A EXPECTED_CLI_MINOR=34
set /A EXPECTED_CLI_REV=2

set NDP_CMD=ndp120\syntiant-uploader-win.exe
set ARDUINO_CORE=arduino:mbed_nicla
set BOARD=%ARDUINO_CORE%:nicla_voice
set MBED_VERSION=4.0.8

FOR %%I IN (.) DO SET DIRECTORY_NAME=%%~nI%%~xI

where /q arduino-cli
IF ERRORLEVEL 1 (
    GOTO NOTINPATHERROR
)

REM parse arduino-cli version
FOR /F "tokens=1-3 delims==." %%I IN ('arduino-cli version') DO (
    FOR /F "tokens=1-3 delims== " %%X IN ('echo %%I') DO (
        set /A CLI_MAJOR=%%Z
    )
    SET /A CLI_MINOR=%%J
    FOR /F "tokens=1-3 delims== " %%X IN ('echo %%K') DO (
        set /A CLI_REV=%%X
    )
)

if !CLI_MAJOR! LEQ !EXPECTED_CLI_MAJOR! if !CLI_MINOR! LSS !EXPECTED_CLI_MINOR! GOTO UPGRADECLI

if !CLI_MAJOR! NEQ !EXPECTED_CLI_MAJOR! (
    echo You're using an untested version of Arduino CLI, this might cause issues (found: %CLI_MAJOR%.%CLI_MINOR%.%CLI_REV%, expected: %EXPECTED_CLI_MAJOR%.%EXPECTED_CLI_MINOR%.%EXPECTED_CLI_REV% )
) else (
    if !CLI_MINOR! NEQ !EXPECTED_CLI_MINOR! (
        echo You're using an untested version of Arduino CLI, this might cause issues (found: %CLI_MAJOR%.%CLI_MINOR%.%CLI_REV%, expected: %EXPECTED_CLI_MAJOR%.%EXPECTED_CLI_MINOR%.%EXPECTED_CLI_REV% )
    ) else (
        if !CLI_REV! NEQ !EXPECTED_CLI_REV! (
            echo You're using an untested version of Arduino CLI, this might cause issues (found: %CLI_MAJOR%.%CLI_MINOR%.%CLI_REV%, expected: %EXPECTED_CLI_MAJOR%.%EXPECTED_CLI_MINOR%.%EXPECTED_CLI_REV% )
        ) 
    )
)

echo Finding Arduino Mbed Nicla %MBED_VERSION%...

(arduino-cli core list  2> nul) | findstr /r "%ARDUINO_CORE% *%MBED_VERSION%"
IF %ERRORLEVEL% NEQ 0 (
    echo Installing Nicla board ...
    arduino-cli core update-index
    arduino-cli core install %ARDUINO_CORE%@%MBED_VERSION%
    echo Installing Nicla board OK
)
echo Finding Arduino MBED core OK

set COM_PORT=""

echo Finding Nicla Voice...
for /f "tokens=1" %%i in ('arduino-cli board list ^| findstr "Nicla Voice" ^| findstr "COM"') do (
    set COM_PORT=%%i
)

IF %COM_PORT% == "" (
    GOTO NOTCONNECTED
)

:FLASHARDUINO

echo Finding Nicla Voice OK at %COM_PORT%

echo Flashing Arduino firmware...
CALL arduino-cli upload -p %COM_PORT% --fqbn %BOARD%  --input-file firmware.ino.elf

IF %ERRORLEVEL% NEQ 0 (
    GOTO FLASHINGFAILEDERROR
)

@pause
exit /b 0

:NOTINPATHERROR
echo Cannot find 'arduino-cli' in your PATH. Install the Arduino CLI before you continue
echo Installation instructions: https://arduino.github.io/arduino-cli/latest/
@pause
exit /b 1

:NOTCONNECTED
echo Cannot find a connected Nicla Voice development board via 'arduino-cli board list'
@pause
exit /b 1

:UPGRADECLI
echo You need to upgrade your Arduino CLI version (now: %CLI_MAJOR%.%CLI_MINOR%.%CLI_REV%, but required: %EXPECTED_CLI_MAJOR%.%EXPECTED_CLI_MINOR%.x or higher)
echo See https://arduino.github.io/arduino-cli/installation/ for upgrade instructions
@pause
exit /b 1

:FLASHINGFAILEDERROR
@pause
exit /b %ERRORLEVEL%
