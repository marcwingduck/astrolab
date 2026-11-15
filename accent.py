"""
Accent color over UDP (optional, enabled by ACCENT_PORT in .env).

Lets another device on the network set the map's accent color:
each mode shows the received color in a role it already has (see paris.py: the
highlights, the neo clock's sweep, a third light on the solar map, opposite sun and moon); the default
comes back when the sender says so or goes quiet.

Datagrams are plain text:
    accent rrggbb   use this color (RGB hex); any brightness, it is drawn at the map's levels
    accent off      back to the default
A sender repeats its color every few seconds; after TIMEOUT_MS without one the default returns.

Test from a computer on the same network:
    echo -n "accent ff8800" | nc -u -w0 <map ip> 4211
"""

import socket
import utime
from machine import Timer

import colors
import paris

POLL_MS = 500
TIMEOUT_MS = 30000

sock = None
timer = Timer(-1)
active = False  # showing a received color rather than the default
last_ms = 0


def parse(msg):
    """b'accent rrggbb' -> full-brightness GRBW, 'off' for b'accent off', None if invalid."""
    parts = msg.split()
    if len(parts) != 2 or parts[0] != b'accent':
        return None
    if parts[1] == b'off':
        return 'off'
    if len(parts[1]) != 6:
        return None
    try:
        color = colors.hex2grb0(parts[1].decode())
    except ValueError:
        return None
    top = max(color)
    if not top:
        return None  # black is no accent
    return [colors.gamma[c * 255 // top] for c in color]


def restore():
    global active
    if active:
        active = False
        paris.change_accent(paris.accent_default)


def handle(msg):
    global active, last_ms
    color = parse(msg)
    if color == 'off':
        restore()
    elif color:
        active = True
        last_ms = utime.ticks_ms()
        paris.change_accent(color, received=True)  # returns right away if the color didn't change


def poll(_):
    try:
        while True:
            try:
                msg = sock.recv(64)
            except OSError:  # nothing waiting
                break
            handle(msg)
        if active and utime.ticks_diff(utime.ticks_ms(), last_ms) > TIMEOUT_MS:
            restore()
    except Exception as e:  # keep the timer alive whatever arrives
        print('accent:', e)


def start(port):
    global sock
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(socket.getaddrinfo('0.0.0.0', port)[0][-1])
    sock.setblocking(False)
    timer.init(period=POLL_MS, mode=Timer.PERIODIC, callback=poll)
