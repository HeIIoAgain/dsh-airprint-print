#!/usr/bin/env python3
"""Rendering helpers: page geometry, fonts, test pages, image pages, text pages.

Everything here is pure Pillow (+ optional numpy in urf.py). Fonts are resolved
from the system; Chinese text falls back to a cached Noto Sans SC download.
"""

from __future__ import annotations

import colorsys
import datetime
import os
import socket
import textwrap
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# millimetres, portrait
PAGE_SIZES = {
    "a4": (210.0, 297.0),
    "a5": (148.0, 210.0),
    "a6": (105.0, 148.0),
    "letter": (215.9, 279.4),
    "legal": (215.9, 355.6),
    "4x6": (101.6, 152.4),
    "5x7": (127.0, 177.8),
    "10x15": (100.0, 150.0),
}

BLACK = (20, 20, 20)
GRAY = (110, 110, 110)
LIGHT = (200, 200, 200)
ACCENT = (26, 115, 232)

_REGULAR = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "/Library/Fonts/Arial.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
]
_BOLD = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "C:/Windows/Fonts/segoeuib.ttf",
]
_MONO = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
    "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
    "C:/Windows/Fonts/consola.ttf",
]
_MONO_BOLD = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSansMono-Bold.ttf",
    "C:/Windows/Fonts/consolab.ttf",
]
_CJK_REGULAR = [
    "~/.cache/dsh-airprint/fonts/NotoSansSC-Regular.otf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/arphic/uming.ttc",
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simsun.ttc",
    "/System/Library/Fonts/PingFang.ttc",
]
_CJK_BOLD = [
    "~/.cache/dsh-airprint/fonts/NotoSansSC-Bold.otf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Bold.otf",
    "C:/Windows/Fonts/msyhbd.ttc",
]

_CJK_DOWNLOAD = {
    "regular": ("NotoSansSC-Regular.otf",
                "https://raw.githubusercontent.com/notofonts/noto-cjk/main/Sans/SubsetOTF/SC/NotoSansSC-Regular.otf"),
    "bold": ("NotoSansSC-Bold.otf",
             "https://raw.githubusercontent.com/notofonts/noto-cjk/main/Sans/SubsetOTF/SC/NotoSansSC-Bold.otf"),
}

_font_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


def page_pixels(page_size: str, dpi: int) -> tuple[int, int]:
    """Page dimensions in pixels for a named size at `dpi`."""
    key = page_size.lower().replace(" ", "")
    if key not in PAGE_SIZES:
        raise SystemExit(f"unknown page size {page_size!r}; choose from {', '.join(PAGE_SIZES)}")
    width_mm, height_mm = PAGE_SIZES[key]
    return (round(width_mm / 25.4 * dpi), round(height_mm / 25.4 * dpi))


def _first_existing(paths) -> str | None:
    for path in paths:
        candidate = Path(os.path.expanduser(path))
        if candidate.is_file():
            return str(candidate)
    return None


def has_cjk_font() -> bool:
    return _first_existing(_CJK_REGULAR) is not None


def needs_cjk(text: str) -> bool:
    return any(ord(ch) > 0x2E80 for ch in text)


def ensure_cjk_font(variant: str = "regular", timeout: float = 60.0) -> str | None:
    """Return a CJK font path, downloading Noto Sans SC into the cache if needed."""
    path = _first_existing(_CJK_BOLD if variant == "bold" else _CJK_REGULAR)
    if path:
        return path
    filename, url = _CJK_DOWNLOAD[variant]
    target = Path(os.path.expanduser(f"~/.cache/dsh-airprint/fonts/{filename}"))
    if not target.is_file():
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            print(f"downloading CJK font {filename} ...", flush=True)
            with urllib.request.urlopen(url, timeout=timeout) as response, \
                    open(target, "wb") as handle:
                handle.write(response.read())
        except Exception as exc:
            print(f"warning: could not fetch a CJK font ({exc}); "
                  f"Chinese text may render as boxes", flush=True)
            return None
    return str(target)


def font(kind: str = "regular", size_px: int = 40, text: str = "") -> ImageFont.FreeTypeFont:
    """Load a font, preferring a CJK-capable one when `text` needs it."""
    key = (kind, size_px)
    if key in _font_cache:
        return _font_cache[key]
    cjk = needs_cjk(text)
    path = None
    if cjk:
        path = _first_existing(_CJK_BOLD if kind == "bold" else _CJK_REGULAR)
        if path is None:
            path = ensure_cjk_font("bold" if kind == "bold" else "regular")
    if path is None:
        candidates = {"regular": _REGULAR, "bold": _BOLD,
                      "mono": _MONO, "mono-bold": _MONO_BOLD}.get(kind, _REGULAR)
        path = _first_existing(candidates)
    if path is None:
        raise SystemExit("no usable font found; install fonts-dejavu-core or pass a page "
                         "that needs no text")
    loaded = ImageFont.truetype(path, size_px)
    _font_cache[key] = loaded
    return loaded


def _gradient(width: int, height: int) -> Image.Image:
    strip = Image.new("RGB", (width, 1))
    pixels = strip.load()
    for x in range(width):
        r, g, b = colorsys.hsv_to_rgb(x / max(width - 1, 1), 0.85, 0.95)
        pixels[x, 0] = (int(r * 255), int(g * 255), int(b * 255))
    return strip.resize((width, height), Image.NEAREST)


def _localize(latin: str, chinese: str) -> str:
    return chinese if has_cjk_font() else latin


def test_page(
    *,
    dpi: int = 600,
    page_size: str = "a4",
    title: str | None = None,
    subtitle: str | None = None,
    printer_label: str = "",
    host: str = "",
    job_name: str = "",
    source: str | None = None,
) -> Image.Image:
    """Build a diagnostic test page (A4 600 dpi by default)."""
    width, height = page_pixels(page_size, dpi)
    sx, sy = width / 4961.0, height / 7016.0
    s = min(sx, sy)
    image = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    margin = round(380 * sx)
    now = datetime.datetime.now()

    title = title or _localize("PRINT TEST PAGE", "DSH 测试打印页")
    subtitle = subtitle or _localize(
        "Random test page from your DSH agent",
        "来自 DSH 智能体的随机测试打印页")

    draw.rectangle([0, 0, width, round(56 * sy)], fill=ACCENT)
    draw.text((margin, round(400 * sy)), title, font=font("bold", round(250 * s), title), fill=BLACK)
    draw.text((margin, round(800 * sy)), subtitle, font=font("regular", round(105 * s), subtitle), fill=GRAY)
    draw.line([margin, round(990 * sy), width - margin, round(990 * sy)], fill=LIGHT, width=max(4, round(8 * s)))

    rows = [
        ("Time      ", now.strftime("%Y-%m-%d %H:%M:%S") + " " + _tz_label()),
        ("From      ", socket.gethostname() + "  (" + _source_label(source) + ")"),
        ("Target    ", printer_label or f"printer @ {host}"),
        ("Transport ", f"IPP over HTTP :631  ->  /ipp/print"),
        ("Format", "Apple Raster (URF) %d dpi, %s, sRGB 24bpp" % (dpi, page_size.upper())),
        ("Job name  ", job_name or f"dsh-test-{int(now.timestamp())}"),
    ]
    mono = font("mono", round(92 * s))
    mono_bold = font("mono-bold", round(92 * s))
    y = round(1090 * sy)
    for key, value in rows:
        draw.text((margin, y), key, font=mono_bold, fill=ACCENT)
        draw.text((margin + round(620 * sx), y), value, font=mono, fill=BLACK)
        y += round(148 * sy)

    bar_x0, bar_x1 = margin, width - margin
    bar_y0, bar_y1 = round(2040 * sy), round(2360 * sy)
    image.paste(_gradient(bar_x1 - bar_x0, bar_y1 - bar_y0), (bar_x0, bar_y0))
    draw.rectangle([bar_x0, bar_y0, bar_x1 - 1, bar_y1 - 1], outline=LIGHT, width=max(2, round(4 * s)))

    names = ["RED", "GREEN", "BLUE", "CYAN", "MAGENTA", "YELLOW", "BLACK", "50% GRAY"]
    colors = [(220, 30, 30), (30, 160, 60), (30, 80, 220), (0, 170, 200),
              (200, 30, 160), (240, 200, 0), (25, 25, 25), (128, 128, 128)]
    size = round(400 * s)
    gap = ((bar_x1 - bar_x0) - len(colors) * size) // (len(colors) - 1)
    swatch_y = round(2480 * sy)
    label_font = font("mono-bold", round(58 * s))
    for index, (name, color) in enumerate(zip(names, colors)):
        x = bar_x0 + index * (size + gap)
        draw.rectangle([x, swatch_y, x + size, swatch_y + size], fill=color,
                       outline=(90, 90, 90), width=max(2, 3))
        text_width = draw.textlength(name, font=label_font)
        draw.text((x + (size - text_width) / 2, swatch_y + size + round(24 * sy)),
                  name, font=label_font, fill=GRAY)

    box = [margin, round(3200 * sy), width - margin, round(3900 * sy)]
    draw.rounded_rectangle(box, radius=round(40 * s), outline=ACCENT, width=max(4, round(10 * s)))
    ok_text = _localize("Print path OK", "打印链路正常")
    caption = _localize("If you can read this page, the whole print path works.",
                        "如果你能看到这一页，说明整条打印链路是通的。")
    draw.text((box[0] + round(90 * sx), box[1] + round(90 * sy)), ok_text,
              font=font("bold", round(210 * s), ok_text), fill=BLACK)
    draw.text((box[0] + round(90 * sx), box[1] + round(400 * sy)), caption,
              font=font("regular", round(95 * s), caption), fill=GRAY)
    draw.text((margin, round(4100 * sy)),
              _localize("— end of test page —", "— 测试页结束 —"),
              font=font("regular", round(80 * s), "测试页"), fill=LIGHT)

    draw.rectangle([margin, round(6600 * sy), width - margin, round(6612 * sy)], fill=LIGHT)
    footer = f"DeepSeek Harness · {now:%Y-%m-%d %H:%M} · URF 24bpp · {page_size.upper()} {dpi}dpi"
    draw.text((margin, round(6660 * sy)), footer, font=font("regular", round(62 * s)), fill=GRAY)
    return image


def image_page(
    path: str | Path,
    *,
    dpi: int = 600,
    page_size: str = "a4",
    scale: str = "fit",
    margin_mm: float = 8.0,
) -> Image.Image:
    """Place an image file on a blank page (fit = keep aspect, fill = crop to page)."""
    source = Image.open(path)
    try:
        source.load()
    except Exception as exc:
        raise SystemExit(f"cannot read image {path}: {exc}")
    source = source.convert("RGB")
    width, height = page_pixels(page_size, dpi)
    margin = round(margin_mm / 25.4 * dpi)
    box_w, box_h = width - 2 * margin, height - 2 * margin
    if scale == "none":
        target = source
    else:
        ratio_w = box_w / source.width
        ratio_h = box_h / source.height
        ratio = max(ratio_w, ratio_h) if scale == "fill" else min(ratio_w, ratio_h)
        target = source.resize((max(1, round(source.width * ratio)),
                                max(1, round(source.height * ratio))),
                               Image.LANCZOS)
        if scale == "fill":
            left = max(0, (target.width - box_w) // 2)
            top = max(0, (target.height - box_h) // 2)
            target = target.crop((left, top, left + box_w, top + box_h))
    canvas = Image.new("RGB", (width, height), (255, 255, 255))
    x = (width - target.width) // 2
    y = (height - target.height) // 2
    canvas.paste(target, (x, y))
    return canvas


def text_pages(
    text: str,
    *,
    dpi: int = 600,
    page_size: str = "a4",
    font_pt: float = 11.0,
    margin_mm: float = 15.0,
    title: str | None = None,
) -> list[Image.Image]:
    """Render plain text (wrapped) onto as many pages as needed."""
    width, height = page_pixels(page_size, dpi)
    margin = round(margin_mm / 25.4 * dpi)
    size_px = max(8, round(font_pt * dpi / 72.0))
    line_height = round(size_px * 1.45)
    body_font = font("regular", size_px, text)
    usable_width = width - 2 * margin
    lines: list[str] = []
    for paragraph in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if not paragraph:
            lines.append("")
            continue
        wrapped = textwrap.wrap(paragraph, width=200) or [""]
        # re-wrap by measured pixel width (font metric aware)
        for chunk in wrapped:
            current = ""
            for word in chunk.split(" "):
                candidate = (current + " " + word).strip()
                if (current and _text_width(candidate, body_font) > usable_width) or \
                        (not current and _text_width(word, body_font) > usable_width):
                    if current:
                        lines.append(current)
                    current = word
                else:
                    current = candidate
            if current:
                lines.append(current)

    pages: list[Image.Image] = []
    index = 0
    first_page = True
    while index < len(lines) or first_page:
        canvas = Image.new("RGB", (width, height), (255, 255, 255))
        draw = ImageDraw.Draw(canvas)
        y = margin
        if first_page and title:
            title_font = font("bold", round(size_px * 1.9), title)
            draw.text((margin, y), title, font=title_font, fill=BLACK)
            y += round(size_px * 1.9 * 1.4)
        while index < len(lines):
            line = lines[index]
            if y + line_height > height - margin:
                break
            draw.text((margin, y), line, font=body_font, fill=BLACK)
            y += line_height
            index += 1
        pages.append(canvas)
        first_page = False
        if index >= len(lines):
            break
    return pages


def _text_width(text: str, used_font) -> float:
    measure = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    return measure.textlength(text, font=used_font)


def _tz_label() -> str:
    now = datetime.datetime.now().astimezone()
    offset = now.utcoffset() or datetime.timedelta()
    minutes = int(offset.total_seconds() // 60)
    sign = "+" if minutes >= 0 else "-"
    minutes = abs(minutes)
    return f"(UTC{sign}{minutes // 60:02d}:{minutes % 60:02d})"


def _source_label(explicit: str | None) -> str:
    if explicit:
        return explicit
    return "Python " + __import__("platform").python_version().split()[0]


if __name__ == "__main__":
    import sys

    out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/test_page.png"
    test_page(host="192.168.1.50", printer_label="test printer").save(out)
    print(f"wrote {out}")
