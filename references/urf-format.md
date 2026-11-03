# Apple Raster (URF / UNIRAST) format

Reverse-engineered from the format, cross-checked against Ghostscript's
`appleraster`/`urf` device output and the `urftopdf` decoder. Verified against a
Brother DCP-T436W (it prints pages produced by this encoder correctly).

All integers are **big-endian**.

## Container

```
offset  size   field
0       8      "UNIRAST\0"
8       4      page_count

per page:
0       1      bits_per_pixel      24 (or 8 for grayscale)
1       1      color_space         1 = sRGB (0 = grayscale)
2       1      duplex_mode         0
3       1      quality             3..5 (4 = normal; printer advertises PQ3-4-5)
4       4      unknown0            0
8       4      unknown1            0
12      4      width               pixels
16      4      height              pixels
20      4      dots_per_inch       300 or 600
24      4      unknown2            0
28      4      unknown3            0
32      ...    raster data
```

Width/height must match the target media at that dpi, e.g. A4 at 600 dpi =
`round(210/25.4*600) x round(297/25.4*600)` = **4961 x 7016**. The printer takes
the page geometry from these fields, not from IPP attributes, so get it right
(a letter-sized raster on A4 paper is clipped/scaled).

## Raster data

Scanlines are encoded one after another. Each scanline starts with one byte:

```
line_repeat_minus_one : repeat the *next decoded line* that many extra times
                        (0 = draw once, 255 = draw 256 times)
```

Then PackBits-like **pixel** codes (inverted vs. TIFF PackBits) until exactly
`width` pixels are filled:

| code byte | signed | meaning |
|---|---|---|
| `0x80` | -128 | fill the rest of the scanline with white (255,255,255) |
| `0x00`..`0x7F` | 0..127 | repeat the next 3-byte RGB pixel `code+1` times |
| `0x81`..`0xFF` | -127..-1 | copy `(256-code)+1` = `-code+1` RGB triples verbatim |

So a literal run of `n` pixels (2 ≤ n ≤ 128) is `[257-n] + n*3 bytes`, and a
repeat of `n` pixels (1 ≤ n ≤ 128) is `[n-1] + 3 bytes`.

## Rules that bite

1. **The line-repeat byte repeats the following line, it does not precede the
   line it was just read with.** Think "this line will be drawn N times", N =
   byte+1. Emit the repeat byte first, then that line's codes.
2. **A fully white scanline is `[repeat][0x80]`** — 2 bytes, no pixel data. A
   trailing white run can also be closed with `0x80` instead of repeat codes.
3. **Never append a code after the scanline is full.** A stray byte is read as
   the *next* line's repeat counter (255 → 256 repeated lines) and the whole
   page scrambles. This was a real bug in the first version of the encoder.
4. A single leftover literal pixel cannot be encoded as a literal (minimum
   literal is 2 pixels): emit it as a 1-pixel repeat `[0x00] + RGB`.
5. Colors are 8-bit RGB triples in sRGB order, white = `FF FF FF`.

## Minimal known-good example

One 2x2 white page at 600 dpi, quality 4:

```
55 4E 49 52 41 53 54 00          "UNIRAST\0"
00 00 00 01                       1 page
18 01 00 04                       bpp=24, sRGB, no duplex, quality 4
00 00 00 00  00 00 00 00          unknown0, unknown1
00 00 00 02  00 00 00 02          width=2, height=2
00 00 02 58                       600 dpi
00 00 00 00  00 00 00 00          unknown2, unknown3
01 FF 80                          line-repeat 2 (0x01 -> 2 lines), fill-rest white
```

## Verifying an encoder

`airprint.py selftest` builds a small synthetic page, encodes it, decodes it and
compares every byte. `airprint.py encode FILE --out x.urf` +
`decode x.urf --out x.png` is the manual path. The decoder lives in
`scripts/urf.py` and also checks that the stream is consumed exactly — trailing
bytes are an error, which is the sanity check that catches rule 3.
