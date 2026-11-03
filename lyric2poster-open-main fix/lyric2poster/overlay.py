"""Step 4: add the title and artist as real text, so the image model never has to draw letters."""
from __future__ import annotations

import io

from PIL import Image, ImageDraw, ImageFilter, ImageFont

_BOLD = [
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "DejaVuSans-Bold.ttf",
]
_REGULAR = [
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "DejaVuSans.ttf",
]

LAYOUTS = ("bottom_left", "bottom_center", "top_left")


def _font(size: int, bold: bool) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    for path in _BOLD if bold else _REGULAR:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    words, lines, line = text.split(), [], ""
    for word in words or [text]:
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=font) <= max_width or not line:
            line = trial
        else:
            lines.append(line)
            line = word
    lines.append(line)
    return lines


def _hex(color: str | None, default: tuple[int, int, int] = (255, 255, 255)) -> tuple[int, int, int]:
    if not color:
        return default
    c = color.lstrip("#")
    try:
        return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    except (ValueError, IndexError):
        return default


def _fit_line(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> str:
    """Shorten a line with an ellipsis until it fits."""
    while len(text) > 1 and draw.textlength(text + "…", font=font) > max_width:
        text = text[:-1]
    return text.rstrip() + "…"


def add_title_overlay(
    png: bytes,
    title: str,
    artist: str,
    *,
    layout: str = "bottom_left",
    accent: str | None = None,
    uppercase: bool = False,
) -> bytes:
    """Draw title and artist on the poster.

    layout     bottom_left, bottom_center or top_left (see styles.Style.layout)
    accent     hex color for a short rule above the title, for example brief.palette[0]
    uppercase  set the title in capitals
    The first three arguments work exactly as before, so old calls keep working.
    """
    if layout not in LAYOUTS:
        layout = "bottom_left"
    image = Image.open(io.BytesIO(png)).convert("RGBA")
    w, h = image.size
    margin = int(w * 0.08)
    max_width = w - 2 * margin
    on_top = layout == "top_left"
    centered = layout == "bottom_center"
    text = title.upper() if uppercase else title

    # dark gradient behind the text so it stays readable on any picture
    scrim_h = int(h * 0.40)
    ramp = Image.new("L", (1, scrim_h))
    ramp.putdata([int(215 * (y / (scrim_h - 1)) ** 1.5) for y in range(scrim_h)])
    scrim = Image.new("RGBA", (w, scrim_h), (0, 0, 0, 255))
    scrim.putalpha(ramp.resize((w, scrim_h)))
    if on_top:
        scrim = scrim.transpose(Image.FLIP_TOP_BOTTOM)
        image.alpha_composite(scrim, (0, 0))
    else:
        image.alpha_composite(scrim, (0, h - scrim_h))

    draw = ImageDraw.Draw(image)
    size = int(h * 0.062)
    while True:
        title_font = _font(size, bold=True)
        lines = _wrap(draw, text, title_font, max_width)
        if (len(lines) <= 2 and max(draw.textlength(x, font=title_font) for x in lines) <= max_width) or size <= 18:
            break
        size -= 2
    if len(lines) > 2:  # still too long at the smallest size: keep two lines and mark the cut
        lines = [lines[0], _fit_line(draw, " ".join(lines[1:]), title_font, max_width)]
    lines = [x if draw.textlength(x, font=title_font) <= max_width else _fit_line(draw, x, title_font, max_width) for x in lines]
    artist_font = _font(max(int(size * 0.5), 14), bold=False)

    line_h = int(size * 1.18)
    artist_h = int(artist_font.size * 1.4) if hasattr(artist_font, "size") else 24
    bar_h = max(3, int(h * 0.004))
    gap = int(size * 0.35)
    block_h = bar_h + gap + line_h * len(lines) + int(size * 0.1) + artist_h
    y = margin if on_top else h - margin - block_h

    def x_for(s: str, font) -> int:
        return int((w - draw.textlength(s, font=font)) / 2) if centered else margin

    jobs: list[tuple[tuple[int, int], str, object, tuple[int, int, int, int]]] = []
    bar_w = int(w * 0.12)
    bar_x = int((w - bar_w) / 2) if centered else margin
    bar = [bar_x, y, bar_x + bar_w, y + bar_h]
    y += bar_h + gap
    for line in lines:
        jobs.append(((x_for(line, title_font), y), line, title_font, (255, 255, 255, 255)))
        y += line_h
    y += int(size * 0.1)
    jobs.append(((x_for(artist, artist_font), y), artist, artist_font, (235, 235, 235, 255)))

    # soft shadow first, then the text on top
    shadow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    for (x, yy), s, font, _ in jobs:
        sd.text((x + 2, yy + 3), s, font=font, fill=(0, 0, 0, 150))
    image.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(4)))

    draw = ImageDraw.Draw(image)
    draw.rectangle(bar, fill=(*_hex(accent), 255))
    for xy, s, font, fill in jobs:
        draw.text(xy, s, font=font, fill=fill)

    out = io.BytesIO()
    image.convert("RGB").save(out, format="PNG")
    return out.getvalue()
