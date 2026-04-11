#!/bin/bash
# deploy.sh - Compile and deploy all files to the ESP8266 wirelessly via webrepl_cli.py

# 1. Compile everything (outputs .mpy files to build/)
./compile.sh

# 2. ESP8266 WebREPL IP and Password — loaded from connection_esp (format: host:port,password)
CONNECTION=$(cat connection_esp)
HOST=$(echo "$CONNECTION" | cut -d: -f1)
PORT=$(echo "$CONNECTION" | cut -d: -f2 | cut -d, -f1)
PASSWORD=$(echo "$CONNECTION" | cut -d, -f2)
WEBREPL_CLI="/Users/marc/Development/external/webrepl/webrepl_cli.py"

echo "Deploying to $HOST..."

# 3. Copy files.
# Use uncompiled main.py (required for MicroPython boot)
python "$WEBREPL_CLI" -p "$PASSWORD" main.py "$HOST":/main.py

# Ensure connection file is copied too (for WiFi credentials)
if [ -f "connection" ]; then
    python "$WEBREPL_CLI" -p "$PASSWORD" connection "$HOST":/connection
fi

# Copy all compiled .mpy files from build/
for f in build/*.mpy; do
    filename=$(basename "$f")
    python "$WEBREPL_CLI" -p "$PASSWORD" "$f" "$HOST":"/$filename"
done

# 4. Soft reset the board via WebREPL
python - <<EOF
import socket, struct, time

def client_handshake(sock):
    cl = sock.makefile("rwb", 0)
    cl.write(b"GET / HTTP/1.1\r\nHost: echo.websocket.org\r\nConnection: Upgrade\r\nUpgrade: websocket\r\nSec-WebSocket-Key: foo\r\n\r\n")
    while cl.readline() != b"\r\n":
        pass

def ws_write(s, data, frame=0x81):  # 0x81 = text frame
    l = len(data)
    hdr = struct.pack(">BB", frame, l) if l < 126 else struct.pack(">BBH", frame, 126, l)
    s.send(hdr + data)

def ws_read(s, size):
    res = b""
    while len(res) < size:
        res += s.recv(size - len(res))
    return res

s = socket.socket()
s.connect(socket.getaddrinfo("$HOST", $PORT)[0][4])
client_handshake(s)

# Login
while True:
    c = ws_read(s, 1)
    if c == b":":
        ws_read(s, 1)
        break
ws_write(s, b"$PASSWORD\r")
time.sleep(0.5)

# Send reset command
ws_write(s, b"import machine; machine.reset()\r\n")
time.sleep(0.5)
s.close()
print("Board reset.")
EOF

echo "Deployment complete!"
