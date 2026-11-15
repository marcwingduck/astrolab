import utime
import random

h, m, s = utime.localtime()[3:6]
random.seed(int(str(h) + str(m) + str(s)))

# Colors as the strip takes them: 4 bytes each, G, R, B, W. Names only as comments, to keep them
# out of the board's RAM; color(TABLE, i) picks one.

# full colors, for the neo clock's random mode
SATURATED = bytes((
      0, 255,   0, 0,  # red                ff0000
    136, 255,   0, 0,  # orange             ff8800
    255, 255,   0, 0,  # yellow             ffff00
    255, 136,   0, 0,  # grass              88ff00
    255,   0,   0, 0,  # green              00ff00
    255,   0, 136, 0,  # mermaid            00ff88
    255,   0, 255, 0,  # cyan               00ffff
    136,   0, 255, 0,  # sky                0088ff
      0,   0, 255, 0,  # blue               0000ff
      0, 136, 255, 0,  # purple             8800ff
      0, 255, 255, 0,  # magenta            ff00ff
      0, 255, 136, 0,  # rose               ff0088
))

# accents that go well with the frame
ACCENTS = bytes((
    170,   0, 255, 0,  # river_blue         00aaff
    136, 255,  17, 0,  # giants_orange      ff8811
      0, 241, 254, 0,  # fuchsia            f100fe
    147, 254, 140, 0,  # coral_pink         fe938c
     86, 255,  25, 0,  # coral              ff5619
    204, 255, 145, 0,  # yellow             ffcc91
     86, 247, 124, 0,  # bright_pink        f7567c
     82, 156, 139, 0,  # plum               9c528b
    145, 236, 216, 0,  # plum_web           ec91d8
     73, 255, 158, 0,  # rose_bonbon        ff499e
    185,  76,  68, 0,  # dark_pastel_green  4cb944
     38, 215,  56, 0,  # crimson            d72638
))

RIVER_BLUE = ACCENTS[0:4]


def color(table, i):
    return table[i * 4:i * 4 + 4]


def hex2grb0(h):
    h = h.lstrip('#')
    x = [int(h[i:i+2], 16) for i in (2, 0, 4)]
    x.append(0)
    return x

# as bytes: a quarter of the memory of a list
gamma = bytes([0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
         0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1,
         1, 1, 1, 1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 2, 2,
         2, 3, 3, 3, 3, 3, 3, 3, 4, 4, 4, 4, 4, 5, 5, 5,
         5, 6, 6, 6, 6, 7, 7, 7, 7, 8, 8, 8, 9, 9, 9, 10,
         10, 10, 11, 11, 11, 12, 12, 13, 13, 13, 14, 14, 15, 15, 16, 16,
         17, 17, 18, 18, 19, 19, 20, 20, 21, 21, 22, 22, 23, 24, 24, 25,
         25, 26, 27, 27, 28, 29, 29, 30, 31, 32, 32, 33, 34, 35, 35, 36,
         37, 38, 39, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 50,
         51, 52, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 66, 67, 68,
         69, 70, 72, 73, 74, 75, 77, 78, 79, 81, 82, 83, 85, 86, 87, 89,
         90, 92, 93, 95, 96, 98, 99, 101, 102, 104, 105, 107, 109, 110, 112, 114,
         115, 117, 119, 120, 122, 124, 126, 127, 129, 131, 133, 135, 137, 138, 140, 142,
         144, 146, 148, 150, 152, 154, 156, 158, 160, 162, 164, 167, 169, 171, 173, 175,
         177, 180, 182, 184, 186, 189, 191, 193, 196, 198, 200, 203, 205, 208, 210, 213,
         215, 218, 220, 223, 225, 228, 231, 233, 236, 239, 241, 244, 247, 249, 252, 255])


def random_saturated():
    return color(SATURATED, random.getrandbits(8) % (len(SATURATED) // 4))


def random_saturated_2(color_1):
    color_2 = random_saturated()
    for _ in range(3):  # make sure to terminate
        dist = sum([abs(a-b) for a, b in zip(color_1, color_2)])
        # i know this is very primitive and does not incorporate human color
        # perception but it prevents sequencing of colors that are too similar
        # (e.g. yellow/orange).
        if dist < 255+127:
            color_2 = random_saturated()
    return color_2
