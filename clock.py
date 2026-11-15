import math
import colors
from common import *
from frame import *


class Clock:
    def __init__(self):
        self.last_minute = -1
        self.last_second = -1

        # cls clock
        self.color_h = [26, 26, 0, 127]
        self.color_m = [60, 0, 40, 0]
        self.color_s = [38, 215, 56, 0]

        # neo clock
        self.color_1 = colors.colors['cyan'][:]
        self.color_2 = colors.colors['orange'][:]
        self.color_old_hands = self.color_2[:]
        self.color_new_hands = self.color_1[:]

        # the colors above at the dimmer's brightness, worked out each frame (see dim)
        self.dim_1, self.dim_2 = bytearray(4), bytearray(4)
        self.dim_old_hands, self.dim_new_hands = bytearray(4), bytearray(4)
        self.dim_h, self.dim_m, self.dim_s = bytearray(4), bytearray(4), bytearray(4)

        self.params = {
            'mode': 'cls',
            # for cls clock
            'continuous': True,
            # for neo clock
            'start_at_minute': True,
            'two_colors': True,
            'ambient': True
        }

    def set_background_colors(self, c1, c2):
        self.color_1[:] = list(c1)
        self.color_2[:] = list(c2)
        self.color_old_hands[:] = self.color_2
        self.color_new_hands[:] = self.color_1

    def set_hand_colors(self, c1, c2, c3):
        self.color_h = list(c1)
        self.color_m = list(c2)
        self.color_s = list(c3)

    def replace_color(self, old, new):
        """Swap one color for another wherever the clock uses it, keeping the neo clock's
        current state (it trades its two colors every minute)."""
        old, new = list(old), list(new)
        for c in (self.color_1, self.color_2, self.color_old_hands, self.color_new_hands,
                  self.color_h, self.color_m, self.color_s):
            if c == old:
                c[:] = new

    def dim(self, dim):
        """Work out the colors to draw with at dim/256 brightness, as fade() dims the map, so a
        clock and the map look alike. Once per frame: a handful of colors, not every led."""
        for src, dst in ((self.color_1, self.dim_1), (self.color_2, self.dim_2),
                         (self.color_old_hands, self.dim_old_hands), (self.color_new_hands, self.dim_new_hands),
                         (self.color_h, self.dim_h), (self.color_m, self.dim_m), (self.color_s, self.dim_s)):
            for k in range(4):
                dst[k] = (src[k] * dim) >> 8

    def update_params(self, params):
        for k, v in params.items():
            self.params[k] = v

    def update(self, h, m, s, ms, leds, dim=256):
        '''
        Parameters:
        ----------------
        h : int
            hours
        m : int
            minutes
        s : int
            seconds
        ms : int
            millis
        dim : int
            brightness, 256 is full (the dimmer, as fade() applies it)

        Returns:
        -----------------
        bool :
            wether repaint is necessary or not
        '''

        frac_s = s + ms/1000.
        frac_m = m + frac_s/60.
        frac_h = h % 12 + frac_m/60.

        minute_changed = m != self.last_minute
        second_changed = s != self.last_second

        repaint = False

        if self.params['mode'] == 'neo':
            self.neo(frac_h, frac_m, frac_s, leds, minute_changed, dim)
            repaint = True
        elif self.params['continuous'] or second_changed:
            self.cls(frac_h, frac_m, frac_s, leds, dim)
            repaint = True

        self.last_minute = m
        self.last_second = s

        return repaint

    def cls(self, h, m, s, leds, dim=256):
        """
        Classic Clock
        """
        self.dim(dim)

        a_h = h / 12. * 2. * math.pi
        a_m = m / 60. * 2. * math.pi
        a_s = s / 60. * 2. * math.pi

        h_dist = unwind_angle(northclockwise2math(a_h))[0]
        m_dist = unwind_angle(northclockwise2math(a_m))[0]
        s_dist = unwind_angle(northclockwise2math(a_s))[0]

        # leds[:] = bytearray(n * list(colors.color_ambient)) # <-- extra right-hand side allocation fails due to memory issues
        background = self.dim_1
        for i in range(n):
            leds[i*4:i*4+4] = background

        set_area2(m_dist, 6, self.dim_m, leds)
        set_area2(h_dist, 8, self.dim_h, leds)
        set_area2(s_dist, 1, self.dim_s, leds)

        # smooth two-led second hand
        # fraction_led = s_dist * leds_per_cm
        # frac, frac_led_index = math.modf(fraction_led)
        # frac_led_index = int(frac_led_index)
        # id0 = frac_led_index * 4
        # id1 = ((frac_led_index + 1) % n) * 4
        # leds[id0:id0+4] = bytearray(interpolate_rgbw(self.color_s, leds[id0:id0+4], frac))
        # leds[id1:id1+4] = bytearray(interpolate_rgbw(leds[id1:id1+4], self.color_s, frac))

    def neo(self, h, m, s, leds, change_color, dim=256):
        """
        Neo(n) Clock
        """

        if change_color:  # switch colors
            self.color_old_hands[:] = self.color_1
            self.color_new_hands[:] = self.color_2
            tmp = self.color_1[:]
            self.color_1[:] = self.color_2
            if self.params['two_colors']:
                self.color_2[:] = tmp
            else:  # random neo mode
                self.color_2[:] = list(colors.random_saturated_2(self.color_1))
        self.dim(dim)  # after the swap, so the dimmed colors follow it

        if self.params['start_at_minute']:  # start seconds at minute hand
            m_h = int(m) / 60. * 2. * math.pi
            m_i = int(unwind_angle(northclockwise2math(m_h))[0] * leds_per_cm)
            start = m_i
        else:  # start seconds at at 12 o'clock
            m_h = m / 60. * 2. * math.pi
            m_i = int(unwind_angle(northclockwise2math(m_h))[0] * leds_per_cm)
            start = int(unwind_angle(northclockwise2math(0))[0] * leds_per_cm)

        a_h = h / 12. * 2. * math.pi
        h_i = int(unwind_angle(northclockwise2math(a_h))[0] * leds_per_cm)

        fraction_led = s / 60. * n
        frac, frac_led_index = math.modf(fraction_led)
        n_leds = int(frac_led_index)  # number of seconds leds (from top to seconds hand if not linear, else from start)
        frac_led_index = (start + n_leds) % n

        h_hand_range = range(h_i-5, h_i+5)
        m_hand_range = range(m_i-3, m_i+3)
        if self.params['start_at_minute']:
            h_hand_range = range(h_i-3, h_i+3)

        for i in range(start, start + n):
            a_i = i % n
            is_hand = a_i in h_hand_range or a_i in m_hand_range and not self.params['start_at_minute']
            if i < start + n_leds:  # seconds passed
                icolor = self.dim_2 if not is_hand else self.dim_new_hands
            elif i > start + n_leds:  # seconds to be passed
                icolor = self.dim_1 if not is_hand else self.dim_old_hands
            elif is_hand:  # frac_led_index and hand (partially lit)
                icolor = bytearray(interpolate_rgbw(self.dim_old_hands, self.dim_new_hands, frac))
            else:  # frac_led_index and not a hand (partially lit)
                icolor = bytearray(interpolate_rgbw(self.dim_1, self.dim_2, frac))
            leds[a_i * 4:a_i * 4 + 4] = icolor
