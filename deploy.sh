#!/bin/bash
# deploy.sh - Compile and deploy all files to the ESP8266 wirelessly via webrepl_cli.py

# 1. Compile everything (outputs .mpy files to build/)
./compile.sh

# 2. ESP8266 WebREPL address and password, from .env: HOST=host[:port], HOST_SECRET=password
env_value() {
    local v
    v=$(sed -n "s/^$1=//p" .env | tail -1)
    # strip one pair of surrounding quotes
    if [[ ${#v} -ge 2 && ( "$v" == \"*\" || "$v" == \'*\' ) ]]; then
        v=${v:1:${#v}-2}
    fi
    printf '%s' "$v"
}
HOST=$(env_value HOST)
PASSWORD=$(env_value HOST_SECRET)
PORT=8266
if [[ "$HOST" == *:* ]]; then
    PORT=${HOST##*:}
    HOST=${HOST%%:*}
fi
TARGET="$HOST:$PORT"
WEBREPL_CLI="/Users/marc/Development/external/webrepl/webrepl_cli.py"

echo "Deploying to $TARGET..."

# 3. Copy files.
# Use uncompiled main.py (required for MicroPython boot)
python "$WEBREPL_CLI" -p "$PASSWORD" main.py "$TARGET":/main.py

# The board reads its WiFi credentials from .env
python "$WEBREPL_CLI" -p "$PASSWORD" .env "$TARGET":/.env

# Copy all compiled .mpy files from build/
for f in build/*.mpy; do
    filename=$(basename "$f")
    python "$WEBREPL_CLI" -p "$PASSWORD" "$f" "$TARGET":"/$filename"
done

# 4. Soft reset the board via WebREPL
# (values passed through the environment, so quotes or $ in the password can't break the script)
HOST="$HOST" PORT="$PORT" PASSWORD="$PASSWORD" python - <<'EOF'
import os, socket, struct, time

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
s.connect(socket.getaddrinfo(os.environ["HOST"], int(os.environ["PORT"]))[0][4])
client_handshake(s)

# Login
while True:
    c = ws_read(s, 1)
    if c == b":":
        ws_read(s, 1)
        break
ws_write(s, os.environ["PASSWORD"].encode() + b"\r")
time.sleep(0.5)

# Send reset command
ws_write(s, b"import machine; machine.reset()\r\n")
time.sleep(0.5)
s.close()
print("Board reset.")
EOF

echo "Deployment complete!"
