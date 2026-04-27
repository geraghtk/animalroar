#!/bin/bash
set -e

SCRIPTPATH="$( cd "$(dirname "$0")" ; pwd -P )"

cd "$SCRIPTPATH"

./flash_mac_mcu.command
echo "Please wait target to reboot"
sleep 20
./flash_mac_model.command
