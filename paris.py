from machine import Pin, Timer, bitstream
import utime
import math

from common import *
from frame import *
import timing
import colors
import solunar
import clock as clk

# solunar
equinox_or_solstice = -1
coords = (48.860536, 2.332237)  # paris
# coords = (50.038333, 8.193611)  # home

# some colors matching the frame
color_off = bytearray(4)
color_ambient = bytearray((1, 0, 1, 8))
color_river = bytearray([int(0.06 * x) for x in colors.colors['river_blue']])

# The accent color, river blue unless one is received (see accent.py).
# Each mode shows it in a role it already has:
#   highlights (equinox, solstice markers, the classic clock's second hand), bright
#   the neo clock's sweep, as dim as the river
#   the solar map's glow, a third light next to sun and moon, in the middle of the largest arc
#   free of both; only while an accent is received (GLOW = 0 turns it off)
accent_default = colors.colors['river_blue']
color_accent = bytearray(4)
color_sweep = bytearray(4)
color_glow = bytearray(4)
accent_received = False
GLOW = 1.  # brightness of the glow's middle, of the full accent


def set_accent(color, received=False):
    """Set the accent from a full-brightness GRBW color, in place."""
    global accent_received
    accent_received = received
    for i in range(4):
        color_accent[i] = int(0.4 * color[i])
        color_sweep[i] = int(0.06 * color[i])
        color_glow[i] = int(GLOW * color[i])


set_accent(accent_default)

# global dimmer
dimmer = 0.5

# displayed led colors
leds0 = bytearray(n * 4)

# led colors to be faded to
leds1 = bytearray(n * 4)

# update timer
timer = Timer(-1)

# keep track if dynamic, timer-based mode is running or a static
static = True

# the running mode that shows the accent, so a new accent can redraw it:
# 'solunar', 'clock', 'ambient', or None for everything else
mode = None

# check if second changed to start counting millis
start_second = 0
last_second = -1
last_minute = -1

# spin globals
last_angle = 0
last_millis = 0

# larson scanner globals
larson_bounds = (0, n)
larson_index = 0
larson_dir = 1
larson_last_dir = -1

clock = clk.Clock()
clock.set_background_colors(color_ambient, color_river)
clock.set_hand_colors([26, 26, 0, 127], [60, 0, 40, 0], color_accent)


# ##############################################################################


def neopixel_write(pin, buffer):
    # low-level driving of a NeoPixel changed from esp.neopixel_write to machine.bitstream
    bitstream(pin, 0, (400, 850, 800, 450), buffer)


# init neopixels
pin = Pin(13, Pin.OUT)
neopixel_write(pin, leds0)


# ##############################################################################


FADE_MS = 1000

# fade's working space, allocated once here: later the heap is too fragmented for it
fade_index = bytearray(n)      # leds that change
fade_start = bytearray(n * 4)  # their colors before
fade_end = bytearray(n * 4)    # their colors after


def fade(duration_ms=FADE_MS):
    """Fade the displayed colors (leds0) to leds1 at the dimmer's brightness, over duration_ms,
    in as many steps as the board manages. Only the leds that change are touched, in integer
    math: a minute's redraw of the map moves just the sun, moon and glow. Allocates nothing."""
    l0, l1 = leds0, leds1
    index, start, end = fade_index, fade_start, fade_end
    dim = int(dimmer * 256)
    m = 0
    for i in range(n):
        o, p = i * 4, m * 4
        e0, e1, e2, e3 = (l1[o] * dim) >> 8, (l1[o + 1] * dim) >> 8, (l1[o + 2] * dim) >> 8, (l1[o + 3] * dim) >> 8
        if l0[o] != e0 or l0[o + 1] != e1 or l0[o + 2] != e2 or l0[o + 3] != e3:
            index[m] = i
            start[p], start[p + 1], start[p + 2], start[p + 3] = l0[o], l0[o + 1], l0[o + 2], l0[o + 3]
            end[p], end[p + 1], end[p + 2], end[p + 3] = e0, e1, e2, e3
            m += 1
    fade_run(m, duration_ms)


def fade_run(m, duration_ms):
    """Step the first m leds of fade_index from fade_start to fade_end over duration_ms."""
    if not m:
        return
    l0, index, start, end = leds0, fade_index, fade_start, fade_end
    t0 = utime.ticks_ms()
    w = 0
    while w < 256:
        t = utime.ticks_diff(utime.ticks_ms(), t0)
        if t >= duration_ms:
            w = 256
        else:
            w = t * 256 // duration_ms
            w = w * w * (768 - 2 * w) >> 16  # ease in and out (smoothstep, in 1/256)
        for k in range(m):
            o, p = index[k] * 4, k * 4
            s = start[p]
            l0[o] = s + ((end[p] - s) * w >> 8)
            s = start[p + 1]
            l0[o + 1] = s + ((end[p + 1] - s) * w >> 8)
            s = start[p + 2]
            l0[o + 2] = s + ((end[p + 2] - s) * w >> 8)
            s = start[p + 3]
            l0[o + 3] = s + ((end[p + 3] - s) * w >> 8)
        neopixel_write(pin, l0)


def apply_dimmer(value):
    global dimmer
    dimmer = clamp(value, 0., 1.)

    # leds1 holds what static modes and the solar map show: fade it to the new brightness now
    # (the clocks, spin and larson draw on their own and don't use the dimmer)
    if static or mode == 'solunar':
        fade()


def clear(leds):
    # leds1[:] = bytearray(n * 4)  <-- causes memory issues
    for i in range(n*4):
        leds[i] = 0


def init(leds, color):
    for i in range(n):
        o = i * 4
        leds[o] = color[0]
        leds[o+1] = color[1]
        leds[o+2] = color[2]
        leds[o+3] = color[3]


def off():
    clear(leds1)
    fade()


def ambient():
    paris(leds1)
    fade()


def paris(leds, glow_azimuth=None):
    init(leds, color_ambient)
    if glow_azimuth is not None:
        draw_glow(color_glow, glow_azimuth, leds)
    set_area2(1/leds_per_cm, 6, color_river, leds)
    set_area2(65/leds_per_cm, 10, color_river, leds)
    set_area2(143/leds_per_cm, 5, color_river, leds)


def draw_glow(color, azimuth, leds):
    """Blend color in around azimuth (radians, clockwise from north)."""
    result = unwind_angle(northclockwise2math(azimuth))
    if result:
        set_area2(result[0], width / 3, color, leds)


def glow_azimuth(positions):
    """The middle of the largest arc free of the bodies that are up, from (azimuth, elevation)
    pairs: opposite a lone one, between two on their far side, and facing the pole (where the
    sun goes least) when none is up."""
    up = sorted(azim % (2. * math.pi) for azim, elev in positions if elev > 0.)
    if not up:
        return 0. if coords[0] >= 0 else math.pi
    if len(up) == 1:
        return up[0] + math.pi
    middle = (up[0] + up[1]) / 2.
    return middle if up[1] - up[0] > math.pi else middle + math.pi


def set_circular_background(color):
    for i in range(n):
        intensity = get_distance_intensity(i)
        icolor = [int(intensity * c) for c in color]
        leds1[i * 4:i * 4 + 4] = bytearray(icolor)
    fade()


def set_area(center, size, primary, secondary, leds):
    if size == 1:
        leds[center * 4:center * 4 + 4] = bytearray(primary)
        return

    half = int(size / 2)
    start = center - half
    end = center + half + size % 2
    d = 0. if size % 2 else 0.5
    for i in range(start, end):
        x = center - i - d
        t = math.fabs((x - sign(x) * d) / (half - (size + 1) % 2))
        color = interpolate_rgbw(primary, secondary, t)
        index = i % n
        leds[index * 4:index * 4 + 4] = bytearray(color)


def set_sides(north, east, south, west, linear=False):

    clear(leds1)

    if linear:
        for i in range(*cardinals['north'][2]):
            o = i * 4
            leds1[o] = north[0]
            leds1[o+1] = north[1]
            leds1[o+2] = north[2]
            leds1[o+3] = north[3]
        for i in range(*cardinals['east'][2]):
            o = i * 4
            leds1[o] = east[0]
            leds1[o+1] = east[1]
            leds1[o+2] = east[2]
            leds1[o+3] = east[3]
        for i in range(*cardinals['south'][2]):
            o = i * 4
            leds1[o] = south[0]
            leds1[o+1] = south[1]
            leds1[o+2] = south[2]
            leds1[o+3] = south[3]
        for i in range(*cardinals['west'][2]):
            o = i * 4
            leds1[o] = west[0]
            leds1[o+1] = west[1]
            leds1[o+2] = west[2]
            leds1[o+3] = west[3]
    else:
        set_area2(cardinals['north'][0] / leds_per_cm, width, north, leds1)
        set_area2(cardinals['east'][0] / leds_per_cm, height, east, leds1)
        set_area2(cardinals['south'][0] / leds_per_cm, width, south, leds1)
        set_area2(cardinals['west'][0] / leds_per_cm, height, west, leds1)

    fade()

# ##############################################################################


def set_vertical(c1, c2):
    set_area(cols//2 + n//2, n//2, c1, c1, leds1)
    set_area(cols//2, n//2, c2, c2, leds1)
    fade()


def set_horizontal(c1, c2):
    set_area(cols+rows//2, n//2, c1, c1, leds1)
    set_area(cols+rows+cols+rows//2, n//2, c2, c2, leds1)
    fade()


def set_vertical_interp(c1, c2):
    set_area(cardinals['north'][0], cardinals['north'][1], c1, c1, leds1)
    set_area(cardinals['south'][0], cardinals['south'][1], c2, c2, leds1)
    for i in range(rows):
        color_linear = interpolate_rgbw(c1, c2, (i + 1.) / rows)
        color = bytearray(color_linear)
        i_east = north_east + i
        i_west = north_west - i - 1
        leds1[i_east * 4:i_east * 4 + 4] = color
        leds1[i_west * 4:i_west * 4 + 4] = color
    fade()


# ##############################################################################


RAMP_TOP_MS = 800
RAMP_TOP_WIDEN = 6.5  # 1: set_area2's plain bell; higher: a wider plateau


def ramp_up():
    """
    Start animation.
    Draws into leds0 array so the next animation will fade from there to leds1.
    """

    center = cardinals['south'][0]
    size = (cols + 2 * rows)
    d = (size + 1) % 2
    ramp_color_1 = bytearray((0, 0, 0, 5))
    ramp_color_2 = bytearray((0, 0, 0, 50))
    ramp_color_3 = bytearray((0, 0, 0, 200))

    clear(leds0)
    set_area2(center/leds_per_cm, width/3, ramp_color_2, leds0)
    neopixel_write(pin, leds0)

    utime.sleep_ms(200)

    for i in range(size // 2):
        i1 = (center - (i % n) - d) % n
        i2 = (center + (i % n)) % n
        leds0[i1 * 4:i1 * 4 + 4] = ramp_color_1
        leds0[i2 * 4:i2 * 4 + 4] = ramp_color_1
        neopixel_write(pin, leds0)
        utime.sleep_ms(12)

    # The top lights up, faded in by time: white over the top edge, a plateau with soft ends,
    # set_area2's bell widened by the exponent
    center, size = cardinals['north'][0]/leds_per_cm, width
    m = 0
    for i in range(int((center - size/2.) * leds_per_cm) + 1, int((center + size/2.) * leds_per_cm) + 1):
        led = i % n
        k = 1. - max(0., 1. - sine(center, size, i/leds_per_cm)) ** RAMP_TOP_WIDEN
        o, p = led * 4, m * 4
        fade_index[m] = led
        for c in range(4):
            v = leds0[o + c]
            fade_start[p + c] = v
            fade_end[p + c] = int(v + (ramp_color_3[c] - v) * k)
        m += 1
    fade_run(m, RAMP_TOP_MS)

    fade()


# ##############################################################################


def test_led(led_id, brightness=255, n_times=3, timeout_ms=500):
    for _ in range(n_times):
        for i in range(4):
            clear(leds0)
            index = (led_id*4) + i
            leds0[index] = brightness
            neopixel_write(pin, leds0)
            utime.sleep_ms(timeout_ms)
        clear(leds0)
        neopixel_write(pin, leds0)
        utime.sleep_ms(timeout_ms)
    off()


def cycle_channels(brightness=255, n_cycles=1, timeout_ms=100):
    for i in range(n * 4 * n_cycles):
        clear(leds0)
        index = i % (n * 4)
        leds0[index] = brightness
        neopixel_write(pin, leds0)
        utime.sleep_ms(timeout_ms)
    off()


def cycle_color(color, n_cycles=1, timeout_ms=100):
    for i in range(n * n_cycles):
        clear(leds0)
        index = (i % n) * 4
        leds0[index:index + 4] = bytearray(color)
        neopixel_write(pin, leds0)
        utime.sleep_ms(timeout_ms)
    off()


def cycle_circular(size=1):
    n_samples = 360
    color_1 = [0, 0, 0, 0]  # background color
    color_2 = [0, 164, 0, 0]  # pointer color
    for i in range(n_samples):
        angle = 2/3.*math.pi + i/n_samples * 3/4.*math.pi
        # angle = 2/3.*math.pi + i/n_samples * 2*math.pi
        cm_on_strip, (x, y) = unwind_angle(northclockwise2math(angle))
        fraction_led = cm_on_strip * leds_per_cm
        frac, frac_led_index = math.modf(fraction_led)
        frac_led_index = int(frac_led_index)
        init(leds0, color_1)
        id0 = frac_led_index * 4
        id1 = ((frac_led_index+1) % n) * 4

        # 1 smooth
        # leds0[id0:id0+4] = bytearray((0, 0, 0, int((1-frac)*64)))
        # leds0[id1:id1+4] = bytearray((0, 0, 0, int(frac*64)))

        # 2 blending in: not so super smooth, but ok
        # leds0[id0:id0+4] = bytearray(interpolate_rgbw(color_2, color_1, frac))
        # leds0[id1:id1+4] = bytearray(interpolate_rgbw(color_1, color_2, frac))

        # 3
        set_area2(cm_on_strip, size, color_2, leds0)

        neopixel_write(pin, leds0)
        utime.sleep_ms(1)
    off()


# ##############################################################################


def solunar_positions(lat_long_deg, utc_time):
    """(azimuth, elevation) of the moon and the sun, radians."""
    return (solunar.calc_lunar_position(lat_long_deg, utc_time),
            solunar.calc_solar_position(lat_long_deg, utc_time))


def draw_solunar_positions(lat_long_deg, utc_time, leds, positions=None):
    (lunar_azim, lunar_elev), (solar_azim, solar_elev) = positions or solunar_positions(lat_long_deg, utc_time)
    # moon
    lunar_result = unwind_angle(northclockwise2math(lunar_azim))
    if lunar_result and lunar_elev > 0.:
        distance = lunar_result[0]
        f1 = clamp(math.degrees(lunar_elev), 0., 18.5) / 18.5
        f2 = clamp(math.degrees(lunar_elev), 0., 6.) / 6.
        color = interpolate_rgbw((10, 10, 20, 80), (64, 64, 200, 0), f1)
        set_area2(distance, 1 + f2 * 10, (0, 0, 0, 5), leds)
        set_area2(distance, 1 + f2 * 5, color, leds)
    # sun
    solar_result = unwind_angle(northclockwise2math(solar_azim))
    if solar_result and solar_elev > 0.:
        distance = solar_result[0]
        f1 = clamp(math.degrees(solar_elev), 0., 23.45) / 23.45
        f2 = clamp(math.degrees(solar_elev), 0., 6.) / 6.
        g = int(interpolate(50, 180, f1))
        set_area2(distance, 1 + f2 * 14, (50, 255, 0, 0), leds)
        set_area2(distance, 1 + f2 * 7, (g, 255, 0, 0), leds)


def paris_solunar():
    now = utime.localtime()
    positions = solunar_positions(coords, now)
    paris(leds1, glow_azimuth(positions) if accent_received and GLOW > 0 else None)
    for i in range(equinox_or_solstice + 1):
        cardinal = list(cardinals.values())[i]
        set_area2(cardinal[0]/leds_per_cm, 5, color_accent, leds1)
    draw_solunar_positions(coords, now, leds1, positions)
    fade()


def solunar_demo():
    paris(leds1)
    fade()
    year, month, day, hour, minute, second, weekday, yearday = utime.localtime()

    for h in range(24):
        for m in range(0, 60):
            # clear
            paris(leds0)

            # hour
            angle = (h % 12 + m / 60.) / 12. * 2. * math.pi
            distance = unwind_angle(northclockwise2math(angle))[0]
            set_area2(distance, 4, [158, 81, 188, 0], leds0)

            # solar/lunar
            draw_solunar_positions(coords, (year, month, day, h, m, 0, weekday, yearday), leds0)

            # apply
            neopixel_write(pin, leds0)

    paris(leds1)
    fade()


# ##############################################################################


def update_clock():
    global start_second, last_second
    h, m, s = utime.localtime()[3:6]
    h = (h + timing.get_cet_offset()) % 24
    if last_second != s:  # no milliseconds in utime, count manually
        start_second = utime.ticks_ms()
    last_second = s
    ms = int(clamp(utime.ticks_ms() - start_second, 0, 1000))

    if clock.update(h, m, s, ms, leds0):
        neopixel_write(pin, leds0)


def clock_demo():
    for h in range(24):
        for m in range(0, 60):
            for s in range(0, 60):
                for ms in range(0, 1000, 250):
                    clock.update(h, m, s, ms, leds0)
                    neopixel_write(pin, leds0)


# ##############################################################################


def spin(color, frequency):
    global last_millis, last_angle

    tail = 24

    now_millis = utime.ticks_ms()
    dt = (now_millis - last_millis) / 1000.
    last_millis = now_millis

    angle = wrap_to_0_2pi(last_angle + dt * frequency * 2. * math.pi)
    last_angle = angle
    cm_on_strip, (x, y) = unwind_angle(northclockwise2math(angle))
    intensity = (min(height, width) / 2.) / math.sqrt(x*x+y*y)
    fraction_led = cm_on_strip * leds_per_cm

    frac, frac_led_index = math.modf(fraction_led)
    frac_led_index = int(frac_led_index)

    background = [0, 0, 0, 0]
    beam_color = [int(intensity * c) for c in color]

    init(leds0, background)

    for i in range(tail):
        o = ((frac_led_index - i) % n) * 4
        t = 1. - float(i) / tail
        leds0[o] = int(interpolate(0, beam_color[0], t))
        leds0[o+1] = int(interpolate(0, beam_color[1], t))
        leds0[o+2] = int(interpolate(0, beam_color[2], t))
        leds0[o+3] = int(interpolate(0, beam_color[3], t))

    neopixel_write(pin, leds0)


def larson_scanner(primary, secondary):
    global larson_index, larson_dir, larson_last_dir

    size = 12

    init(leds1, secondary)
    leds1[larson_index * 4:larson_index * 4 + 4] = bytearray(primary)

    for i in range(size):
        b = larson_index + 1 + i
        a = larson_index - 1 - i
        t = (i+1.) / size
        fading = interpolate_rgbw(secondary, primary, 1-t)
        if larson_bounds[0] <= a and a < larson_bounds[1]:
            leds1[a * 4:a * 4 + 4] = bytearray(fading)
        if larson_bounds[0] <= b and b < larson_bounds[1]:
            leds1[b * 4:b * 4 + 4] = bytearray(fading)

    neopixel_write(pin, leds1)

    larson_last_dir = larson_dir
    larson_index += larson_dir
    if larson_dir == 1 and larson_index == larson_bounds[1] - 1:
        larson_dir = -1
    elif larson_dir == -1 and larson_index == larson_bounds[0]:
        larson_dir = 1


# ##############################################################################


def set_color(led_index, color, clear_others=False):
    led_index = clamp(led_index, 0, n-1)
    if clear_others:
        clear(leds0)
    leds0[led_index*4:led_index*4+4] = bytearray(color)
    neopixel_write(pin, leds0)


# ##############################################################################


def run_solunar():
    global static, equinox_or_solstice, mode
    mode = 'solunar'

    # calculate once if today is equinox or solstice
    equinox_or_solstice = solunar.is_equinox_or_solstice(utime.localtime())

    paris_solunar()

    static = False
    timer.init(period=60000, mode=Timer.PERIODIC, callback=lambda t: paris_solunar())


def run_cls_clock(continuous=False):
    global static, mode
    mode = 'clock'

    clock.update_params({'mode': 'cls', 'continuous': continuous})
    clock.set_background_colors(color_ambient, color_river)
    clock.set_hand_colors([26, 26, 0, 127], [60, 0, 40, 0], color_accent)

    timing.update_time()

    static = False
    timer.init(period=100, mode=Timer.PERIODIC, callback=lambda t: update_clock())


def run_neo_clock(start_at_minute=False, two_colors=False, ambient=False):
    global static, last_minute, mode
    mode = 'clock'

    clock.update_params({'mode': 'neo',
                         'start_at_minute': start_at_minute,
                         'two_colors': two_colors,
                         'ambient': ambient})

    if ambient:
        clock.set_background_colors(color_ambient, color_sweep)
        clock.set_hand_colors([26, 26, 0, 127], [60, 0, 40, 0], color_accent)
    else:
        clock.set_background_colors(colors.colors['cyan'], colors.colors['orange'])

    timing.update_time()
    s = utime.localtime()[5]  # seconds
    while True:  # wait for the next full second
        if utime.localtime()[5] != s:
            last_minute = utime.localtime()[4]  # prevents color update on first neo draw
            break
        utime.sleep_ms(10)

    static = False
    timer.init(period=100, mode=Timer.PERIODIC, callback=lambda t: update_clock())


def run_spin(color, frequency=0.25):
    global static

    static = False
    timer.init(period=100, mode=Timer.PERIODIC, callback=lambda t: spin(color, frequency))


def run_larson_scanner(cardinal, primary, secondary):
    global static, larson_bounds, larson_index, larson_dir, larson_last_dir

    larson_bounds = cardinals[cardinal][2]
    larson_index = larson_bounds[0]
    larson_dir = 1
    larson_last_dir = -1

    n_leds = cardinals[cardinal][1]
    seconds = 2.
    dt = seconds / n_leds * 1000.

    static = False
    timer.init(period=int(round(dt)), mode=Timer.PERIODIC, callback=lambda t: larson_scanner(primary, secondary))


def stop_timer():
    global static, mode
    mode = None
    if not static:
        leds0[:] = leds1  # copy currently displayed colors to start array for next fade
        static = True  # back to static mode
    timer.deinit()


def change_accent(color, received=False):
    """Switch to another accent (full-brightness GRBW) and redraw what shows it."""
    old_accent, old_sweep, old_received = color_accent[:], color_sweep[:], accent_received
    set_accent(color, received)
    if color_accent == old_accent and color_sweep == old_sweep and accent_received == old_received:
        return
    if mode == 'solunar':
        paris_solunar()
    elif mode == 'clock':  # repaints within a second
        clock.replace_color(old_sweep, color_sweep)
        clock.replace_color(old_accent, color_accent)


# ##############################################################################


def start():
    """Boot animation, shown while wifi and ntp are still connecting."""
    paris(leds1)
    ramp_up()


def run(is_online):
    if is_online:
        run_solunar()
    else:
        set_sides((0, 0, 0, 0), (50, 50, 0, 80), (0, 0, 0, 0), (50, 50, 0, 80), False)
