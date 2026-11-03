"""One catalog for every poster style.

A Style bundles three things so they cannot drift apart:
  prompt   the words added to the image prompt,
  effects  Pillow finishing steps that run on the picture after the image model (or demo engine),
  layout   where overlay.py puts the title.

Pillow only (no numpy). Deterministic for a given seed.
Use apply_style_effects(png, style_key, palette, seed) to finish an image.
"""
from __future__ import annotations

import io
import logging
import math
import random
from dataclasses import dataclass
from typing import Callable, Sequence

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageOps

log = logging.getLogger("l2p.styles")

Effect = Callable[[Image.Image, Sequence[str], int], Image.Image]

# ---------------------------------------------------------------- small helpers


def _rgb(color: str, default: tuple[int, int, int] = (255, 255, 255)) -> tuple[int, int, int]:
    c = color.lstrip("#")
    try:
        return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    except (ValueError, IndexError):
        return default


def _pick(palette: Sequence[str], i: int) -> tuple[int, int, int]:
    return _rgb(palette[i % len(palette)]) if palette else (136, 136, 136)


def _white(size: tuple[int, int]) -> Image.Image:
    return Image.new("RGB", size, (255, 255, 255))


def _noise(size: tuple[int, int], seed: int, amount: float) -> Image.Image:
    """Grey noise centred on 128. `amount` 0..1 scales how far it strays from 128."""
    rng = random.Random(seed)
    raw = Image.frombytes("L", size, rng.randbytes(size[0] * size[1]))
    return raw.point(lambda v: int(128 + (v - 128) * amount))


def _grain(img: Image.Image, seed: int, amount: float = 0.16) -> Image.Image:
    return ImageChops.add(img, _noise(img.size, seed, amount).convert("RGB"), 1.0, -128)


def _paper(img: Image.Image, seed: int, strength: float = 0.10) -> Image.Image:
    """Uneven paper tone (multiply) plus a little fibre grain."""
    w, h = img.size
    rng = random.Random(seed + 1)
    cw, ch = max(w // 24, 2), max(h // 24, 2)
    blotch = Image.frombytes("L", (cw, ch), rng.randbytes(cw * ch)).resize(img.size, Image.BICUBIC)
    lo = int(255 * (1 - strength))
    blotch = blotch.point(lambda v: lo + int(v * (255 - lo) / 255))
    return _grain(ImageChops.multiply(img, blotch.convert("RGB")), seed + 2, 0.08)


def _vignette(img: Image.Image, strength: float = 0.5) -> Image.Image:
    mask = Image.radial_gradient("L").resize(img.size, Image.BICUBIC)
    mask = mask.point(lambda v: int(255 * strength * (v / 255) ** 2.2))
    return Image.composite(Image.new("RGB", img.size, (0, 0, 0)), img, mask)


def _bloom(img: Image.Image, radius: float = 20, strength: float = 0.6, threshold: int = 170) -> Image.Image:
    scale = 255 / (255 - threshold)
    hi = img.point(lambda v: min(255, int(max(0, v - threshold) * scale)))
    glow = hi.filter(ImageFilter.GaussianBlur(radius)).point(lambda v: int(v * strength))
    return ImageChops.screen(img, glow)


def _saturate(img: Image.Image, factor: float) -> Image.Image:
    return ImageEnhance.Color(img).enhance(factor)


def _contrast(img: Image.Image, factor: float) -> Image.Image:
    return ImageEnhance.Contrast(img).enhance(factor)


def _shift(band: Image.Image, dx: int, dy: int) -> Image.Image:
    """Move one color band without wrapping around the edges (ImageChops.offset wraps)."""
    out = band.copy()
    out.paste(band, (dx, dy))
    return out


def _scanlines(img: Image.Image, gap: int = 4, alpha: float = 0.18) -> Image.Image:
    w, h = img.size
    mask = Image.new("L", img.size, 0)
    d = ImageDraw.Draw(mask)
    for y in range(0, h, gap):
        d.line([(0, y), (w, y)], fill=int(255 * alpha))
    return Image.composite(Image.new("RGB", img.size, (0, 0, 0)), img, mask)


def _halftone(img: Image.Image, ink: tuple[int, int, int], paper: tuple[int, int, int], cell: int = 9) -> Image.Image:
    """Round dots on paper: darker areas of `img` get bigger dots of `ink`."""
    w, h = img.size
    cols, rows = -(-w // cell), -(-h // cell)
    small = img.convert("L").resize((cols, rows), Image.BOX)
    px = small.load()
    s = 2  # draw at 2x, then shrink, for smooth dot edges
    canvas = Image.new("RGB", (w * s, h * s), paper)
    d = ImageDraw.Draw(canvas)
    for j in range(rows):
        for i in range(cols):
            r = cell * s * 0.72 * math.sqrt(1 - px[i, j] / 255)
            if r < 0.6:
                continue
            cx, cy = (i + 0.5) * cell * s, (j + 0.5) * cell * s
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=ink)
    return canvas.resize((w, h), Image.LANCZOS)


# ---------------------------------------------------------------- effects: fn(img, palette, seed) -> img


def fx_film(img, palette, seed):
    img = _contrast(img, 1.08)
    img = _bloom(img, radius=14, strength=0.35, threshold=190)
    img = _grain(img, seed, 0.24)
    return _vignette(img, 0.45)


def fx_riso(img, palette, seed):
    # Reduce the picture to the palette "inks" on cream paper. Dithering gives the stippled, printed shading.
    cream = (244, 238, 226)
    inks = [cream] + [_pick(palette, i) for i in range(min(max(len(palette), 1), 4))]
    flat = [c for ink in inks for c in ink]
    flat += [0] * (768 - len(flat))
    pal = Image.new("P", (1, 1))
    pal.putpalette(flat)
    flat_img = img.filter(ImageFilter.GaussianBlur(1.2)).quantize(palette=pal, dither=3).convert("RGB")  # 3 = Floyd-Steinberg
    r, g, b = flat_img.split()
    flat_img = Image.merge("RGB", (_shift(r, 3, 2), g, b))  # slight misregistration of one ink
    return _paper(flat_img, seed, 0.08)


def fx_neon(img, palette, seed):
    img = _saturate(_contrast(img, 1.15), 1.25)
    img = _bloom(img, radius=20, strength=0.7, threshold=150)
    return _grain(_vignette(img, 0.6), seed, 0.08)


def fx_paper_cut(img, palette, seed):
    img = ImageOps.posterize(img.filter(ImageFilter.MedianFilter(7)), 3)
    img = _saturate(img, 1.15)
    edges = img.convert("L").filter(ImageFilter.FIND_EDGES).point(lambda v: 255 if v > 18 else 0)
    shadow = ImageChops.offset(edges.filter(ImageFilter.GaussianBlur(2)), 3, 4).point(lambda v: int(v * 0.35))
    img = Image.composite(Image.new("RGB", img.size, (0, 0, 0)), img, shadow)  # soft drop shadows between layers
    return _paper(img, seed, 0.08)


def fx_watercolor(img, palette, seed):
    wash = img.filter(ImageFilter.MedianFilter(5)).filter(ImageFilter.GaussianBlur(1.2))
    wash = Image.blend(wash, _white(wash.size), 0.08)
    edges = wash.convert("L").filter(ImageFilter.FIND_EDGES).filter(ImageFilter.GaussianBlur(1.5))
    pool = ImageOps.invert(edges.point(lambda v: min(255, int(v * 3 * 0.35)))).convert("RGB")
    return _paper(ImageChops.multiply(wash, pool), seed, 0.14)  # pigment pools at the edges


def fx_bauhaus(img, palette, seed):
    img = ImageOps.posterize(img.filter(ImageFilter.MedianFilter(9)), 2)
    return _saturate(img, 1.3)


def fx_vapor(img, palette, seed):
    img = _saturate(img, 1.3)
    r, g, b = img.split()
    img = Image.merge("RGB", (_shift(r, 6, 0), g, _shift(b, -6, 0)))
    return _scanlines(_bloom(img, 18, 0.6, 160), 4, 0.18)


def fx_ukiyo(img, palette, seed):
    base = img.filter(ImageFilter.MedianFilter(5)).quantize(10).convert("RGB")
    edges = base.convert("L").filter(ImageFilter.FIND_EDGES).point(lambda v: 204 if v > 24 else 0)
    base = Image.composite(Image.new("RGB", base.size, (30, 24, 40)), base, edges)  # bold outlines
    base = Image.blend(base, Image.new("RGB", base.size, (240, 228, 200)), 0.12)  # washi tint
    return _paper(base, seed, 0.10)


def fx_deco(img, palette, seed):
    img = _vignette(_saturate(_contrast(img, 1.1), 1.1), 0.35)
    d = ImageDraw.Draw(img)
    w, h = img.size
    gold = (201, 162, 39)
    for inset, width in ((int(w * 0.035), 3), (int(w * 0.05), 1)):
        d.rectangle([inset, inset, w - inset, h - inset], outline=gold, width=width)
    return img


def fx_pixel(img, palette, seed):
    w, h = img.size
    small = img.resize((max(w // 8, 1), max(h // 8, 1)), Image.BOX).quantize(16).convert("RGB")
    return small.resize((w, h), Image.NEAREST)


def fx_blueprint(img, palette, seed):
    gray = ImageOps.autocontrast(img.convert("L"))
    lines = ImageOps.autocontrast(gray.filter(ImageFilter.FIND_EDGES)).point(lambda v: min(255, v * 3))
    tone = ImageChops.add(lines, gray.point(lambda v: v // 6))
    out = ImageOps.colorize(tone, black=(11, 58, 140), white=(214, 232, 255)).convert("RGBA")
    w, h = out.size
    grid = Image.new("RGBA", out.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(grid)
    for x in range(0, w, 48):
        d.line([(x, 0), (x, h)], fill=(255, 255, 255, 28))
    for y in range(0, h, 48):
        d.line([(0, y), (w, y)], fill=(255, 255, 255, 28))
    return Image.alpha_composite(out, grid).convert("RGB")


def fx_pop(img, palette, seed):
    img = ImageOps.posterize(_saturate(_contrast(img, 1.2), 1.6), 2)
    dots = _halftone(img, (0, 0, 0), (255, 255, 255), 10)
    dots = Image.blend(_white(img.size), dots, 0.28)
    return ImageChops.multiply(img, dots)


def fx_xerox(img, palette, seed):
    gray = ImageOps.autocontrast(_contrast(img.convert("L"), 1.3))
    bw = gray.convert("1").convert("L")  # dithered black and white, like a photocopy
    out = ImageOps.colorize(bw, black=(20, 20, 20), white=(236, 232, 220))
    return _grain(out, seed, 0.18)


def fx_pastel(img, palette, seed):
    soft = img.filter(ImageFilter.GaussianBlur(10))
    img = Image.blend(img, ImageChops.screen(img, soft), 0.5)
    img = _saturate(img, 0.85).point(lambda v: 28 + int(v * 0.89))  # lift the blacks
    return _grain(img, seed, 0.07)


EFFECTS: dict[str, Effect] = {
    "film": fx_film, "riso": fx_riso, "neon": fx_neon, "paper_cut": fx_paper_cut,
    "watercolor": fx_watercolor, "bauhaus": fx_bauhaus, "vapor": fx_vapor, "ukiyo": fx_ukiyo,
    "deco": fx_deco, "pixel": fx_pixel, "blueprint": fx_blueprint, "pop": fx_pop,
    "xerox": fx_xerox, "pastel": fx_pastel,
}

# ---------------------------------------------------------------- the catalog


@dataclass(frozen=True)
class Style:
    key: str
    label: str
    blurb: str          # one line for the UI
    prompt: str         # added to the image prompt
    effects: tuple[str, ...] = ()
    layout: str = "bottom_left"   # bottom_left | bottom_center | top_left
    uppercase: bool = False


_STYLE_LIST = [
    Style("risograph", "Risograph", "Two-ink overprint, halftone dots, cream paper",
          "risograph print, two-color ink overprint, coarse halftone dots, slight misregistration, flat shapes, off-white paper",
          ("riso",)),
    Style("film_grain", "Film grain", "35mm photo look, halation, heavy grain",
          "35mm film photograph, cinematic lighting, shallow depth of field, heavy film grain, halation, muted colors",
          ("film",)),
    Style("paper_cut", "Paper cut", "Stacked cardstock layers with soft shadows",
          "layered paper-cut art, stacked cardstock layers with soft shadows, handcrafted, simple bold shapes",
          ("paper_cut",), "bottom_center"),
    Style("neon_noir", "Neon noir", "Rain, glowing signs, deep shadows",
          "neon noir, rain-slick streets, glowing neon signs, deep shadows, high contrast, cinematic",
          ("neon",)),
    Style("watercolor", "Watercolor", "Soft washes, bleeding edges, paper grain",
          "loose watercolor painting, wet-on-wet washes, bleeding pigment edges, visible paper texture",
          ("watercolor",), "bottom_center"),
    Style("bauhaus", "Bauhaus", "Flat geometric shapes, strict composition",
          "Bauhaus poster design, geometric shapes, circles and triangles, flat primary colors, strict composition, asymmetrical balance",
          ("bauhaus",), "top_left", True),
    Style("vaporwave", "Vaporwave", "Pastel sunset, grid horizon, glitchy 80s dream",
          "vaporwave aesthetic, pastel gradient sky, retro-futuristic grid horizon, marble columns, glowing sun, dreamy 1980s",
          ("vapor",), "bottom_center"),
    Style("ukiyo_e", "Ukiyo-e woodblock", "Bold outlines, flat color, washi paper",
          "ukiyo-e Japanese woodblock print, bold ink outlines, flat areas of color, flowing waves and clouds, washi paper",
          ("ukiyo",)),
    Style("art_deco", "Art Deco", "Symmetry, gold lines, 1920s glamour",
          "Art Deco poster, symmetrical composition, gold geometric ornament, fan and sunburst patterns, elegant 1920s luxury",
          ("deco",), "bottom_center", True),
    Style("pixel_art", "Pixel art", "16-bit game scene, chunky pixels",
          "16-bit pixel art scene, limited color palette, crisp pixels, retro game background, parallax layers",
          ("pixel",), "bottom_left", True),
    Style("blueprint", "Blueprint", "White linework on blue, drafting grid",
          "technical blueprint drawing, white linework on blue, schematic diagrams, measurement marks, drafting grid",
          ("blueprint",), "top_left", True),
    Style("pop_art", "Pop art", "Bold outlines, Ben-Day dots, loud color",
          "pop art, bold black outlines, Ben-Day dots, saturated flat colors, comic book style",
          ("pop",), "bottom_left", True),
    Style("xerox_zine", "Xerox zine", "Photocopied punk collage, black and white",
          "photocopied punk zine collage, high-contrast black and white, torn paper edges, rough cut-and-paste layout, gritty texture",
          ("xerox",), "bottom_left", True),
    Style("pastel_dream", "Pastel dream", "Hazy, soft light, gentle gradients",
          "dreamy pastel illustration, soft diffused light, gentle gradients, hazy clouds, whimsical, airy",
          ("pastel",), "bottom_center"),
]

STYLES: dict[str, Style] = {s.key: s for s in _STYLE_LIST}
STYLE_KEYS: tuple[str, ...] = tuple(STYLES)
DEFAULT_STYLE = "risograph"


def get_style(key: str) -> Style:
    return STYLES.get(key) or STYLES[DEFAULT_STYLE]


def style_prompt(key: str) -> str:
    """Words to add to the image prompt for this style."""
    return get_style(key).prompt


def style_menu(allowed: Sequence[str] | None = None) -> str:
    """A compact list for the art director's instructions.

    allowed: only list styles whose key is in this collection (pass schemas.STYLE_PRESETS so the
    model never suggests a style the schema would reject). None lists every style.
    """
    chosen = [s for s in _STYLE_LIST if allowed is None or s.key in allowed]
    return "; ".join(f"{s.key} ({s.blurb.lower()})" for s in chosen or _STYLE_LIST)


def apply_style_effects(png: bytes, style: str, palette: Sequence[str], seed: int) -> bytes:
    """Run the style's finishing steps. Never raises: on any problem the original image is returned."""
    spec = STYLES.get(style)
    if spec is None or not spec.effects:
        return png
    try:
        img = Image.open(io.BytesIO(png)).convert("RGB")
        for name in spec.effects:
            img = EFFECTS[name](img, palette, seed)
        out = io.BytesIO()
        img.convert("RGB").save(out, format="PNG")
        return out.getvalue()
    except Exception as exc:  # noqa: BLE001 - a bad effect must never break poster generation
        log.info("style effect %s failed: %s", style, type(exc).__name__)
        return png
