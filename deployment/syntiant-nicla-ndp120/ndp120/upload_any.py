"""Upload arbitrary .synpkg files via AT+UPDATEFILE / YMODEM."""
import sys, os, time, serial

PORT = "COM5"
UPLOADER = "C:/Users/Kevin/AnimalRaw/deployment/syntiant-nicla-ndp120/ndp120/syntiant-uploader-win.exe"
FILES = sys.argv[1:]

ser = serial.Serial(PORT, 115200, timeout=0.2)
# Wake board
for _ in range(60):
    ser.write(b"test\r\n")
    if any(b"Not a valid AT command" in l for l in ser.readlines()):
        print("Board found")
        break
    time.sleep(0.5)

# Format
print("Formatting flash...")
ser.write(b"AT+FORMATEXTFLASH\r\n")
time.sleep(0.5); ser.readlines(); time.sleep(0.5); ser.readlines()
print("Done")

# Upload each file
for fname in FILES:
    base = os.path.basename(fname)
    print(f"\nUploading {base}...")
    while True:
        time.sleep(0.25)
        ser.write(f"AT+UPDATEFILE={base}\r\n".encode())
        time.sleep(0.25)
        ready = False
        for _ in range(5):
            line = ser.readline().decode(errors="ignore")
            if "Ready to update file" in line:
                ready = True; break
        if ready: break
    ser.flush(); ser.close()
    cmd = f'"{UPLOADER}" send -m Y -w Y -p {PORT} "{fname}"'
    print(cmd)
    print(os.popen(cmd).read())
    time.sleep(1)
    ser.open()
    time.sleep(1)

ser.close()
print("Done")
