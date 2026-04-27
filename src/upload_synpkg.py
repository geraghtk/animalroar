"""
Upload .synpkg files to Nicla Voice SPI flash via YMODEM.
Board must be running Syntiant_upload_fw_ymodem.ino.

Usage:  python src/upload_synpkg.py
"""

import serial
import time
import os
import struct

PORT       = "COM5"
BAUD       = 115200
SYNPKG_DIR = r"C:\Users\Kevin\.platformio\packages\framework-arduino-mbed\libraries\NDP\extra"
FILES      = [
    "mcu_fw_120_v91.synpkg",
    "dsp_firmware_v91.synpkg",
    "alexa_334_NDP120_B0_v11_v91.synpkg",
]

# Protocol constants
SOH  = 0x01
STX  = 0x02
EOT  = 0x04
ACK  = 0x06
NAK  = 0x15
POLL = 0x43   # 'C'
BLOCK_SIZE = 1024

def crc16(data: bytes, pad_to: int = None) -> int:
    crc = 0
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = (crc << 1) ^ 0x1021 if crc & 0x8000 else crc << 1
        crc &= 0xFFFF
    if pad_to and len(data) < pad_to:
        for _ in range(pad_to - len(data)):
            crc ^= EOT << 8
            for _ in range(8):
                crc = (crc << 1) ^ 0x1021 if crc & 0x8000 else crc << 1
            crc &= 0xFFFF
    return crc


def read_byte(s: serial.Serial, timeout: float = 10.0) -> int:
    s.timeout = timeout
    b = s.read(1)
    if not b:
        raise TimeoutError("Timed out waiting for byte from board")
    return b[0]


def send_block(s: serial.Serial, block_num: int, data: bytes):
    # Pad with EOT to 1024 bytes
    padded = data + bytes([EOT] * (BLOCK_SIZE - len(data)))
    checksum = crc16(data, BLOCK_SIZE)
    pkt = (bytes([STX, block_num & 0xFF, (255 - block_num) & 0xFF])
           + padded
           + bytes([checksum >> 8, checksum & 0xFF]))
    s.write(pkt)
    time.sleep(0.05)   # small delay on Windows (mirrors the Go code)


def modem_send(s: serial.Serial, data: bytes, filename: str):
    # 1. Wait for POLL
    b = read_byte(s)
    if b != POLL:
        raise RuntimeError(f"Expected POLL (0x43), got 0x{b:02x}")

    # 2. Send block 0: filename\0size\0 padded to 1024 with 0x00
    header = (os.path.basename(filename).encode() + b'\x00'
              + str(len(data)).encode() + b'\x00')
    header = header + bytes(BLOCK_SIZE - len(header))
    send_block(s, 0, header)

    # 3. Wait for ACK
    b = read_byte(s)
    if b != ACK:
        raise RuntimeError(f"Header block: expected ACK, got 0x{b:02x}")

    # 4. Wait for POLL
    b = read_byte(s)
    if b != POLL:
        raise RuntimeError(f"Expected POLL before data, got 0x{b:02x}")

    # 5. Send data blocks
    blocks = (len(data) + BLOCK_SIZE - 1) // BLOCK_SIZE
    print(f"    {blocks} blocks to send", flush=True)
    for i in range(blocks):
        chunk = data[i * BLOCK_SIZE:(i + 1) * BLOCK_SIZE]
        send_block(s, i + 1, chunk)
        b = read_byte(s)
        if b != ACK:
            raise RuntimeError(f"Block {i+1}: expected ACK, got 0x{b:02x}")
        if (i + 1) % 20 == 0:
            print(f"    {i+1}/{blocks} blocks sent", flush=True)

    # 6. EOT → NAK
    s.write(bytes([EOT]))
    b = read_byte(s)
    if b != NAK:
        raise RuntimeError(f"After EOT: expected NAK, got 0x{b:02x}")

    # 7. EOT → ACK
    s.write(bytes([EOT]))
    b = read_byte(s)
    if b != ACK:
        raise RuntimeError(f"After 2nd EOT: expected ACK, got 0x{b:02x}")

    # 8. Wait for POLL, send null block to end batch
    b = read_byte(s)
    if b != POLL:
        raise RuntimeError(f"End POLL: expected POLL, got 0x{b:02x}")
    send_block(s, 0, bytes(BLOCK_SIZE))

    # 9. Wait for final ACK
    b = read_byte(s)
    if b != ACK:
        raise RuntimeError(f"Final ACK: got 0x{b:02x}")


def upload_file(s: serial.Serial, filename: str) -> bool:
    path = os.path.join(SYNPKG_DIR, filename)
    size = os.path.getsize(path)
    print(f"  Uploading {filename} ({size/1024:.1f} KB)...", flush=True)

    # Trigger YMODEM receive on board ("Y\r\n"), wait for board to echo "Y"
    s.reset_input_buffer()
    s.write(b"Y\r\n")
    deadline = time.time() + 5
    buf = b""
    while time.time() < deadline:
        buf += s.read(s.in_waiting or 1)
        if b"Y" in buf:
            break
    else:
        print("  Warning: no 'Y' confirmation from board, proceeding anyway")

    time.sleep(0.5)
    s.reset_input_buffer()

    with open(path, "rb") as f:
        data = f.read()

    modem_send(s, data, filename)
    print(f"  {filename} OK", flush=True)
    return True


if __name__ == "__main__":
    print(f"Opening {PORT} at {BAUD} baud...")
    s = serial.Serial(PORT, BAUD, timeout=5)
    time.sleep(2)
    s.reset_input_buffer()

    # List existing files
    print("Current flash contents:")
    s.write(b"L\r\n")
    time.sleep(1)
    print(s.read(s.in_waiting or 1).decode("utf-8", errors="replace").strip() or "(empty)")

    # Upload each file
    all_ok = True
    for fname in FILES:
        try:
            upload_file(s, fname)
        except Exception as e:
            print(f"  FAILED: {e}")
            all_ok = False

    # List final flash contents
    time.sleep(0.5)
    s.reset_input_buffer()
    print("\nFlash contents after upload:")
    s.write(b"L\r\n")
    time.sleep(1)
    print(s.read(s.in_waiting or 1).decode("utf-8", errors="replace").strip())

    s.close()
    print("\nDone." if all_ok else "\nSome files failed — check output above.")
