# Astrolab

I have upgraded an almost 50 year old map of Paris to display solar/lunar positions.

[![Astrolab](https://www.marclieser.de/data/content/interests/astrolab/astrolab_ytcue.jpg)](http://www.youtube.com/watch?v=3vjASYzq22o "Astrolab")

Since I could not find a (free) web service to query solar and lunar azimuth and elevation, I used equations from [Meeus, Jean. Astronomical Algorithms, 1998](https://shopatsky.com/products/astronomical-algorithms-2nd-edition) and [Astronomy Answers](https://www.aa.quae.nl/en/reken.html) to do the calculations myself.
The accuracy is very poor and there are probably bugs.

The lack of double precision of the ESP8266 means that basic astronomical calculations cannot be performed with the necessary precision.
For example, the Julian day number (JDN) cannot actually be calculated to the day.
I have currently hotfixed this specific problem by breaking the equation into integer and floating point parts, but all following equations lack accuracy and in the long run I will just upgrade to an ESP32.

Next to the astrolab celestial map, the frame can show the time as an analog clock, light the map in a radial glow, in the four sides' own colors or as a gradient from top to bottom, and run two animations (see [Modes](#modes)).

The map can be controlled from your home wifi through a [web interface](http://astrolab.marclieser.de/), [Astrolab Remote](https://github.com/marcwingduck/astrolab-remote).

## Components

### Main Components

* [Adafruit HUZZAH ESP8266 Breakout](https://www.adafruit.com/product/2471)
* [Neopixel LEDs (SK6812RGBW)](https://www.adafruit.com/product/2842)

The worst case consumption of the 180 NeoPixels I used for this project is

    4 LEDs (RGBW) x 0.02 A (max current per LED) x 180 NeoPixels = 14.4 A

The ESP8266 consumes up to 250 mA.
So the worst case estimate amounts to 14.65 A, which will never be reached in practice.
Nevertheless, I opted for the next larger power supply (15 A) because it will run cooler as it will never reach its limit and excessive heat could damage the map or dissolve the glue.

So this 15A/5V power supply should be more than enough

* [Power Supply](https://www.meanwell-web.com/en-gb/ac-dc-single-output-enclosed-power-supply-output-rsp--75--5)

### Electronic Components

* 1000 uF capacitor connecting the + and - terminals of the power supply to prevent initial current peaks from damaging other parts of the circuit
* 340 Ohm data line resistor close to the first NeoPixel to help prevent voltage spikes damaging it (see the [Adafruit NeoPixel Überguide](https://learn.adafruit.com/adafruit-neopixel-uberguide/powering-neopixels]), they recommend 300 to 500 Ohm)
* [74AHCT125N](https://www.adafruit.com/product/1787) level-shifter from 3 V board logic to 5 V NeoPixel data signal
* [15 A Fuse](https://www.reichelt.de/feinsicherung-6-3x32mm-flink-us-norm-15a-rnd-170-00087-p204868.html?&nbc=1) and a [Fuse Holder](https://www.reichelt.de/sicherungshalter-6-3-x-32-20-a-32-v-kabel-litt-01550120hxu-p229211.html?&nbc=1)

Of course some cables are required. I soldered the microcontroller and the level-shifter on a prototyping board.

## Configuration

### `.env`

Copy `.env.example` to `.env` (gitignored) and fill in:

```
HOST=192.168.0.188:8266
HOST_SECRET=mypassword
WIFI_SSID=myssid
WIFI_PASSWORD=mypassword
```

`WIFI_SSID` and `WIFI_PASSWORD` let the board join your WiFi to retrieve date and time for the solar/lunar position calculations and the clock visualization. `HOST` (port optional, default 8266) and `HOST_SECRET` are the board's WebREPL address and password, used by `deploy.sh`, which also copies `.env` to the board.

### Accent Color Over UDP (optional)

The map has one accent color, river blue by default. Each mode shows it in a role it already has:
the highlights (equinox and solstice markers, the classic clock's second hand) and the neo clock's sweep.
With `ACCENT_PORT=4211` in `.env`, the map also takes that color from another device on the network.
While a received color is active, the solar map also shows it as a third light next to sun and moon, twice the
size of the sun, in the middle of the largest arc free of both: opposite the one that is up, between the two on
their far side, or facing the pole when neither is (`GLOW` in `paris.py`):

```
echo -n "accent ff8800" | nc -u -w0 <map ip> 4211   # any RGB hex, drawn at the map's brightness
echo -n "accent off" | nc -u -w0 <map ip> 4211      # back to the default
```

A sender should repeat its color every few seconds; after 30 s without one, the map returns to the default.
See `accent.py`.

### Frame Constants

In `frame.py`, adjust to your frame: the number of vertical (rows) and horizontal LEDs (cols), and the LEDs per centimeter.
The number of LEDs, `n = 2*(cols+rows)`, follows from them.

```
rows, cols = 36, 54
leds_per_cm = 0.6
```

In `paris.py`, the latitude and longitude of the location in degrees:

```
coords = (48.860536, 2.332237)
```

## Modes

`paris.show(name, ...)` switches to a mode, stopping whatever runs and fading over. The web interface sends nothing else; from the WebREPL it works the same, e.g. `paris.show('clock', True)`. Colors are G, R, B, W tuples.

| Name | Arguments | Shows |
|---|---|---|
| `solunar` | | the solar/lunar map: sun and moon where they stand, river and equinox/solstice markers |
| `clock` | `continuous` | a classic analog clock |
| `neo` | `start_at_minute, two_colors, ambient` | a clock filling up with the seconds |
| `radial` | `color[, corner]` | the frame in one color, like a light at its center |
| `sides` | `north, east, south, west, linear[, corner]` | each side in its own color, evenly or fading toward the corners |
| `vertical_interp` | `top, bottom` | a gradient from top to bottom |
| `vertical` | `top, bottom` | the top half in one color, the bottom half in another |
| `spin` | `color, frequency` | a beam turning around the frame |
| `larson` | `cardinal, primary, secondary` | a scanner along one side |
| `off` | | dark |

`paris.apply_dimmer(0..1)` sets the brightness of every mode. The test functions behind the web interface's Tests section live in `tests.py`, loaded only when used.

## MicroPython Firmware

Download the latest stable [ESP8266 MicroPython firmware](http://micropython.org/download/esp8266/) and create a new Python environment if not done yet:

```
conda create -n esp python=3.9
conda activate esp
pip install esptool
```

Connect an USB RS232 adapter to the HUZZAH ESP8266:

```
|                              |
| ( ) (TX) (RX) (C+) ( ) (GND) |
________________________________
```

When MicroPython boots for the first time, the ESP8266 radio does a full RF calibration and saves the parameters to flash. This draws a significant spike of current (up to 400mA).
If you are powering the HUZZAH solely from the USB-serial adapter (which usually only provides ~100-150mA on its 3.3V pin), the voltage drops, and the ESP8266 reboots with a wdt reset before it can finish.

**SO DON'T USE USB FTDI POWER, JUST CONNECT GND/RX/TX, leave C+ disconnected and USE THE EXTERNAL POWER OF THE ESP8266**

Clear and flash firmware (press/release RESET while holding GPIO0 button to put it into firmware flashing mode)

```
python3 -m esptool --port /dev/tty.usbserial-AH02PPM3 erase_flash
```

Press/release RESET while holding GPIO0 button

```
python3 -m esptool --port /dev/tty.usbserial-AH02PPM3 --baud 460800 write_flash --flash_size=detect 0 ESP8266_GENERIC-20260406-v1.28.0.bin
```

Keep the USB connection for the next step.

## WebREPL Setup

Open a serial connection to the board using `screen`:

```bash
screen /dev/tty.usbserial-AH02PPM3 115200
```

Once at the REPL, initiate the setup process:

```python
import webrepl_setup
```

Follow the setup steps and configure it to start on boot. Restart the board when finished.

## Cross-compile Project Files

I ran into size issues at some point which could be solved by pre-compiling the scripts into bytecode before transferring them to the ESP8266.

### Get Repository

In order to do so, clone the [MicroPython repository](https://github.com/micropython/micropython).

```
git clone https://github.com/micropython/micropython
```

You should checkout the version according to the firmware you just flashed.

### Build Cross Compiler

```
make -C mpy-cross
```

### Cross Compile Modules

Add `mpy-cross` to your path and run:

```bash
mpy-cross module.py
```

for individual modules, or use the provided script to compile all modules except for the main module:

```bash
./compile.sh
```

**Note:** Do not cross-compile `main.py`. MicroPython's boot sequence explicitly looks for a plain-text `main.py` file to execute after `boot.py`. If it's compiled as `main.mpy`, the firmware won't run it automatically on startup.

### Transfer Files

Instead of using the manual WebREPL web interface, you can deploy everything wirelessly using [`webrepl_cli.py`](https://github.com/micropython/webrepl) from the MicroPython webrepl repository. Clone it somewhere on your machine:

```bash
git clone https://github.com/micropython/webrepl /path/to/webrepl
```

Then update the `WEBREPL_CLI` path in `deploy.sh` to point to `webrepl_cli.py` in that checkout.

Connect to the `MicroPython-XXXXXX` WiFi network (default password: `micropythoN`), or if connected to your home network, use the IP your router assigned to the board.

To transfer a single file manually:

```bash
python webrepl_cli.py -p <password> local_file.py <host>:/remote_file.py
```

Or deploy all compiled `.mpy` files, the plain `main.py`, and your `.env` using the provided deployment script:

```bash
./deploy.sh
```

The script reads the target host, port, and WebREPL password from `.env` (see [Configuration](#configuration)), cross-compiles the latest code, transfers all files to the ESP8266, and soft-resets the board to run the new code.
