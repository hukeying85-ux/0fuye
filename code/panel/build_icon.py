#!/usr/bin/env python3
"""Pure-stdlib multi-resolution icon & vector emblem builder for Arena Desk."""
import math
import pathlib
import struct
import zlib

ASSETS = pathlib.Path(__file__).resolve().parent / "assets"


def clamp01(x: float) -> float:
    return 0.0 if x <= 0.0 else (1.0 if x >= 1.0 else x)


def smoothstep(edge0: float, edge1: float, x: float) -> float:
    t = clamp01((x - edge0) / (edge1 - edge0))
    return t * t * (3.0 - 2.0 * t)


def mix(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def mix_rgb(c1, c2, t: float):
    return (mix(c1[0], c2[0], t), mix(c1[1], c2[1], t), mix(c1[2], c2[2], t))


def sd_seg(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    vx, vy = bx - ax, by - ay
    wx, wy = px - ax, py - ay
    denom = vx * vx + vy * vy
    h = clamp01((wx * vx + wy * vy) / denom) if denom > 1e-9 else 0.0
    dx = wx - vx * h
    dy = wy - vy * h
    return math.hypot(dx, dy)


def render_rgba(size: int) -> bytes:
    """Render anti-aliased Arena Desk squircle emblem at `size x size`."""
    aa = 1.35 / size
    rows = bytearray()

    bg_top = (14.0, 32.0, 36.0)
    bg_bot = (7.0, 14.0, 20.0)
    jade = (82.0, 236.0, 190.0)
    cyan = (94.0, 208.0, 255.0)
    lime = (210.0, 248.0, 152.0)

    nodes = [
        (0.0, -0.50, 0.068, lime),
        (-0.433, 0.25, 0.062, jade),
        (0.433, 0.25, 0.062, cyan),
    ]

    for yi in range(size):
        rows.append(0)  # PNG filter type 0
        ny = ((yi + 0.5) / size) * 2.0 - 1.0
        for xi in range(size):
            nx = ((xi + 0.5) / size) * 2.0 - 1.0

            # Squircle SDF: |x|^4.4 + |y|^4.4
            ax_n = abs(nx) / 0.89
            ay_n = abs(ny) / 0.89
            sq = (ax_n ** 4.4 + ay_n ** 4.4) ** (1.0 / 4.4) - 1.0
            alpha = 1.0 - smoothstep(-aa * 1.4, aa * 1.4, sq)
            if alpha <= 0.002:
                rows.extend((0, 0, 0, 0))
                continue

            # Base vertical + radial aurora gradient
            gt = clamp01((ny + 1.0) * 0.5)
            col = mix_rgb(bg_top, bg_bot, gt)

            # Soft radial aurora glow from upper-left & center
            d_glow1 = math.hypot(nx + 0.28, ny + 0.34)
            col = mix_rgb(col, (26.0, 96.0, 86.0), 0.52 * math.exp(-2.6 * d_glow1 * d_glow1))
            d_glow2 = math.hypot(nx - 0.30, ny - 0.28)
            col = mix_rgb(col, (22.0, 68.0, 112.0), 0.45 * math.exp(-2.8 * d_glow2 * d_glow2))

            # Subtle inner squircle glass border
            border_d = abs(sq + 0.025)
            border_a = (1.0 - smoothstep(0.0, aa * 2.2 + 0.012, border_d)) * (0.42 - 0.22 * gt)
            col = mix_rgb(col, (180.0, 245.0, 225.0), clamp01(border_a))

            # Orbital ring
            r = math.hypot(nx, ny)
            ring_d = abs(r - 0.50)
            ring_glow = 0.26 * math.exp(-70.0 * ring_d * ring_d)
            col = mix_rgb(col, jade, clamp01(ring_glow))
            ring_stroke = 1.0 - smoothstep(0.022 - aa, 0.022 + aa, ring_d)
            ring_col = mix_rgb(jade, cyan, clamp01((nx + 0.6) / 1.2))
            col = mix_rgb(col, ring_col, 0.72 * ring_stroke)

            # Stylized central prism 'A' / Delta + crossbar + hub core
            d_l = sd_seg(nx, ny, 0.0, -0.34, -0.30, 0.24)
            d_r = sd_seg(nx, ny, 0.0, -0.34, 0.30, 0.24)
            d_b = sd_seg(nx, ny, -0.19, 0.06, 0.19, 0.06)
            d_a = min(d_l, d_r, d_b)

            # Prism soft halo
            col = mix_rgb(col, jade, 0.28 * math.exp(-42.0 * d_a * d_a))

            # Crisp prism stroke
            stroke_w = 0.056
            a_mask = 1.0 - smoothstep(stroke_w - aa * 1.3, stroke_w + aa * 1.3, d_a)
            prism_grad = mix_rgb(lime, cyan, clamp01((ny + 0.36) / 0.68))
            col = mix_rgb(col, (242.0, 255.0, 249.0), 0.35 * a_mask)
            col = mix_rgb(col, prism_grad, 0.88 * a_mask)

            # Center hub jewel
            d_core = math.hypot(nx, ny + 0.03)
            core_m = 1.0 - smoothstep(0.072 - aa, 0.072 + aa, d_core)
            col = mix_rgb(col, (255.0, 255.0, 255.0), 0.92 * core_m)

            # 3 orbital nodes (Local, Remote, Cloud)
            for ox, oy, rad, ncol in nodes:
                dn = math.hypot(nx - ox, ny - oy)
                col = mix_rgb(col, ncol, 0.28 * math.exp(-65.0 * dn * dn))
                nm = 1.0 - smoothstep(rad - aa * 1.3, rad + aa * 1.3, dn)
                col = mix_rgb(col, ncol, 0.95 * nm)
                hi = 1.0 - smoothstep(rad * 0.42 - aa, rad * 0.42 + aa, dn)
                col = mix_rgb(col, (255.0, 255.0, 255.0), 0.70 * hi)

            rows.extend((
                int(clamp01(col[0] / 255.0) * 255.0 + 0.5),
                int(clamp01(col[1] / 255.0) * 255.0 + 0.5),
                int(clamp01(col[2] / 255.0) * 255.0 + 0.5),
                int(clamp01(alpha) * 255.0 + 0.5),
            ))
    return bytes(rows)


def encode_png(size: int, raw_scanlines: bytes) -> bytes:
    def chunk(tag: bytes, payload: bytes) -> bytes:
        crc = zlib.crc32(tag + payload) & 0xFFFFFFFF
        return struct.pack(">I", len(payload)) + tag + payload + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    idat = zlib.compress(raw_scanlines, level=9)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


def build_ico(png_map: dict) -> bytes:
    sizes = sorted(png_map.keys())
    header = struct.pack("<HHH", 0, 1, len(sizes))
    entries = bytearray()
    blobs = bytearray()
    offset = 6 + 16 * len(sizes)
    for sz in sizes:
        blob = png_map[sz]
        w_byte = 0 if sz >= 256 else sz
        h_byte = 0 if sz >= 256 else sz
        entries.extend(struct.pack("<BBBBHHII", w_byte, h_byte, 0, 0, 1, 32, len(blob), offset))
        blobs.extend(blob)
        offset += len(blob)
    return header + bytes(entries) + bytes(blobs)


ICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" fill="none">
  <defs>
    <linearGradient id="bg" x1="24" y1="16" x2="232" y2="244" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#10272B"/>
      <stop offset="0.52" stop-color="#0B1B22"/>
      <stop offset="1" stop-color="#071018"/>
    </linearGradient>
    <radialGradient id="aur1" cx="0" cy="0" r="1" gradientUnits="userSpaceOnUse" gradientTransform="translate(86 72) scale(120)">
      <stop offset="0" stop-color="#227B68" stop-opacity="0.62"/>
      <stop offset="1" stop-color="#227B68" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="aur2" cx="0" cy="0" r="1" gradientUnits="userSpaceOnUse" gradientTransform="translate(178 176) scale(115)">
      <stop offset="0" stop-color="#1E5C93" stop-opacity="0.52"/>
      <stop offset="1" stop-color="#1E5C93" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="ring" x1="56" y1="64" x2="200" y2="196" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#D2F898"/>
      <stop offset="0.5" stop-color="#52ECBE"/>
      <stop offset="1" stop-color="#5ED0FF"/>
    </linearGradient>
    <linearGradient id="prism" x1="128" y1="74" x2="128" y2="172" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#E6FFB8"/>
      <stop offset="0.55" stop-color="#6AF2C8"/>
      <stop offset="1" stop-color="#62D2FF"/>
    </linearGradient>
  </defs>
  <rect x="14" y="14" width="228" height="228" rx="54" fill="url(#bg)"/>
  <rect x="14" y="14" width="228" height="228" rx="54" fill="url(#aur1)"/>
  <rect x="14" y="14" width="228" height="228" rx="54" fill="url(#aur2)"/>
  <rect x="15.5" y="15.5" width="225" height="225" rx="52.5" stroke="#9EF5DC" stroke-opacity="0.26" stroke-width="3"/>
  <circle cx="128" cy="128" r="66" stroke="url(#ring)" stroke-width="6.5" stroke-opacity="0.86"/>
  <path d="M128 83L90 159M128 83L166 159M103 136H153" stroke="url(#prism)" stroke-width="14" stroke-linecap="round" stroke-linejoin="round"/>
  <circle cx="128" cy="124" r="9.5" fill="#FFFFFF"/>
  <circle cx="128" cy="62" r="9.5" fill="#D2F898"/>
  <circle cx="128" cy="62" r="4" fill="#FFFFFF"/>
  <circle cx="71" cy="161" r="8.5" fill="#52ECBE"/>
  <circle cx="71" cy="161" r="3.6" fill="#FFFFFF"/>
  <circle cx="185" cy="161" r="8.5" fill="#5ED0FF"/>
  <circle cx="185" cy="161" r="3.6" fill="#FFFFFF"/>
</svg>
"""

WHALE_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 100" fill="none">
  <defs>
    <linearGradient id="wbody" x1="22" y1="22" x2="96" y2="82" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#69F0C8"/>
      <stop offset="0.52" stop-color="#38BDF8"/>
      <stop offset="1" stop-color="#2563EB"/>
    </linearGradient>
    <linearGradient id="wbelly" x1="30" y1="54" x2="78" y2="82" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#ECFEFF"/>
      <stop offset="1" stop-color="#BAE6FD"/>
    </linearGradient>
  </defs>
  <!-- Water spout -->
  <path d="M52 24C52 14 43 9 37 12M55 24C57 12 67 8 73 12" stroke="#7DD3FC" stroke-width="3.2" stroke-linecap="round"/>
  <circle cx="34" cy="16" r="2.4" fill="#A5F3FC"/>
  <circle cx="76" cy="16" r="2.4" fill="#6EE7B7"/>
  <!-- Tail -->
  <path d="M90 58C99 54 106 44 111 38C111 49 106 58 99 62C106 65 112 72 110 80C103 76 96 68 90 64Z" fill="#2563EB"/>
  <!-- Main whale body -->
  <path d="M18 56C18 35 36 24 58 24C79 24 94 38 94 57C94 72 81 80 56 80C32 80 18 71 18 56Z" fill="url(#wbody)"/>
  <!-- Belly -->
  <path d="M22 61C30 61 45 63 68 74C58 79 44 80 34 78C25 76 21 69 22 61Z" fill="url(#wbelly)"/>
  <!-- Cheek & Eye -->
  <circle cx="39" cy="52" r="4.5" fill="#0F172A"/>
  <circle cx="37.5" cy="50.3" r="1.7" fill="#FFFFFF"/>
  <ellipse cx="32" cy="59" rx="4.6" ry="2.6" fill="#FDA4AF" fill-opacity="0.72"/>
  <!-- Cute smile -->
  <path d="M26 57C28.5 60 32.5 60 35 57.8" stroke="#0F172A" stroke-width="2.2" stroke-linecap="round"/>
  <!-- Side flipper -->
  <path d="M56 62C52 70 57 77 65 74C67 69 64 63 56 62Z" fill="#1D4ED8"/>
</svg>
"""


def main():
    ASSETS.mkdir(parents=True, exist_ok=True)
    sizes = (16, 24, 32, 48, 64, 128, 256)
    pngs = {sz: encode_png(sz, render_rgba(sz)) for sz in sizes}
    (ASSETS / "ArenaDesk.ico").write_bytes(build_ico(pngs))
    (ASSETS / "icon-256.png").write_bytes(pngs[256])
    (ASSETS / "icon-64.png").write_bytes(pngs[64])
    (ASSETS / "icon.svg").write_text(ICON_SVG, encoding="utf-8")
    (ASSETS / "whale.svg").write_text(WHALE_SVG, encoding="utf-8")
    print(f"Generated ArenaDesk.ico ({(ASSETS / 'ArenaDesk.ico').stat().st_size} B) + PNG/SVG assets in {ASSETS}")


if __name__ == "__main__":
    main()
