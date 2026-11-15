from machine import Pin, Timer, bitstream
import gc
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
color_river = bytearray([int(0.06 * x) for x in colors.RIVER_BLUE])

# The accent color, river blue unless one is received (see accent.py).
# Each mode shows it in a role it already has:
#   highlights (equinox, solstice markers, the classic clock's second hand), bright
#   the neo clock's sweep, as dim as the river
#   the solar map's glow, a third light next to sun and moon, in the middle of the largest arc
#   free of both; only while an accent is received (GLOW = 0 turns it off)
accent_default = colors.RIVER_BLUE
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
# 'solunar', 'clock', or None for everything else
mode = None

# check if second changed to start counting millis
start_second = 0
last_second = -1

# spin globals
last_angle = 0
last_millis = 0
spin_head = -1  # the beam's head led last frame, -1: draw the whole strip
SPIN_TAIL = 24  # leds
SPIN_FRAME_MS = 40

# larson scanner globals
larson_bounds = (0, n)
larson_index = 0
larson_dir = 1
larson_last_dir = -1

clock = clk.Clock()
clock.set_background_colors(color_ambient, color_river)
clock.set_hand_colors([26, 26, 0, 127], [60, 0, 40, 0], color_accent)


# ##############################################################################


# False while a timer mode's first frame is drawn unseen (see fade_in)
showing = True


def neopixel_write(pin, buffer):
    # low-level driving of a NeoPixel changed from esp.neopixel_write to machine.bitstream
    if showing:
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
# Each led rounds at its own threshold, spread evenly (golden ratio): fading between two close
# levels, some leds take the step before their neighbors, so a dim area fades evenly instead of
# all its leds jumping together. Start and end stay exact; each led still steps only once per level.
fade_dither = bytearray((i * 159) & 255 for i in range(n))


def fade(duration_ms=FADE_MS):
    """Fade the displayed colors (leds0) to leds1 at the dimmer's brightness, over duration_ms,
    in as many steps as the board manages. Only the leds that change are touched, in integer
    math: a minute's redraw of the map moves just the sun, moon and glow. Allocates nothing."""
    fade_run(fade_plan(leds0, leds1, int(dimmer * 256)), duration_ms)


def fade_in(draw, duration_ms=FADE_MS):
    """Start a timer mode softly: draw its first frame into leds0 unseen, then fade to it from
    what was shown. leds1 holds that meanwhile: the timer modes don't use it."""
    global showing
    leds1[:] = leds0
    showing = False
    try:
        draw()
    finally:
        showing = True
    fade_run(fade_plan(leds1, leds0, 256), duration_ms)


def fade_plan(shown, target, dim):
    """Fill fade_index, fade_start and fade_end with the leds where shown differs from target at
    dim/256 brightness; returns how many."""
    index, start, end = fade_index, fade_start, fade_end
    m = 0
    for i in range(n):
        o, p = i * 4, m * 4
        e0, e1, e2, e3 = (target[o] * dim) >> 8, (target[o + 1] * dim) >> 8, (target[o + 2] * dim) >> 8, (target[o + 3] * dim) >> 8
        if shown[o] != e0 or shown[o + 1] != e1 or shown[o + 2] != e2 or shown[o + 3] != e3:
            index[m] = i
            start[p], start[p + 1], start[p + 2], start[p + 3] = shown[o], shown[o + 1], shown[o + 2], shown[o + 3]
            end[p], end[p + 1], end[p + 2], end[p + 3] = e0, e1, e2, e3
            m += 1
    return m


def fade_run(m, duration_ms):
    """Step the first m leds of fade_index from fade_start to fade_end over duration_ms."""
    if not m:
        return
    l0, index, start, end, dither = leds0, fade_index, fade_start, fade_end, fade_dither
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
            i = index[k]
            o, p, d = i * 4, k * 4, dither[i]
            s = start[p]
            l0[o] = s + (((end[p] - s) * w + d) >> 8)
            s = start[p + 1]
            l0[o + 1] = s + (((end[p + 1] - s) * w + d) >> 8)
            s = start[p + 2]
            l0[o + 2] = s + (((end[p + 2] - s) * w + d) >> 8)
            s = start[p + 3]
            l0[o + 3] = s + (((end[p + 3] - s) * w + d) >> 8)
        neopixel_write(pin, l0)


def apply_dimmer(value):
    global dimmer
    dimmer = clamp(value, 0., 1.)

    # leds1 holds what static modes and the solar map show: fade it to the new brightness now
    # (the clocks, spin and larson pick it up with their next frame)
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


RADIAL_CORNER = 0.2  # how bright the corners look, 0..1: 0.1 a strong circle, 0.3 a soft one


def set_circular_background(color, corner=RADIAL_CORNER):
    """The whole frame in one color, like a light at its center: brightest where the edge is
    nearest, fading evenly as seen toward the corners."""
    for i in range(n):
        x, y = led_xy(i)
        k = radial_intensity(x, y, corner)
        o = i * 4
        leds1[o], leds1[o+1], leds1[o+2], leds1[o+3] = int(k * color[0]), int(k * color[1]), int(k * color[2]), int(k * color[3])
    fade()


def set_sides(north, east, south, west, linear=False, corner=RADIAL_CORNER):
    """Each side in its own color: evenly (linear), or brightest in its middle and fading evenly
    as seen toward the corners, to corner (as in set_circular_background), every side alike."""
    w2, h2 = width / 2., height / 2.
    for i in range(n):
        if i < south_west:
            color, near = south, h2
        elif i < north_west:
            color, near = west, w2
        elif i < north_east:
            color, near = north, h2
        else:
            color, near = east, w2
        if linear:
            k = 1.
        else:
            x, y = led_xy(i)
            k = radial_intensity(x, y, corner, near)
        o = i * 4
        leds1[o], leds1[o+1], leds1[o+2], leds1[o+3] = int(k * color[0]), int(k * color[1]), int(k * color[2]), int(k * color[3])

    fade()

def set_vertical(c1, c2):
    """The frame in two halves: the top (north and the upper half of the sides) in c1, the
    bottom in c2."""
    for i in range(n):
        x, y = led_xy(i)
        c = c1 if y > 0 else c2
        o = i * 4
        leds1[o], leds1[o+1], leds1[o+2], leds1[o+3] = c[0], c[1], c[2], c[3]
    fade()


def set_vertical_interp(c1, c2):
    """North in c1, south in c2, the sides a gradient between them, by height."""
    for i in range(n):
        x, y = led_xy(i)
        t = (y + height / 2.) / height  # 0 at the bottom, 1 at the top
        o = i * 4
        for k in range(4):
            leds1[o + k] = int(c2[k] + (c1[k] - c2[k]) * t)
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


def update_clock():
    global start_second, last_second
    h, m, s = utime.localtime()[3:6]
    h = (h + timing.get_cet_offset()) % 24
    if last_second != s:  # no milliseconds in utime, count manually
        start_second = utime.ticks_ms()
    last_second = s
    ms = int(clamp(utime.ticks_ms() - start_second, 0, 1000))

    if clock.update(h, m, s, ms, leds0, int(dimmer * 256)):
        neopixel_write(pin, leds0)


def spin(color, frequency):
    """A beam turning around the frame like a lighthouse's. Drawn between leds: the led ahead
    of the head lights up by how far the head has reached it, so it glides instead of jumping."""
    global last_millis, last_angle, spin_head

    now_millis = utime.ticks_ms()
    dt = utime.ticks_diff(now_millis, last_millis) / 1000.
    last_millis = now_millis

    angle = wrap_to_0_2pi(last_angle + dt * frequency * 2. * math.pi)
    last_angle = angle
    cm_on_strip, (x, y) = unwind_angle(northclockwise2math(angle))
    intensity = distance_intensity(x, y)  # dimmer where the edge is far, as the circular background
    head = cm_on_strip * leds_per_cm  # where the beam's head is, in leds, between two of them
    h = int(head)
    frac = head - h

    l0, tail = leds0, SPIN_TAIL
    if spin_head < 0:
        clear(l0)
    else:  # only last frame's beam needs clearing
        for i in range(spin_head - tail, spin_head + 2):
            o = (i % n) * 4
            l0[o] = l0[o+1] = l0[o+2] = l0[o+3] = 0
    spin_head = h

    k = intensity * int(dimmer * 256) / 256.  # the dimmer as fade() applies it
    c0, c1, c2, c3 = k * color[0], k * color[1], k * color[2], k * color[3]
    for i in range(-1, tail + 1):  # the led ahead of the head, the head, the tail
        d = frac + i  # how far behind the head this led is
        t = 1. + d if d < 0 else 1. - d / tail
        if t <= 0:
            continue
        o = ((h - i) % n) * 4
        l0[o], l0[o+1], l0[o+2], l0[o+3] = int(c0 * t), int(c1 * t), int(c2 * t), int(c3 * t)

    neopixel_write(pin, l0)


def larson_scanner(primary, secondary):
    global larson_index, larson_dir, larson_last_dir

    size = 12
    dim = int(dimmer * 256)  # its two colors at the dimmer's brightness, as fade() applies it
    primary = [(c * dim) >> 8 for c in primary]
    secondary = [(c * dim) >> 8 for c in secondary]

    init(leds0, secondary)
    leds0[larson_index * 4:larson_index * 4 + 4] = bytearray(primary)

    for i in range(size):
        b = larson_index + 1 + i
        a = larson_index - 1 - i
        t = (i+1.) / size
        fading = interpolate_rgbw(secondary, primary, 1-t)
        if larson_bounds[0] <= a and a < larson_bounds[1]:
            leds0[a * 4:a * 4 + 4] = bytearray(fading)
        if larson_bounds[0] <= b and b < larson_bounds[1]:
            leds0[b * 4:b * 4 + 4] = bytearray(fading)

    neopixel_write(pin, leds0)

    larson_last_dir = larson_dir
    larson_index += larson_dir
    if larson_dir == 1 and larson_index == larson_bounds[1] - 1:
        larson_dir = -1
    elif larson_dir == -1 and larson_index == larson_bounds[0]:
        larson_dir = 1


# ##############################################################################


def run_solunar():
    global static, equinox_or_solstice, mode
    stop_timer()  # the old mode's timer would draw between the fade's frames
    mode = 'solunar'

    # calculate once if today is equinox or solstice
    equinox_or_solstice = solunar.is_equinox_or_solstice(utime.localtime())

    paris_solunar()

    static = False
    timer.init(period=60000, mode=Timer.PERIODIC, callback=lambda t: paris_solunar())


def run_cls_clock(continuous=False):
    global static, mode
    stop_timer()
    mode = 'clock'

    clock.update_params({'mode': 'cls', 'continuous': continuous})
    clock.set_background_colors(color_ambient, color_river)
    clock.set_hand_colors([26, 26, 0, 127], [60, 0, 40, 0], color_accent)

    timing.update_time()

    clock.last_second = -1  # so the first frame draws
    fade_in(update_clock)
    static = False
    timer.init(period=100, mode=Timer.PERIODIC, callback=lambda t: update_clock())


def run_neo_clock(start_at_minute=False, two_colors=False, ambient=False):
    global static, mode
    stop_timer()
    mode = 'clock'

    clock.update_params({'mode': 'neo',
                         'start_at_minute': start_at_minute,
                         'two_colors': two_colors,
                         'ambient': ambient})

    if ambient:
        clock.set_background_colors(color_ambient, color_sweep)
        clock.set_hand_colors([26, 26, 0, 127], [60, 0, 40, 0], color_accent)
    else:
        first = colors.random_saturated()  # a random pair to start with
        clock.set_background_colors(first, colors.random_saturated_2(first))

    timing.update_time()
    s = utime.localtime()[5]  # seconds
    while True:  # wait for the next full second
        if utime.localtime()[5] != s:
            clock.last_minute = utime.localtime()[4]  # prevents color update on first neo draw
            break
        utime.sleep_ms(10)

    fade_in(update_clock)
    static = False
    timer.init(period=100, mode=Timer.PERIODIC, callback=lambda t: update_clock())


def run_spin(color, frequency=0.25):
    global static, last_millis, spin_head
    stop_timer()

    last_millis = utime.ticks_ms()
    spin_head = -1  # the first frame draws the whole strip
    fade_in(lambda: spin(color, frequency))
    last_millis = utime.ticks_ms()  # turn on from the faded-in frame, not a second ahead
    static = False
    timer.init(period=SPIN_FRAME_MS, mode=Timer.PERIODIC, callback=lambda t: spin(color, frequency))


def run_larson_scanner(cardinal, primary, secondary):
    global static, larson_bounds, larson_index, larson_dir, larson_last_dir
    stop_timer()

    larson_bounds = cardinals[cardinal][2]
    larson_index = larson_bounds[0]
    larson_dir = 1
    larson_last_dir = -1

    n_leds = cardinals[cardinal][1]
    seconds = 2.
    dt = seconds / n_leds * 1000.

    fade_in(lambda: larson_scanner(primary, secondary))
    static = False
    timer.init(period=int(round(dt)), mode=Timer.PERIODIC, callback=lambda t: larson_scanner(primary, secondary))


def stop_timer():
    global static, mode
    mode = None
    static = True  # back to static mode; leds0 holds what's shown, the next fade starts there
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


# the modes to switch between, by name (see show)
MODES = {
    'solunar': run_solunar,        # ()
    'clock': run_cls_clock,        # (continuous)
    'neo': run_neo_clock,          # (start_at_minute, two_colors, ambient)
    'off': off,                    # ()
    'sides': set_sides,            # (north, east, south, west, linear, corner)
    'radial': set_circular_background,  # (color, corner)
    'vertical': set_vertical,      # (top, bottom)
    'vertical_interp': set_vertical_interp,  # (top, bottom)
    'spin': run_spin,              # (color, frequency)
    'larson': run_larson_scanner,  # (cardinal, primary, secondary)
}


def show(name, *args):
    """Switch to a mode by name, e.g. show('clock', True): stops whatever runs, then starts the
    mode with its fade. The one call the web app needs; the functions above are the parts."""
    stop_timer()
    gc.collect()  # what the webrepl left behind, before the mode allocates
    MODES[name](*args)


def start():
    """Boot animation, shown while wifi and ntp are still connecting."""
    paris(leds1)
    ramp_up()


def run(is_online):
    if is_online:
        run_solunar()
    else:
        set_sides((0, 0, 0, 0), (50, 50, 0, 80), (0, 0, 0, 0), (50, 50, 0, 80), False)
