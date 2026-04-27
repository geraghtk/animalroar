#!/bin/bash

SCRIPTPATH="$( cd "$(dirname "$0")" ; pwd -P )"

# used for grepping
ARDUINO_CORE="arduino:mbed_nicla"
ARDUINO_CORE_VERSION="4.0.8"

BOARD="${ARDUINO_CORE}":nicla_voice

EXPECTED_CLI_MAJOR=0
EXPECTED_CLI_MINOR=34
EXPECTED_CLI_REV=2

if [ -z "$ARDUINO_CLI" ]; then
	ARDUINO_CLI=$(which arduino-cli || true)
fi

if [ ! -x "$ARDUINO_CLI" ]; then
    echo "Cannot find 'arduino-cli' in your PATH. Install the Arduino CLI before you continue."
    echo "Installation instructions: https://arduino.github.io/arduino-cli/latest/"
    exit 1
fi

CLI_MAJOR=$($ARDUINO_CLI version | cut -d. -f1 | rev | cut -d ' '  -f1)
CLI_MINOR=$($ARDUINO_CLI version | cut -d. -f2)
CLI_REV=$($ARDUINO_CLI version | cut -d. -f3 | cut -d ' '  -f1)

if ((CLI_MAJOR <= EXPECTED_CLI_MAJOR && CLI_MINOR < EXPECTED_CLI_MINOR)); then
    echo "You need to upgrade your Arduino CLI version (now: $CLI_MAJOR.$CLI_MINOR.$CLI_REV, but required: $EXPECTED_CLI_MAJOR.$EXPECTED_CLI_MINOR.$EXPECTED_CLI_REV or higher)"
    echo "See https://arduino.github.io/arduino-cli/installation/ for upgrade instructions"
    exit 1
fi

if (( CLI_MAJOR != EXPECTED_CLI_MAJOR || CLI_MINOR != EXPECTED_CLI_MINOR || CLI_REV != EXPECTED_CLI_REV)); then
    echo "You're using an untested version of Arduino CLI, this might cause issues (found: $CLI_MAJOR.$CLI_MINOR.$CLI_REV, expected: $EXPECTED_CLI_MAJOR.$EXPECTED_CLI_MINOR.$EXPECTED_CLI_REV)"
fi

# parses Arduino CLI's (core list and lib list) output and returns the installed version.
# Expected format (spaces can vary):
#    <package/core>   <installed version>  <latest version>  <other>
#
parse_installed() {
    echo "${1}" | awk -F " " '{print $2}' || true
}

# finds a Arduino core installed and returns the version
# otherwise it returns empty string
#
find_arduino_core() {
    core=$1
    version=$2
    result=""
    # space intentional
    line="$($ARDUINO_CLI core list | grep "${core} " || true)"
    if [ -n "$line" ]; then
        installed="$(parse_installed "${line}")"
        if [ "$version" = "$installed" ]; then
           result="$installed"
        fi
    fi
    echo $result
}

HAS_ARDUINO_CORE="$(find_arduino_core "${ARDUINO_CORE}" "${ARDUINO_CORE_VERSION}")"

if [ -z "$HAS_ARDUINO_CORE" ]; then
    echo not found
    echo "Installing Arduino Nicla Voice core..."
    $ARDUINO_CLI core update-index
    $ARDUINO_CLI core install "${ARDUINO_CORE}@${ARDUINO_CORE_VERSION}"
    echo "Installing Arduino Nicla Voice core OK"
fi

# Functions
echo "Finding Nicla Voice"

has_serial_port() {
    (arduino-cli board list | grep "nicla_voice" || true) | cut -d ' ' -f1
}
SERIAL_PORT=$(has_serial_port)

if [ -z "$SERIAL_PORT" ]; then
    echo "Cannot find a connected Arduino Nicla Voice development board (via 'arduino-cli board list')."
    exit 1
fi

echo "Finding Nicla Voice OK"

echo "Flashing board"
arduino-cli upload -p $SERIAL_PORT --fqbn  $BOARD --input-file firmware.ino.elf

echo "Flashing done. Use the flash_mac_model.command if you need to update the external flash"
