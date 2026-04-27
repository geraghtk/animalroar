#!/bin/bash
set -e

echo "Flashing synpgk to external flash"
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

UNAME=`uname -m`

echo "Finding Nicla Voice OK"
SCRIPTPATH="$( cd "$(dirname "$0")" ; pwd -P )"
cd "$SCRIPTPATH"
cd ndp120
echo "Updating NN model to flash..."

if [ "$UNAME" == "aarch64" ]; then
python3 ei_uploader.py -a ./syntiant-uploader-linux-arm64 -s $SERIAL_PORT -p -u ei_model.synpkg
else
python3 ei_uploader.py -a ./syntiant-uploader-linux -s $SERIAL_PORT -p -u ei_model.synpkg
fi

cd ..

echo "Writing NN model OK"

echo ""
echo "Press reset button to start the application"
