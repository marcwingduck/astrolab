import ntptime
import utime


def update_time(attempts=5):
    """Set the clock from ntp. Returns False if no server answered."""
    for _ in range(attempts):
        try:
            ntptime.settime()
            return True
        except OSError:
            utime.sleep_ms(500)
    return False


def get_cet_offset():
    """Return UTC offset for Central European Time: 2 (CEST) or 1 (CET).
    CEST: last Sunday of March 01:00 UTC -> last Sunday of October 01:00 UTC."""
    year = utime.localtime()[0]
    # last Sunday of March / October (31st minus weekday offset)
    # utime weekday: 0=Mon, 6=Sun
    mar_last_sun = 31 - (utime.localtime(utime.mktime((year, 3, 31, 0, 0, 0, 0, 0)))[6] + 1) % 7
    oct_last_sun = 31 - (utime.localtime(utime.mktime((year, 10, 31, 0, 0, 0, 0, 0)))[6] + 1) % 7
    # transition timestamps at 01:00 UTC
    cest_start = utime.mktime((year, 3, mar_last_sun, 1, 0, 0, 0, 0))
    cest_end = utime.mktime((year, 10, oct_last_sun, 1, 0, 0, 0, 0))
    now = utime.time()
    return 2 if cest_start <= now < cest_end else 1
