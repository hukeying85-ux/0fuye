"""Zero-dependency ISO/IEC 18004 QR Code (Byte mode, ECC Level L, v1..v10) SVG renderer."""

from __future__ import annotations

import html

# (version: (total_codewords, ec_codewords_per_block, num_blocks, alignment_centers))
_QR_SPECS = {
    1: (26, 7, 1, ()),
    2: (44, 10, 1, (6, 18)),
    3: (70, 15, 1, (6, 22)),
    4: (100, 20, 1, (6, 26)),
    5: (134, 26, 1, (6, 30)),
    6: (172, 18, 2, (6, 34)),
    7: (196, 20, 2, (6, 22, 38)),
    8: (242, 24, 2, (6, 24, 42)),
    9: (292, 30, 2, (6, 26, 46)),
    10: (346, 18, 4, (6, 28, 50)),
}

_GF_EXP = [0] * 512
_GF_LOG = [0] * 256
_x = 1
for _i in range(255):
    _GF_EXP[_i] = _x
    _GF_LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for _i in range(255, 512):
    _GF_EXP[_i] = _GF_EXP[_i - 255]


def _gf_mul(a: int, b: int) -> int:
    if a == 0 or b == 0:
        return 0
    return _GF_EXP[_GF_LOG[a] + _GF_LOG[b]]


def _rs_generator(degree: int) -> list[int]:
    poly = [1]
    for i in range(degree):
        nxt = [0] * (len(poly) + 1)
        root = _GF_EXP[i]
        for j, coeff in enumerate(poly):
            nxt[j] ^= coeff
            nxt[j + 1] ^= _gf_mul(coeff, root)
        poly = nxt
    return poly


def _rs_encode(data: list[int], ec_len: int) -> list[int]:
    gen = _rs_generator(ec_len)
    rem = [0] * ec_len
    for byte in data:
        factor = byte ^ rem[0]
        rem = rem[1:] + [0]
        for j in range(ec_len):
            rem[j] ^= _gf_mul(gen[j + 1], factor)
    return rem


def _format_bits_ecc_l(mask: int) -> int:
    # ECC Level L = 01
    data = (0b01 << 3) | (mask & 0b111)
    rem = data << 10
    for i in range(14, 9, -1):
        if (rem >> i) & 1:
            rem ^= 0x537 << (i - 10)
    return ((data << 10) | rem) ^ 0x5412


def _version_bits(ver: int) -> int:
    rem = ver << 12
    for i in range(17, 11, -1):
        if (rem >> i) & 1:
            rem ^= 0x1F25 << (i - 12)
    return (ver << 12) | rem


def encode_qr_matrix(text: str) -> list[list[int]]:
    raw = text.encode("utf-8")
    ver = 0
    for v, (tot, ec, blk, _) in _QR_SPECS.items():
        data_cw = tot - ec * blk
        cap = data_cw - (3 if v >= 10 else 2)
        if len(raw) <= cap:
            ver = v
            break
    if ver == 0:
        raw = raw[:270]
        ver = 10

    tot_cw, ec_cw, n_blk, aligns = _QR_SPECS[ver]
    data_cw = tot_cw - ec_cw * n_blk

    bits: list[int] = []

    def push_bits(val: int, length: int):
        for shift in range(length - 1, -1, -1):
            bits.append((val >> shift) & 1)

    push_bits(0b0100, 4)  # Byte mode
    push_bits(len(raw), 16 if ver >= 10 else 8)
    for b in raw:
        push_bits(b, 8)
    rem_bits = data_cw * 8 - len(bits)
    push_bits(0, min(4, rem_bits))
    while len(bits) % 8 != 0:
        bits.append(0)
    codewords = [
        int("".join(str(bit) for bit in bits[i : i + 8]), 2)
        for i in range(0, len(bits), 8)
    ]
    pads = [0xEC, 0x11]
    idx = 0
    while len(codewords) < data_cw:
        codewords.append(pads[idx % 2])
        idx += 1

    # Split into blocks and interleave
    base_len = data_cw // n_blk
    extra = data_cw % n_blk
    d_blocks: list[list[int]] = []
    e_blocks: list[list[int]] = []
    pos = 0
    for b in range(n_blk):
        ln = base_len + (1 if b >= n_blk - extra else 0)
        blk_data = codewords[pos : pos + ln]
        pos += ln
        d_blocks.append(blk_data)
        e_blocks.append(_rs_encode(blk_data, ec_cw))

    stream_cw: list[int] = []
    max_d = max(len(b) for b in d_blocks)
    for col in range(max_d):
        for b in d_blocks:
            if col < len(b):
                stream_cw.append(b[col])
    for col in range(ec_cw):
        for eb in e_blocks:
            stream_cw.append(eb[col])

    stream_bits: list[int] = []
    for cw in stream_cw:
        for shift in range(7, -1, -1):
            stream_bits.append((cw >> shift) & 1)

    size = 17 + 4 * ver
    grid: list[list[int | None]] = [[None] * size for _ in range(size)]
    reserved = [[False] * size for _ in range(size)]

    def set_fn(r: int, c: int, val: int):
        if 0 <= r < size and 0 <= c < size:
            grid[r][c] = val
            reserved[r][c] = True

    def place_finder(top: int, left: int):
        for dr in range(-1, 8):
            for dc in range(-1, 8):
                if 0 <= dr <= 6 and 0 <= dc <= 6:
                    on = (
                        dr in (0, 6)
                        or dc in (0, 6)
                        or (2 <= dr <= 4 and 2 <= dc <= 4)
                    )
                    set_fn(top + dr, left + dc, 1 if on else 0)
                else:
                    set_fn(top + dr, left + dc, 0)

    place_finder(0, 0)
    place_finder(0, size - 7)
    place_finder(size - 7, 0)

    for r in aligns:
        for c in aligns:
            if reserved[r][c]:
                continue
            for dr in range(-2, 3):
                for dc in range(-2, 3):
                    on = max(abs(dr), abs(dc)) in (0, 2)
                    set_fn(r + dr, c + dc, 1 if on else 0)

    for i in range(8, size - 8):
        if not reserved[6][i]:
            set_fn(6, i, 1 if i % 2 == 0 else 0)
        if not reserved[i][6]:
            set_fn(i, 6, 1 if i % 2 == 0 else 0)

    # Dark module & format reserve
    set_fn(4 * ver + 9, 8, 1)
    for i in range(9):
        if not reserved[8][i]:
            set_fn(8, i, 0)
        if not reserved[i][8]:
            set_fn(i, 8, 0)
    for i in range(8):
        if not reserved[8][size - 1 - i]:
            set_fn(8, size - 1 - i, 0)
        if not reserved[size - 1 - i][8]:
            set_fn(size - 1 - i, 8, 0)

    if ver >= 7:
        vbits = _version_bits(ver)
        for i in range(18):
            bit = (vbits >> i) & 1
            r, c = i // 3, size - 11 + (i % 3)
            set_fn(r, c, bit)
            set_fn(c, r, bit)

    # Zigzag data placement
    bit_idx = 0
    upward = True
    col = size - 1
    while col > 0:
        if col == 6:
            col -= 1
        rows = range(size - 1, -1, -1) if upward else range(size)
        for r in rows:
            for dc in (0, -1):
                c = col + dc
                if not reserved[r][c]:
                    b = stream_bits[bit_idx] if bit_idx < len(stream_bits) else 0
                    bit_idx += 1
                    # Mask 0: (r + c) % 2 == 0
                    if (r + c) % 2 == 0:
                        b ^= 1
                    grid[r][c] = b
        upward = not upward
        col -= 2

    # Write format info for Mask 0
    fbits = _format_bits_ecc_l(0)
    f_coords_a = [
        (8, 0), (8, 1), (8, 2), (8, 3), (8, 4), (8, 5), (8, 7), (8, 8),
        (7, 8), (5, 8), (4, 8), (3, 8), (2, 8), (1, 8), (0, 8),
    ]
    f_coords_b = [
        (size - 1, 8), (size - 2, 8), (size - 3, 8), (size - 4, 8),
        (size - 5, 8), (size - 6, 8), (size - 7, 8),
        (8, size - 8), (8, size - 7), (8, size - 6), (8, size - 5),
        (8, size - 4), (8, size - 3), (8, size - 2), (8, size - 1),
    ]
    for i in range(15):
        bit = (fbits >> (14 - i)) & 1
        ra, ca = f_coords_a[i]
        rb, cb = f_coords_b[i]
        grid[ra][ca] = bit
        grid[rb][cb] = bit

    return [[int(cell or 0) for cell in row] for row in grid]


def render_qr_svg(text: str, box_px: int = 180) -> str:
    matrix = encode_qr_matrix(text)
    n = len(matrix)
    quiet = 3
    dim = n + quiet * 2
    rects = []
    for r, row in enumerate(matrix):
        c = 0
        while c < n:
            if row[c]:
                run = 1
                while c + run < n and row[c + run]:
                    run += 1
                rects.append(f"M{c + quiet},{r + quiet}h{run}v1h-{run}z")
                c += run
            else:
                c += 1
    path_d = "".join(rects)
    safe_title = html.escape(text[:120])
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {dim} {dim}" '
        f'width="{box_px}" height="{box_px}" shape-rendering="crispEdges" role="img" aria-label="{safe_title}">'
        f'<rect width="{dim}" height="{dim}" rx="2.2" fill="#ffffff"/>'
        f'<path d="{path_d}" fill="#0f172a"/></svg>'
    )
