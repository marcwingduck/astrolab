import machine
import network
import utime

import timing
import paris


def read_env(path='.env'):
    """KEY=VALUE lines into a dict; skips blank lines and comments, strips quotes."""
    env = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, value = line.split('=', 1)
                value = value.strip()
                if len(value) > 1 and value[0] == value[-1] and value[0] in '"\'':
                    value = value[1:-1]
                env[key.strip()] = value
    except OSError:
        pass
    return env


def connect(env):
    ssid = env.get('WIFI_SSID')
    if not ssid:
        return False

    sta_if = network.WLAN(network.STA_IF)
    if not sta_if.isconnected():
        # print('connecting to network...')
        sta_if.active(True)
        sta_if.connect(ssid, env.get('WIFI_PASSWORD', ''))
        deadline = utime.ticks_add(utime.ticks_ms(), 10000)
        while not sta_if.isconnected():
            machine.idle()
            if utime.ticks_diff(deadline, utime.ticks_ms()) < 0:
                break
        else:
            print('network config:', sta_if.ifconfig())
    return sta_if.isconnected()


def init(env):
    return connect(env) and timing.update_time()


if __name__ == '__main__':
    machine.freq(160000000)
    paris.start()
    is_online = init(read_env())
    ap_if = network.WLAN(network.AP_IF)
    if is_online:
        ap_if.active(False)
    else:
        ap_if.active(True)
    paris.run(is_online)
