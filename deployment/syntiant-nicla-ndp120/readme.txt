There are 4 scripts for each supported OS:
- flash_<os> runs the mcu and the model flash script.
- flash_<os>_mcu flash just the firmware for the mcu.
- flash_<os>_model flash, if they are not present on the board, the NDP fw and the NDP dsp fw, and update the model.
- format_<os>_ext_flash erase the external flash

where os can be linux, mac or windows.

To install the required dependencies, run the install_lib script for your os; you need to run isntall_lib just once.

The script to update the model uses one python package:
- pyserial https://pyserial.readthedocs.io/en/latest/
