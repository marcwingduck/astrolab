"""
Tests and demos for the web app's Tests section. Kept out of paris.py so they only take the
board's scarce RAM while they run: the web app imports this module on demand.
"""

from paris import *


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


def clock_demo():
    for h in range(24):
        for m in range(0, 60):
            for s in range(0, 60):
                for ms in range(0, 1000, 250):
                    clock.update(h, m, s, ms, leds0)
                    neopixel_write(pin, leds0)


# ##############################################################################
