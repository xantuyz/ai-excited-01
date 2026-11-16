#!/usr/bin/env python3
"""ai-excited-01 — Frame-Break Koi (round 3).

Entrypoint for the make.fun "Make the AI judge excited" bounty.

This program *draws* the entry image from scratch at runtime — no
pre-rendered pixels are bundled. A tiny software rasterizer (circles,
ellipses, polygons, bezier spines, gradients) paints a 1024x1024 scene
and a hand-rolled PNG encoder writes it out.

The scene: a giant orange-and-white koi bursts out of its gilt-framed
ukiyo-e painting into a quiet museum gallery. The fish arcs out of the
painting, smashing through the bottom of the frame — gold splinters
flying, water exploding onto the floor, ripples spreading — while two
tiny visitors duck for cover. The impossible moment, frozen mid-leap.

Standard library only. No network, no timestamps in the output, and a
single fixed seed drives every "random" splash droplet, splinter and
grain speck — two runs always produce byte-identical PNGs.

Usage:
    python3 main.py                 # writes entry.png next to main.py
    MAKEFUN_OUTPUT_DIR=out python3 main.py   # writes out/entry.png

The written file is validated in-process before the program reports
success: PNG signature, IHDR dimensions, every chunk CRC, IEND
trailer present with no trailing bytes.
"""

import hashlib
import math
import os
import random
import struct
import sys
import zlib

WIDTH = 1024
HEIGHT = 1024
OUTPUT_NAME = "entry.png"
SEED = 20261116
MAX_SIZE = 1024 * 1024  # 1 MiB, the competition's file cap

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


# ---------------------------------------------------------------- colors

WALL_TOP = (246, 236, 215)
WALL_BOTTOM = (233, 214, 174)
FLOOR_TOP = (185, 141, 95)
FLOOR_BOTTOM = (138, 95, 54)
BASEBOARD = (120, 90, 60)
GOLD = (176, 141, 44)
GOLD_LIGHT = (226, 190, 90)
GOLD_DARK = (110, 84, 26)
GOLD_EDGE = (96, 74, 26)
PAINT_TOP = (18, 58, 92)
PAINT_BOTTOM = (10, 47, 78)
WAVE = (165, 205, 232)
MOON = (250, 244, 214)
CLOUD = (240, 246, 250)
KOI_WHITE = (250, 246, 238)
KOI_ORANGE = (238, 110, 38)
KOI_DEEP = (214, 82, 20)
KOI_RIM = (200, 100, 45)
KOI_DARK = (150, 80, 45)
SPLASH = (245, 252, 255)
SPLASH_BLUE = (205, 232, 244)
VISITOR = (38, 42, 61)
SEAL_RED = (178, 34, 34)
REED = (52, 120, 78)


def lerp(a, b, t):
    return a + (b - a) * t


def lerp_color(c1, c2, t):
    return (round(lerp(c1[0], c2[0], t)),
            round(lerp(c1[1], c2[1], t)),
            round(lerp(c1[2], c2[2], t)))


def clamp_byte(v):
    return 0 if v < 0 else 255 if v > 255 else v


# ---------------------------------------------------------------- canvas

class Canvas:
    """A flat RGB buffer with a small set of filled-shape primitives."""

    def __init__(self, width, height):
        self.w = width
        self.h = height
        self.buf = bytearray(width * height * 3)
        self.clip = (0, 0, width, height)

    def set_clip(self, x0, y0, x1, y1):
        self.clip = (max(0, x0), max(0, y0),
                     min(self.w, x1), min(self.h, y1))

    def reset_clip(self):
        self.clip = (0, 0, self.w, self.h)

    def _hline(self, x0, x1, y, rgb, alpha=255):
        cx0, cy0, cx1, cy1 = self.clip
        if y < cy0 or y >= cy1:
            return
        x0 = max(x0, cx0)
        x1 = min(x1, cx1 - 1)
        if x1 < x0:
            return
        base = (y * self.w + x0) * 3
        n = x1 - x0 + 1
        if alpha >= 255:
            self.buf[base:base + n * 3] = bytes(rgb) * n
        else:
            inv = 255 - alpha
            r, g, b = rgb
            buf = self.buf
            for i in range(base, base + n * 3, 3):
                buf[i] = (r * alpha + buf[i] * inv) // 255
                buf[i + 1] = (g * alpha + buf[i + 1] * inv) // 255
                buf[i + 2] = (b * alpha + buf[i + 2] * inv) // 255

    def _px(self, x, y, rgb, alpha=255):
        cx0, cy0, cx1, cy1 = self.clip
        if not (cx0 <= x < cx1 and cy0 <= y < cy1):
            return
        i = (y * self.w + x) * 3
        if alpha >= 255:
            self.buf[i] = rgb[0]
            self.buf[i + 1] = rgb[1]
            self.buf[i + 2] = rgb[2]
        else:
            inv = 255 - alpha
            self.buf[i] = (rgb[0] * alpha + self.buf[i] * inv) // 255
            self.buf[i + 1] = (rgb[1] * alpha + self.buf[i + 1] * inv) // 255
            self.buf[i + 2] = (rgb[2] * alpha + self.buf[i + 2] * inv) // 255

    def fill_rect(self, x0, y0, x1, y1, rgb, alpha=255):
        for y in range(y0, y1):
            self._hline(x0, x1 - 1, y, rgb, alpha)

    def vgrad_rect(self, x0, y0, x1, y1, top, bottom):
        span = max(1, y1 - y0 - 1)
        for y in range(y0, y1):
            self._hline(x0, x1 - 1, y, lerp_color(top, bottom, (y - y0) / span))

    def fill_circle(self, cx, cy, r, rgb, alpha=255):
        r = int(round(r))
        if r < 0:
            return
        for y in range(cy - r, cy + r + 1):
            dy = y - cy
            dx = int(math.sqrt(max(0, r * r - dy * dy)))
            self._hline(cx - dx, cx + dx, y, rgb, alpha)

    def fill_ellipse(self, cx, cy, rx, ry, rgb, alpha=255):
        if rx <= 0 or ry <= 0:
            return
        for y in range(cy - ry, cy + ry + 1):
            dy = (y - cy) / ry
            dx = int(rx * math.sqrt(max(0.0, 1.0 - dy * dy)))
            self._hline(cx - dx, cx + dx, y, rgb, alpha)

    def fill_ellipse_rot(self, cx, cy, rx, ry, angle_deg, rgb, alpha=255):
        """Rotated ellipse; per-pixel, so use only for small shapes."""
        ang = math.radians(angle_deg)
        ca, sa = math.cos(ang), math.sin(ang)
        br = int(math.ceil(math.hypot(rx, ry))) + 1
        cx0, cy0, cx1, cy1 = self.clip
        for y in range(max(cy - br, cy0), min(cy + br + 1, cy1)):
            for x in range(max(cx - br, cx0), min(cx + br + 1, cx1)):
                dx, dy = x - cx, y - cy
                u = dx * ca + dy * sa
                v = -dx * sa + dy * ca
                if (u / rx) ** 2 + (v / ry) ** 2 <= 1.0:
                    self._px(x, y, rgb, alpha)

    def ring(self, cx, cy, r, thickness, rgb, alpha=255):
        ri = max(0, r - thickness)
        for y in range(cy - r, cy + r + 1):
            dy = y - cy
            d2 = dy * dy
            if d2 > r * r:
                continue
            dxo = int(math.sqrt(r * r - d2))
            if d2 <= ri * ri:
                dxi = int(math.sqrt(ri * ri - d2))
                self._hline(cx - dxo, cx - dxi - 1, y, rgb, alpha)
                self._hline(cx + dxi + 1, cx + dxo, y, rgb, alpha)
            else:
                self._hline(cx - dxo, cx + dxo, y, rgb, alpha)

    def ellipse_ring(self, cx, cy, rx, ry, thickness, rgb, alpha=255):
        rxi, ryi = max(1, rx - thickness), max(1, ry - thickness)
        for y in range(cy - ry, cy + ry + 1):
            dy = (y - cy) / ry
            rem = 1.0 - dy * dy
            if rem < 0:
                continue
            dxo = int(rx * math.sqrt(rem))
            dyi = (y - cy) / ryi
            remi = 1.0 - dyi * dyi
            if remi <= 0:
                self._hline(cx - dxo, cx + dxo, y, rgb, alpha)
            else:
                dxi = int(rxi * math.sqrt(remi))
                self._hline(cx - dxo, cx - dxi - 1, y, rgb, alpha)
                self._hline(cx + dxi + 1, cx + dxo, y, rgb, alpha)

    def fill_polygon(self, pts, rgb, alpha=255):
        if len(pts) < 3:
            return
        ys = [p[1] for p in pts]
        ymin = max(int(min(ys)), 0)
        ymax = min(int(max(ys)), self.h - 1)
        n = len(pts)
        for y in range(ymin, ymax + 1):
            xs = []
            for i in range(n):
                x1, y1 = pts[i]
                x2, y2 = pts[(i + 1) % n]
                if (y1 <= y < y2) or (y2 <= y < y1):
                    t = (y - y1) / (y2 - y1)
                    xs.append(x1 + t * (x2 - x1))
            if len(xs) < 2:
                continue
            xs.sort()
            for k in range(0, len(xs) - 1, 2):
                self._hline(int(math.ceil(xs[k])), int(math.floor(xs[k + 1])),
                            y, rgb, alpha)

    def thick_line(self, x0, y0, x1, y1, width, rgb, alpha=255):
        dist = math.hypot(x1 - x0, y1 - y0)
        steps = max(1, int(dist))
        r = max(1.0, width / 2.0)
        for i in range(steps + 1):
            t = i / steps
            self.fill_circle(round(x0 + (x1 - x0) * t),
                             round(y0 + (y1 - y0) * t), r, rgb, alpha)


# ---------------------------------------------------------------- curves

def quad_bezier(p0, p1, p2, t):
    u = 1 - t
    return (u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0],
            u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1])


def quad_tangent(p0, p1, p2, t):
    return (2 * (1 - t) * (p1[0] - p0[0]) + 2 * t * (p2[0] - p1[0]),
            2 * (1 - t) * (p1[1] - p0[1]) + 2 * t * (p2[1] - p1[1]))


def angle_of(vec):
    return math.degrees(math.atan2(vec[1], vec[0]))


def unit(vec):
    d = math.hypot(vec[0], vec[1]) or 1.0
    return (vec[0] / d, vec[1] / d)


def left_normal(vec):
    ux, uy = unit(vec)
    return (-uy, ux)


# ---------------------------------------------------------------- scene

# Frame geometry.
FRAME = (170, 110, 854, 760)      # outer gilt frame
PAINT = (204, 144, 820, 726)      # painting inside the frame
BREAK_X0, BREAK_X1 = 715, 825     # smashed gap in the bottom frame bar

# Koi spine: tail inside the painting, head bursting out below the frame.
KOI_P0 = (300, 380)
KOI_P1 = (560, 330)
KOI_P2 = (830, 810)


def koi_radius(t):
    """Body radius along the spine: thin tail, fat middle, narrower head."""
    return 42 + 58 * math.sin(math.pi * t ** 0.85)


def draw_gallery(img):
    """Wall, floor, baseboard and plank lines."""
    img.vgrad_rect(0, 0, WIDTH, 830, WALL_TOP, WALL_BOTTOM)
    img.vgrad_rect(0, 830, WIDTH, HEIGHT, FLOOR_TOP, FLOOR_BOTTOM)
    for y in (872, 912, 955, 998):
        img.fill_rect(0, y, WIDTH, y + 2, (110, 74, 40), alpha=90)
    for x in (300, 700):
        img.fill_rect(x, 830, x + 2, HEIGHT, (110, 74, 40), alpha=60)
    img.fill_rect(0, 822, WIDTH, 832, BASEBOARD)
    img.fill_rect(0, 822, WIDTH, 824, (150, 115, 75))


def draw_frame(img):
    """Gilt frame with bevel, plus the smashed gap in the bottom bar."""
    x0, y0, x1, y1 = FRAME
    # Soft shadow of the frame on the wall.
    img.fill_rect(x0 + 16, y0 + 14, x1 + 16, y1 + 14, (70, 55, 30), alpha=45)
    # Gold body.
    img.fill_rect(x0, y0, x1, y1, GOLD)
    # Bevel: light on top/left, dark on bottom/right.
    img.fill_rect(x0, y0, x1, y0 + 6, GOLD_LIGHT)
    img.fill_rect(x0, y0, x0 + 6, y1, GOLD_LIGHT)
    img.fill_rect(x0, y1 - 8, x1, y1, GOLD_DARK)
    img.fill_rect(x1 - 8, y0, x1, y1, GOLD_DARK)
    # Outer edge line.
    img.fill_rect(x0, y0, x1, y0 + 2, GOLD_EDGE)
    img.fill_rect(x0, y1 - 2, x1, y1, GOLD_EDGE)
    img.fill_rect(x0, y0, x0 + 2, y1, GOLD_EDGE)
    img.fill_rect(x1 - 2, y0, x1, y1, GOLD_EDGE)
    # Inner edge line around the painting.
    px0, py0, px1, py1 = PAINT
    img.fill_rect(px0 - 3, py0 - 3, px1 + 3, py0, GOLD_EDGE)
    img.fill_rect(px0 - 3, py1, px1 + 3, py1 + 3, GOLD_EDGE)
    img.fill_rect(px0 - 3, py0 - 3, px0, py1 + 3, GOLD_EDGE)
    img.fill_rect(px1, py0 - 3, px1 + 3, py1 + 3, GOLD_EDGE)
    # Smashed gap in the bottom bar: show the wall behind it, with
    # jagged gold teeth left and right of the hole.
    wall_at_gap = lerp_color(WALL_TOP, WALL_BOTTOM, 745 / 829)
    img.fill_rect(BREAK_X0, y1 - 34, BREAK_X1, y1, wall_at_gap)
    for (tx, ty, s) in ((BREAK_X0, y1 - 34, 12), (BREAK_X0 + 8, y1 - 20, 9),
                        (BREAK_X1 - 12, y1 - 34, 12), (BREAK_X1 - 20, y1 - 18, 9)):
        img.fill_polygon([(tx, ty), (tx + s, ty + 6), (tx, ty + s + 8)],
                         GOLD_DARK)


def draw_painting(img, rng):
    """Ukiyo-e seascape inside the frame (clipped to the painting)."""
    px0, py0, px1, py1 = PAINT
    img.set_clip(px0, py0, px1, py1)
    img.vgrad_rect(px0, py0, px1, py1, PAINT_TOP, PAINT_BOTTOM)
    # Pale moon with a soft glow.
    for r, a in ((92, 14), (72, 16), (58, 20)):
        img.fill_circle(690, 230, r, MOON, alpha=a)
    img.fill_circle(690, 230, 46, MOON)
    img.fill_circle(676, 218, 8, (228, 220, 188))
    img.fill_circle(702, 242, 6, (228, 220, 188))
    # Drifting clouds.
    for (cx, cy, rx, ry) in ((300, 205, 92, 22), (385, 232, 70, 18),
                             (610, 178, 80, 20), (250, 300, 60, 15)):
        img.fill_ellipse(cx, cy, rx, ry, CLOUD, alpha=70)
    # Stylized wave arcs rising from below the painting.
    for cx, cy, r0, step, a in ((512, 790, 90, 58, 105),
                                (200, 770, 60, 55, 80),
                                (760, 800, 70, 60, 80)):
        r = r0
        while r < 470:
            img.ring(cx, cy, r, 6, WAVE, alpha=a)
            r += step
    # Reeds in the lower-left corner.
    for (bx, top, lean) in ((248, 606, -14), (272, 580, -6),
                            (298, 612, 4), (322, 592, 12)):
        img.thick_line(bx, py1, bx + lean, top, 5, REED)
        img.fill_ellipse(bx + lean, top - 6, 5, 10, (90, 60, 30))
    # Red hanko seal, top-left.
    img.fill_rect(228, 168, 262, 202, SEAL_RED)
    img.fill_rect(234, 174, 256, 196, (250, 240, 230))
    img.fill_rect(240, 180, 250, 190, SEAL_RED)
    img.reset_clip()


def draw_koi(img, rng):
    """The koi itself: tail fin, body, patches, fins, head, whiskers."""
    # Speed lines trailing the leap.
    for t, off, length in ((0.08, 26, 46), (0.16, 30, 62), (0.24, 28, 54),
                           (0.33, 32, 70)):
        pos = quad_bezier(KOI_P0, KOI_P1, KOI_P2, t)
        tan = unit(quad_tangent(KOI_P0, KOI_P1, KOI_P2, t))
        nor = left_normal(quad_tangent(KOI_P0, KOI_P1, KOI_P2, t))
        r = koi_radius(t)
        sx = pos[0] + nor[0] * (r + off)
        sy = pos[1] + nor[1] * (r + off)
        img.thick_line(sx, sy, sx + tan[0] * length, sy + tan[1] * length,
                       4, SPLASH, alpha=80)

    # Tail fin: a swallowtail fan spreading from the body end.
    img.fill_polygon([(305, 372), (190, 292), (172, 344), (236, 380),
                      (178, 430), (198, 472), (300, 396)], KOI_ORANGE, alpha=235)
    img.fill_polygon([(298, 378), (214, 312), (200, 348), (238, 380),
                      (202, 428), (216, 452), (296, 390)], KOI_WHITE, alpha=200)
    for (tx, ty) in ((186, 300), (182, 348), (192, 438), (206, 464)):
        img.thick_line(300, 382, tx, ty, 3, KOI_DEEP, alpha=170)

    # Body: a warm rim under-layer, then white, drawn as overlapping
    # circles along the bezier spine.
    steps = 64
    for layer, color in ((6, KOI_RIM), (0, KOI_WHITE)):
        for i in range(steps + 1):
            t = i / steps
            pos = quad_bezier(KOI_P0, KOI_P1, KOI_P2, t)
            img.fill_circle(round(pos[0]), round(pos[1]),
                            koi_radius(t) + layer, color)

    # Orange patches, hugging the spine and rotated with the body.
    for t, color in ((0.18, KOI_ORANGE), (0.35, KOI_ORANGE),
                     (0.52, KOI_DEEP), (0.68, KOI_ORANGE), (0.84, KOI_ORANGE)):
        pos = quad_bezier(KOI_P0, KOI_P1, KOI_P2, t)
        ang = angle_of(quad_tangent(KOI_P0, KOI_P1, KOI_P2, t))
        r = koi_radius(t)
        img.fill_ellipse_rot(round(pos[0]), round(pos[1]),
                             r * 0.95, r * 0.62, ang, color)

    # Dorsal fin: three small triangles along the back. The back is the
    # outer (upper) side of the arc, i.e. the opposite of left_normal
    # in screen coordinates (y grows downward).
    for t in (0.32, 0.45, 0.58):
        pos = quad_bezier(KOI_P0, KOI_P1, KOI_P2, t)
        tan = unit(quad_tangent(KOI_P0, KOI_P1, KOI_P2, t))
        nor = left_normal(quad_tangent(KOI_P0, KOI_P1, KOI_P2, t))
        nor = (-nor[0], -nor[1])  # flip to the back (upper) side
        r = koi_radius(t)
        base_x = pos[0] + nor[0] * (r - 4)
        base_y = pos[1] + nor[1] * (r - 4)
        tip_x = base_x + nor[0] * 26 - tan[0] * 8
        tip_y = base_y + nor[1] * 26 - tan[1] * 8
        img.fill_polygon([(base_x - tan[0] * 16, base_y - tan[1] * 16),
                          (tip_x, tip_y),
                          (base_x + tan[0] * 16, base_y + tan[1] * 16)],
                         KOI_ORANGE, alpha=230)

    # Pectoral fin peeking out on the near side, close to the head.
    pos = quad_bezier(KOI_P0, KOI_P1, KOI_P2, 0.86)
    tan = quad_tangent(KOI_P0, KOI_P1, KOI_P2, 0.86)
    nor = left_normal(tan)
    ang = angle_of(tan)
    img.fill_ellipse_rot(round(pos[0] - nor[0] * 30),
                         round(pos[1] - nor[1] * 30),
                         34, 14, ang + 38, KOI_ORANGE, alpha=220)

    # Head: eye, mouth, whiskers.
    head = KOI_P2
    tan = unit(quad_tangent(KOI_P0, KOI_P1, KOI_P2, 1.0))
    nor = left_normal(quad_tangent(KOI_P0, KOI_P1, KOI_P2, 1.0))
    eye_x = round(head[0] + nor[0] * 16 + tan[0] * 12)
    eye_y = round(head[1] + nor[1] * 16 + tan[1] * 12)
    img.fill_circle(eye_x, eye_y, 9, (20, 16, 14))
    img.fill_circle(eye_x - 3, eye_y - 3, 3, (255, 255, 255))
    snout = (head[0] + tan[0] * 46, head[1] + tan[1] * 46)
    img.thick_line(round(snout[0]), round(snout[1]),
                   round(snout[0] + 16), round(snout[1] + 6),
                   4, KOI_DARK)
    # Whiskers curling out from the snout.
    img.thick_line(round(snout[0]), round(snout[1]), 878, 832, 3, KOI_DARK)
    img.thick_line(878, 832, 898, 838, 3, KOI_DARK)
    img.thick_line(round(snout[0]), round(snout[1]), 872, 872, 3, KOI_DARK)
    img.thick_line(872, 872, 886, 884, 3, KOI_DARK)


def draw_splash_and_splinters(img, rng):
    """Water explosion, gold splinters, floor shadow and ripples."""
    # Soft shadow of the leaping fish on the floor.
    img.fill_ellipse(770, 905, 235, 42, (60, 40, 20), alpha=55)

    # Splash crown rings around the break point.
    for r, a in ((42, 110), (72, 85), (102, 60)):
        img.ring(775, 745, r, 4, SPLASH, alpha=a)

    # Droplets bursting out of the break and around the head.
    for _ in range(34):
        ang = math.radians(rng.uniform(-165, -15))
        dist = rng.uniform(18, 130)
        cx = 775 + math.cos(ang) * dist
        cy = 745 + math.sin(ang) * dist * 0.8
        img.fill_circle(round(cx), round(cy), rng.uniform(4, 13),
                        rng.choice((SPLASH, SPLASH_BLUE)), alpha=225)
    for _ in range(10):
        cx = rng.uniform(790, 900)
        cy = rng.uniform(780, 880)
        img.fill_circle(round(cx), round(cy), rng.uniform(3, 9),
                        rng.choice((SPLASH, SPLASH_BLUE)), alpha=230)
    # Fine spray.
    for _ in range(70):
        cx = rng.uniform(640, 930)
        cy = rng.uniform(690, 900)
        img.fill_circle(round(cx), round(cy), rng.uniform(1.5, 3.5),
                        SPLASH, alpha=200)

    # Gold splinters flying up from the smashed frame bar.
    for _ in range(12):
        ang = math.radians(rng.uniform(200, 340))
        length = rng.uniform(25, 70)
        width = rng.uniform(4, 9)
        bx, by = 770, 745
        tx, ty = bx + math.cos(ang) * length, by + math.sin(ang) * length
        px, py = -math.sin(ang) * width / 2, math.cos(ang) * width / 2
        img.fill_polygon([(bx + px, by + py), (tx, ty), (bx - px, by - py)],
                         rng.choice((GOLD, GOLD_LIGHT, GOLD_DARK)))

    # Ripples spreading on the floor under the fish.
    for rx, ry, a in ((120, 26, 70), (170, 36, 55), (220, 46, 40)):
        img.ellipse_ring(800, 905, rx, ry, 3, SPLASH_BLUE, alpha=a)


def draw_visitors(img):
    """Two tiny museum visitors ducking for cover, bottom-left."""
    # Standing visitor, arm raised to shield their head.
    img.fill_circle(190, 852, 15, VISITOR)
    img.fill_polygon([(168, 872), (212, 872), (224, 960), (156, 960)], VISITOR)
    img.thick_line(200, 885, 235, 850, 8, VISITOR)
    img.thick_line(180, 960, 172, 1010, 10, VISITOR)
    img.thick_line(200, 960, 210, 1010, 10, VISITOR)
    # Crouching visitor.
    img.fill_circle(330, 890, 14, VISITOR)
    img.fill_polygon([(310, 908), (352, 908), (368, 985), (296, 985)], VISITOR)
    img.thick_line(318, 920, 300, 892, 7, VISITOR)


def draw_scene():
    """Paint the whole scene and return the canvas."""
    rng = random.Random(SEED)
    img = Canvas(WIDTH, HEIGHT)
    draw_gallery(img)
    draw_frame(img)
    draw_painting(img, rng)
    draw_koi(img, rng)
    draw_splash_and_splinters(img, rng)
    draw_visitors(img)
    # A whisper of film grain, fully deterministic.
    for _ in range(12000):
        x = rng.randrange(WIDTH)
        y = rng.randrange(HEIGHT)
        i = (y * WIDTH + x) * 3
        d = rng.randint(-7, 7)
        img.buf[i] = clamp_byte(img.buf[i] + d)
        img.buf[i + 1] = clamp_byte(img.buf[i + 1] + d)
        img.buf[i + 2] = clamp_byte(img.buf[i + 2] + d)
    return img


# ---------------------------------------------------------------- png out

def _chunk(kind, body):
    return (struct.pack(">I", len(body)) + kind + body +
            struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF))


def encode_png(img):
    """Encode the canvas as a deterministic PNG (filter 0, level 9)."""
    raw = bytearray()
    stride = img.w * 3
    for y in range(img.h):
        raw.append(0)
        raw += img.buf[y * stride:(y + 1) * stride]
    ihdr = struct.pack(">IIBBBBB", img.w, img.h, 8, 2, 0, 0, 0)
    return (PNG_SIGNATURE + _chunk(b"IHDR", ihdr) +
            _chunk(b"IDAT", zlib.compress(bytes(raw), 9)) +
            _chunk(b"IEND", b""))


class BadImage(Exception):
    """Raised when a PNG fails structural validation."""


def parse_png(data):
    """Validate PNG bytes; return (width, height).

    Checks the 8-byte signature, the IHDR size, every chunk CRC, the
    IEND trailer, and that no bytes trail after IEND.
    """
    if len(data) < 8 or data[:8] != PNG_SIGNATURE:
        raise BadImage("not a PNG file (bad signature)")
    if len(data) < 29 or data[12:16] != b"IHDR":
        raise BadImage("PNG has no IHDR chunk where one is expected")
    width, height = struct.unpack(">II", data[16:24])
    offset = 8
    saw_iend = False
    while offset + 8 <= len(data):
        length = struct.unpack(">I", data[offset:offset + 4])[0]
        kind = data[offset + 4:offset + 8]
        body_start = offset + 8
        body_end = body_start + length
        if body_end + 4 > len(data):
            raise BadImage(f"chunk {kind!r} overruns the end of the file")
        expected = struct.unpack(">I", data[body_end:body_end + 4])[0]
        actual = zlib.crc32(kind + data[body_start:body_end]) & 0xFFFFFFFF
        if expected != actual:
            raise BadImage(f"CRC mismatch in {kind!r} chunk")
        offset = body_end + 4
        if kind == b"IEND":
            saw_iend = True
            if offset != len(data):
                raise BadImage(f"{len(data) - offset} trailing bytes after IEND")
            break
    if not saw_iend:
        raise BadImage("PNG is truncated (no IEND trailer)")
    return width, height


def die(message):
    print(f"ERROR: {message}", file=sys.stderr)
    sys.exit(1)


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = os.environ.get("MAKEFUN_OUTPUT_DIR", script_dir)
    dest_path = os.path.join(output_dir, OUTPUT_NAME)

    img = draw_scene()
    png_bytes = encode_png(img)

    if len(png_bytes) > MAX_SIZE:
        die(f"generated image is {len(png_bytes)} bytes, over the "
            f"{MAX_SIZE} byte limit")

    try:
        width, height = parse_png(png_bytes)
    except BadImage as exc:
        die(f"generated image failed validation: {exc}")
    if (width, height) != (WIDTH, HEIGHT):
        die(f"generated image is {width}x{height}, expected "
            f"{WIDTH}x{HEIGHT}")

    os.makedirs(output_dir, exist_ok=True)
    with open(dest_path, "wb") as handle:
        handle.write(png_bytes)

    # Read the file back from disk and check it, never trusting the
    # in-memory bytes alone.
    with open(dest_path, "rb") as handle:
        written = handle.read()
    if written != png_bytes:
        die("bytes on disk differ from the generated image")
    try:
        out_w, out_h = parse_png(written)
    except BadImage as exc:
        die(f"written file failed validation: {exc}")
    if (out_w, out_h) != (WIDTH, HEIGHT):
        die("written file dimensions changed after writing")

    print(f"Wrote {dest_path}")
    print(f"bytes: {len(written)}")
    print(f"sha256: {hashlib.sha256(written).hexdigest()}")
    print(f"dimensions: {out_w}x{out_h}")


if __name__ == "__main__":
    main()
