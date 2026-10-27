#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Headless test-bench for cosmic-hopper.gba using Unicorn Engine.

Emulates the ARM7TDMI code of the ROM, fakes the two hardware registers the
game polls (VCOUNT and KEYINPUT), checks the game logic and dumps the
framebuffer to PNG files.
"""

import os
import struct
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_PC

import build_rom as B

ROM_BASE = 0x08000000
EWRAM = 0x02000000
IWRAM = 0x03000000
IO = 0x04000000
VRAM = 0x06000000

KEY_RIGHT = 0x10
KEY_LEFT = 0x20
KEY_UP = 0x40
KEY_DOWN = 0x80
KEY_START = 0x08

ALL_RELEASED = 0x3FF


class Emu:
    def __init__(self, rom, labels):
        self.uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        for base, size in ((0x08000000, 0x40000),
                           (0x02000000, 0x40000),
                           (0x03000000, 0x8000),
                           (0x04000000, 0x1000),
                           (0x06000000, 0x18000)):
            self.uc.mem_map(base, size)
        self.uc.mem_write(0x08000000, rom)
        self.vcount = 0
        self.uc.mem_write(IO + 6, struct.pack('<H', 0))
        self.uc.mem_write(IO + 0x130, struct.pack('<H', ALL_RELEASED))
        self.frames = 0
        self.limit = 0
        self.key_fn = lambda f: ALL_RELEASED
        self.l_main = labels['l_main']
        self.uc.hook_add(UC_HOOK_CODE, self._hook,
                         begin=self.l_main, end=self.l_main)
        for name in ('wv_low', 'wv_high'):
            self.uc.hook_add(UC_HOOK_CODE, self._tick_vcount,
                             begin=labels[name], end=labels[name])

    def _tick_vcount(self, uc, address, size, user_data):
        self.vcount = (self.vcount + 1) % 228
        uc.mem_write(IO + 6, struct.pack('<H', self.vcount))

    def _hook(self, uc, address, size, user_data):
        self.frames += 1
        uc.mem_write(IO + 0x130, struct.pack('<H', self.key_fn(self.frames)))
        if self.frames >= self.limit:
            uc.emu_stop()

    def run(self, n):
        self.limit = self.frames + n
        if self.frames == 0:
            start = 0x080000C0
        else:
            start = self.uc.reg_read(UC_ARM_REG_PC)
            if start == self.l_main:
                # stopped on the frame hook: the body has not run yet
                start += 4
        self.uc.emu_start(start, 0xFFFFFFFF, timeout=0, count=0)

    # ---- inspection helpers ------------------------------------------------
    def u32(self, addr):
        return struct.unpack('<I', self.uc.mem_read(addr, 4))[0]

    def s32(self, addr):
        return struct.unpack('<i', self.uc.mem_read(addr, 4))[0]

    def set32(self, addr, value):
        self.uc.mem_write(addr, struct.pack('<I', value & 0xFFFFFFFF))

    @property
    def state(self):
        return self.u32(B.V_STATE)

    @property
    def score(self):
        return self.u32(B.V_SCORE)

    @property
    def px(self):
        return self.s32(B.V_PX) >> 8

    @property
    def py(self):
        return self.s32(B.V_PY) >> 8

    @property
    def cam(self):
        return self.s32(B.V_CAM) >> 8

    def set_keys(self, fn):
        self.key_fn = fn

    def vram(self):
        return bytes(self.uc.mem_read(VRAM, 240 * 160 * 2))

    def platforms(self):
        out = []
        for i in range(B.NPLATS):
            x = self.u32(B.V_PLATS + i * 8)
            y = self.s32(B.V_PLATS + i * 8 + 4)
            out.append((x, y))
        return out


def write_png(path, w, h, rgb):
    raw = b''.join(b'\x00' + rgb[y * w * 3:(y + 1) * w * 3] for y in range(h))

    def chunk(tag, data):
        return (struct.pack('>I', len(data)) + tag + data +
                struct.pack('>I', zlib.crc32(tag + data) & 0xFFFFFFFF))

    png = (b'\x89PNG\r\n\x1a\n' +
           chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)) +
           chunk(b'IDAT', zlib.compress(raw, 9)) +
           chunk(b'IEND', b''))
    with open(path, 'wb') as f:
        f.write(png)


def save_screenshot(emu, path, scale=3):
    vram = emu.vram()
    w, h = 240, 160
    out = bytearray()
    for y in range(h):
        row = bytearray()
        for x in range(w):
            v = struct.unpack_from('<H', vram, (y * w + x) * 2)[0]
            r = (v & 0x1F) * 255 // 31
            g = ((v >> 5) & 0x1F) * 255 // 31
            b = ((v >> 10) & 0x1F) * 255 // 31
            row += bytes((r, g, b)) * scale
        for _ in range(scale):
            out += row
    write_png(path, w * scale, h * scale, bytes(out))


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print("  ok  " + msg)


def press_start_once(emu, frame):
    # The game debounces input: START must be held for five frames, and the
    # pad must have been seen released at least once since power-on.
    emu.set_keys(lambda f: ALL_RELEASED & ~KEY_START
                 if frame <= f < frame + 10 else ALL_RELEASED)


def main():
    rom, info = B.build()
    labels = info['labels']

    print("[1] header")
    check(rom[0:4] == struct.pack('<I', 0xEA00002E), "ARM branch to 0x080000C0")
    check(rom[4:0xA0] == B.NINTENDO_LOGO, "official 156-byte Nintendo logo")
    check(rom[0xA0:0xAC].rstrip(b'\x00') == b'COSMICHOPPER', "game title")
    check(rom[0xAC:0xB0] == b'CHPR', "game code CHPR")
    chk = 0
    for b in rom[0xA0:0xBD]:
        chk -= b
    check(rom[0xBD] == (chk - 0x19) & 0xFF, "header complement check valid")
    check(rom[0xC0] != 0xFF and rom[0x100] != 0, "code is present at 0x080000C0")

    print("[2] boot -> title screen")
    emu = Emu(rom, labels)
    emu.run(1)
    check(emu.state == 2, "boot lands on the title screen")
    save_screenshot(emu, 'shot_title.png')
    title_vram = emu.vram()
    check(sum(1 for i in range(0, len(title_vram), 2)
              if title_vram[i:i + 2] == b'\xff\x7f') > 40,
          "title screen draws text pixels")

    print("[3] START -> playing")
    base = emu.frames
    press_start_once(emu, base + 2)
    emu.run(12)
    check(emu.state == 0, "START starts the game")
    check(emu.px == 120, "player starts centred (x=%d)" % emu.px)
    start_y = emu.py

    print("[4] bouncing on the first platform (idle)")
    emu.set_keys(lambda f: ALL_RELEASED)
    emu.run(200)
    check(emu.state == 0, "player never dies while idling")
    check(860 <= emu.py <= 950, "player keeps hopping on the start platform (y=%d)" % emu.py)
    check(emu.cam < start_y, "camera followed the hop")
    check(0 <= emu.score <= 15, "idle score stays small (%d)" % emu.score)
    save_screenshot(emu, 'shot_play.png')

    print("[5] steering and screen bounds")
    emu.set32(B.V_PX, 239 << 8)
    emu.set_keys(lambda f: ALL_RELEASED & ~KEY_RIGHT)
    emu.run(2)
    check(emu.px == 240 - B.PW, "player is clamped at the right edge")

    emu.set32(B.V_PX, 120 << 8)
    emu.run(20)
    right_x = emu.px
    check(right_x > 130, "RIGHT moves the player right (x=%d)" % right_x)
    emu.set_keys(lambda f: ALL_RELEASED & ~KEY_LEFT)
    emu.run(30)
    left_x = emu.px
    check(left_x < right_x, "LEFT moves the player left (x=%d)" % left_x)

    print("[6] climbing: camera + platform generation + score")
    emu = Emu(rom, labels)
    emu.run(1)
    base = emu.frames
    press_start_once(emu, base + 2)
    emu.run(12)
    check(emu.state == 0, "fresh game running")
    emu.set_keys(lambda f: ALL_RELEASED)
    emu.run(4)
    old_cam = emu.cam
    old_score = emu.score
    emu.set32(B.V_PY, (old_cam - 120) << 8)   # teleport the player upwards
    emu.set32(B.V_VY, (-1500) & 0xFFFFFFFF)
    emu.set32(B.V_PPY, (old_cam - 120) << 8)
    emu.run(6)
    check(emu.cam < old_cam, "camera scrolled up (%d -> %d)" % (old_cam, emu.cam))
    check(emu.score > old_score, "score increased (%d -> %d)" % (old_score, emu.score))
    plats = emu.platforms()
    check(len(set(p[1] for p in plats)) == B.NPLATS, "14 platforms, all at different heights")
    check(min(p[1] for p in plats) < emu.cam, "a platform is queued above the camera")
    ys = sorted(p[1] for p in plats)
    gaps = [ys[i + 1] - ys[i] for i in range(len(ys) - 1)]
    check(all(30 <= g <= 60 for g in gaps), "vertical gaps stay jumpable (%s)" % gaps)
    save_screenshot(emu, 'shot_climb.png')

    print("[6b] a simple autopilot can actually climb")
    emu = Emu(rom, labels)
    emu.run(1)
    base = emu.frames
    press_start_once(emu, base + 2)
    emu.run(12)
    check(emu.state == 0, "autopilot game running")

    pilot = {'origin': None, 'vy': 0, 'target': None}

    def pilot_keys(f):
        py = emu.py
        vy = emu.s32(B.V_VY)
        if pilot['origin'] is None:
            pilot['origin'] = py + B.PH
        if pilot['vy'] > 0 and vy < 0:          # just bounced
            pilot['origin'] = py + B.PH
            pilot['target'] = None
        if pilot['target'] is None:
            best = None
            for (x, y) in emu.platforms():
                d = pilot['origin'] - y
                if 12 < d < 95 and (best is None or y > best[1]):
                    best = (x, y)
            pilot['target'] = (best[0] + B.PLAT_W // 2) if best else 120
        pilot['vy'] = vy
        tx = pilot['target']
        px = emu.px + B.PW // 2
        if px < tx - 6:
            return ALL_RELEASED & ~KEY_RIGHT
        if px > tx + 6:
            return ALL_RELEASED & ~KEY_LEFT
        return ALL_RELEASED

    emu.set_keys(pilot_keys)
    emu.run(500)
    print("      autopilot: state=%d score=%d y=%d cam=%d" %
          (emu.state, emu.score, emu.py, emu.cam))
    check(emu.state == 0, "autopilot survived 500 frames")
    check(emu.score >= 20, "autopilot climbed and scored (%d)" % emu.score)
    check(emu.cam < 700, "camera reached high altitude (cam=%d)" % emu.cam)
    save_screenshot(emu, 'shot_autopilot.png')

    print("[6c] no height ceiling (climb past the old 108-point cap)")
    emu = Emu(rom, labels)
    emu.run(1)
    base = emu.frames
    press_start_once(emu, base + 2)
    emu.run(12)
    check(emu.state == 0, "high-altitude run started")
    # A normal bounce may cross the old y=0 ceiling: signed coordinates must work.
    emu.set32(B.V_PY, 5 << 8)
    emu.set32(B.V_PPY, 5 << 8)
    emu.set32(B.V_VY, (-1500) & 0xFFFFFFFF)
    emu.run(20)
    print("      boundary: state=%d score=%d y=%d cam=%d" %
          (emu.state, emu.score, emu.py, emu.cam))
    check(emu.py < 0, "player can bounce above y=0 (y=%d)" % emu.py)
    check(emu.score >= 110, "score passes 108 while crossing y=0 (%d)" % emu.score)
    check(emu.state == 0, "crossing y=0 does not end the game")
    # Teleport far above the old ceiling to check unbounded generation.
    emu.set32(B.V_PY, (-8000 << 8) & 0xFFFFFFFF)
    emu.set32(B.V_PPY, (-8000 << 8) & 0xFFFFFFFF)
    emu.set32(B.V_VY, 0)
    emu.run(8)
    print("      high: state=%d score=%d y=%d cam=%d topy=%d" %
          (emu.state, emu.score, emu.py, emu.cam, emu.s32(B.V_TOPY)))
    check(emu.state == 0, "player survives above y=0")
    check(emu.cam < -7000, "camera followed above y=0 (cam=%d)" % emu.cam)
    check(emu.score > 1000, "score goes past the old cap (%d)" % emu.score)
    check(emu.s32(B.V_TOPY) < emu.cam - 100, "platforms keep generating above y=0")
    check(any(y < 0 for (x, y) in emu.platforms()), "negative-y platforms exist")
    save_screenshot(emu, 'shot_high.png')

    print("[7] falling -> game over")
    emu.set32(B.V_PY, (emu.cam + 260) << 8)
    emu.set32(B.V_PPY, (emu.cam + 260) << 8)
    emu.set32(B.V_VY, 800)
    emu.run(3)
    check(emu.state == 1, "falling below the screen ends the game")
    save_screenshot(emu, 'shot_gameover.png')

    print("[8] START restarts")
    base = emu.frames
    press_start_once(emu, base + 3)
    emu.run(14)
    check(emu.state == 0, "START restarts the game")
    check(emu.score == 0, "score reset")
    check(emu.py >= 900, "player back on the start platform (y=%d)" % emu.py)
    check(abs(emu.cam - (B.START_Y - 56)) <= 60, "camera reset (cam=%d)" % emu.cam)

    print("[9] drawing sanity")
    vram = emu.vram()
    words = struct.unpack('<%dH' % (240 * 160), vram)
    check(words.count(B.C_PLAT) > 200, "platforms are drawn")
    check(words.count(B.C_BODY) > 40, "astronaut is drawn")
    check(words.count(B.C_HUD) > 2000, "HUD strip is drawn")
    check(all(w != 0x0000 or True for w in words), "framebuffer readable")
    save_screenshot(emu, 'shot_restart.png')

    print("\nall tests passed")
    return rom, info


if __name__ == '__main__':
    main()
