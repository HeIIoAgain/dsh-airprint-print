#!/usr/bin/env python3
"""Apple Raster (URF / "UNIRAST") encoder and decoder.

AirPrint printers that advertise `urf-supported` accept pages as a compressed
24-bit RGB raster stream, not as PDF. This module turns Pillow images into that
stream (and back, for self-checks).

Container layout (big-endian):

    "UNIRAST\\0"                    8 bytes
    page_count                       uint32
    per page:
        bpp (24) colorspace (1) duplex (0) quality (3..5)   4 bytes
        unknown0 unknown1 width height dpi unknown2 unknown3   7 x uint32
        raster: per scanline
            1 byte  line_repeat_minus_one   (0 = one line, 255 = 256 lines)
            PackBits-like pixel codes until `width` pixels are filled:
                0x80          fill the rest of the scanline with white
                0x00..0x7F    repeat the next RGB triple (code+1) times
                0x81..0xFF    copy (-code)+1 RGB triples verbatim
"""

from __future__ import annotations

import struct

try:  # numpy makes encoding of photo-sized pages fast; pure Python still works
    import numpy as _np
except ImportError:  # pragma: no cover - exercised only on minimal installs
    _np = None

from PIL import Image

WHITE = b"\xff\xff\xff"


# ----------------------------------------------------------------------------
# encoding
# ----------------------------------------------------------------------------
def encode_image(image: Image.Image, dpi: int = 600, quality: int = 4) -> bytes:
    return encode_images([image], dpi=dpi, quality=quality)


def encode_images(images, dpi: int = 600, quality: int = 4) -> bytes:
    """Encode one or more RGB pages into a URF byte stream."""
    out = bytearray(b"UNIRAST\x00")
    out += struct.pack(">I", len(images))
    for image in images:
        rgb = image.convert("RGB")
        width, height = rgb.size
        out += bytes([24, 1, 0, quality & 0xFF])
        out += struct.pack(">7I", 0, 0, width, height, dpi, 0, 0)
        _encode_raster(out, rgb.tobytes(), width, height)
    return bytes(out)


def _encode_raster(out: bytearray, data: bytes, width: int, height: int) -> None:
    stride = width * 3
    blank = b"\xff" * stride
    encoder = _encode_line_numpy if _np is not None else _encode_line_python
    previous = None
    repeated = 0
    for y in range(height):
        line = data[y * stride:(y + 1) * stride]
        encoded = b"\x80" if line == blank else encoder(line, width)
        if encoded == previous and repeated < 256:
            repeated += 1
            continue
        if previous is not None:
            out.append(repeated - 1)
            out += previous
        previous, repeated = encoded, 1
    if previous is not None:
        out.append(repeated - 1)
        out += previous


def _pack_runs(out: bytearray, width: int, starts, ends, pixel):
    """Shared packing: `pixel(index)` returns the RGB triple at a run start."""
    literal = bytearray()
    literal_count = 0

    def flush():
        nonlocal literal, literal_count, out
        if not literal_count:
            return
        if literal_count == 1:
            out.append(0x00)  # a literal needs >=2 pixels; a 1x repeat is exact
        else:
            out.append((257 - literal_count) & 0xFF)
        out += literal
        literal = bytearray()
        literal_count = 0

    for start, end in zip(starts, ends):
        run = end - start
        rgb = pixel(start)
        if end == width and rgb == WHITE:
            flush()
            out.append(0x80)
            return
        if run >= 2:
            flush()
            remaining = run
            while remaining > 0:
                chunk = min(remaining, 128)
                out.append(chunk - 1)
                out += rgb
                remaining -= chunk
        else:
            literal += rgb
            literal_count += 1
            if literal_count == 128:
                flush()
    flush()


def _encode_line_numpy(line: bytes, width: int) -> bytes:
    row = _np.frombuffer(line, dtype=_np.uint8).reshape(width, 3)
    diff = _np.any(row[1:] != row[:-1], axis=1)
    starts = _np.concatenate(([0], _np.flatnonzero(diff) + 1)).tolist()
    ends = starts[1:] + [width]
    out = bytearray()
    _pack_runs(out, width, starts, ends, lambda i: line[i * 3:i * 3 + 3])
    return bytes(out)


def _encode_line_python(line: bytes, width: int) -> bytes:
    starts = []
    previous = None
    for i in range(width):
        triple = line[i * 3:i * 3 + 3]
        if triple != previous:
            starts.append(i)
            previous = triple
    ends = starts[1:] + [width]
    out = bytearray()
    _pack_runs(out, width, starts, ends, lambda i: line[i * 3:i * 3 + 3])
    return bytes(out)


# ----------------------------------------------------------------------------
# decoding (self-check / inspection)
# ----------------------------------------------------------------------------
def decode(data: bytes):
    """Decode a URF stream into [(PIL.Image, dpi), ...]. Raises on malformed input."""
    if data[:8] != b"UNIRAST\x00":
        raise ValueError(f"not a URF stream: {data[:8]!r}")
    (page_count,) = struct.unpack(">I", data[8:12])
    offset = 12
    pages = []
    for _ in range(page_count):
        bpp, colorspace, duplex, quality = data[offset:offset + 4]
        _u0, _u1, width, height, dpi, _u2, _u3 = struct.unpack(">7I", data[offset + 4:offset + 32])
        offset += 32
        if bpp not in (24, 8) or colorspace not in (1, 0):
            raise ValueError(f"unsupported URF page: bpp={bpp} colorspace={colorspace}")
        pixel = 3 if bpp == 24 else 1
        stride = width * pixel
        if bpp == 8:
            pixels = bytearray(stride * height)
        else:
            pixels = bytearray(stride * height)
        y = 0
        while y < height:
            repeat = data[offset] + 1
            offset += 1
            line = bytearray(stride)
            position = 0
            while position < width:
                code = struct.unpack("b", data[offset:offset + 1])[0]
                offset += 1
                if code == -128:
                    line[position * pixel:] = b"\xff" * ((width - position) * pixel)
                    position = width
                elif 0 <= code <= 127:
                    count = min(code + 1, width - position)
                    rgb = data[offset:offset + pixel]
                    offset += pixel
                    line[position * pixel:(position + count) * pixel] = rgb * count
                    position += count
                else:
                    count = min(-code + 1, width - position)
                    line[position * pixel:(position + count) * pixel] = data[offset:offset + pixel * count]
                    offset += pixel * count
                    position += count
            chunk = bytes(line)
            for i in range(repeat):
                if y + i >= height:
                    break
                pixels[(y + i) * stride:(y + i + 1) * stride] = chunk
            y += repeat
        mode = "RGB" if bpp == 24 else "L"
        pages.append((Image.frombytes(mode, (width, height), bytes(pixels)), dpi))
    if offset != len(data):
        raise ValueError(f"trailing bytes in URF stream: consumed {offset} of {len(data)}")
    return pages


def verify(images, urf: bytes, dpi: int = 600) -> tuple[bool, int, str]:
    """Round-trip check: decode `urf` and compare with the source images."""
    decoded = decode(urf)
    if len(decoded) != len(images):
        return False, -1, f"page count {len(decoded)} != {len(images)}"
    mismatched = 0
    for index, (source, (target, decoded_dpi)) in enumerate(zip(images, decoded)):
        a = source.convert("RGB")
        b = target.convert("RGB")
        if a.size != b.size:
            return False, -1, f"page {index}: size {a.size} != {b.size}"
        if a.tobytes() != b.tobytes():
            diff = sum(1 for pa, pb in zip(a.tobytes(), b.tobytes()) if pa != pb)
            mismatched += diff
        if decoded_dpi != dpi:
            return False, -1, f"page {index}: dpi {decoded_dpi} != {dpi}"
    if mismatched:
        return False, mismatched, f"{mismatched} byte(s) differ"
    return True, 0, "exact match"


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("usage: urf.py decode <file.urf> <out.png>")
        raise SystemExit(2)
    pages = decode(open(sys.argv[1], "rb").read())
    pages[0][0].save(sys.argv[2])
    print(f"decoded {len(pages)} page(s), first at {pages[0][1]} dpi -> {sys.argv[2]}")
