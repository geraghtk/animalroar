#!/bin/bash
set -e

SCRIPTPATH="$( cd "$(dirname "$0")" ; pwd -P )"

cd "$SCRIPTPATH"

./flash_linux_mcu.sh
echo "Please wait target to restart"
sleep 20
./flash_linux_model.sh
