"""Shareable report images (PNG/PDF) for a single check and for a tool comparison."""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .imageio import to_rgb
from .pipeline import CheckResult

INK = (29, 29, 31)
MUTED = (110, 110, 115)
LINE = (225, 225, 228)
LEVEL_COLORS = {"good": (31, 157, 85), "ok": (217, 119, 6), "bad": (220, 38, 38)}
RED = (220, 38, 38)
BLUE = (37, 99, 235)
IGNORED = (205, 205, 205)

_FONT_CANDIDATES = {
    False: [
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "DejaVuSans.ttf",
    ],
    True: [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "C:/Windows/Fonts/segoeuib.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "DejaVuSans-Bold.ttf",
    ],
}


@lru_cache(maxsize=64)
def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    for path in _FONT_CANDIDATES[bold]:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _text_w(draw: ImageDraw.ImageDraw, text: str, f) -> int:
    return int(draw.textlength(text, font=f))


def _wrap(draw: ImageDraw.ImageDraw, text: str, f, width: int) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if _text_w(draw, trial, f) <= width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def _fit(img: np.ndarray, width: int) -> Image.Image:
    pil = Image.fromarray(to_rgb(img))
    h = round(pil.height * width / pil.width)
    return pil.resize((width, h), Image.Resampling.LANCZOS)


def build_report(
    result: CheckResult,
    tool: str,
    job_name: str | None = None,
    when: datetime | None = None,
) -> Image.Image:
    """One landscape page: both images, the overlay, the score and the tool."""
    when = when or datetime.now()
    W, M, GAP = 2400, 90, 36
    col = (W - 2 * M - 2 * GAP) // 3
    tiles = [
        ("Original model view", _fit(result.original, col)),
        (f"AI render ({tool})", _fit(result.render, col)),
        ("What changed", _fit(result.overlay, col)),
    ]
    img_h = max(t[1].height for t in tiles)

    probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    body = font(30)
    findings = _findings(result)
    finding_lines = [ln for f in findings for ln in _wrap(probe, f, body, W - 2 * M - 40)]
    H = 330 + 60 + img_h + 150 + 48 * len(finding_lines) + 140

    page = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(page)

    # Header
    d.text((M, M), "Render check", font=font(64, True), fill=INK)
    sub = " · ".join(x for x in [job_name, tool, when.strftime("%d %b %Y, %H:%M")] if x)
    d.text((M, M + 92), sub, font=font(32), fill=MUTED)

    # Score block (right aligned)
    color = LEVEL_COLORS[result.level]
    score_txt = f"{result.score:.0f}"
    sf, of, lf = font(120, True), font(40), font(38, True)
    score_w = _text_w(d, score_txt, sf)
    right = W - M
    d.text((right - _text_w(d, "/100", of), M + 70), "/100", font=of, fill=MUTED)
    score_x = right - _text_w(d, "/100", of) - 12 - score_w
    d.text((score_x, M - 10), score_txt, font=sf, fill=INK)
    r = 26
    cx, cy = score_x - 40 - r, M + 55
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)
    d.text((right - _text_w(d, result.label, lf), M + 140), result.label, font=lf, fill=color)

    y = 330
    d.line((M, y - 40, W - M, y - 40), fill=LINE, width=2)
    cap = font(30, True)
    for i, (title, tile) in enumerate(tiles):
        x = M + i * (col + GAP)
        d.text((x, y), title, font=cap, fill=INK)
        page.paste(tile, (x, y + 52))
        d.rectangle((x, y + 52, x + tile.width - 1, y + 52 + tile.height - 1), outline=LINE, width=2)
    y += 52 + img_h + 36

    # Legend
    x = M
    for color_, label in ((RED, "Missing or moved from your model"), (BLUE, "Added by the AI"), (IGNORED, "Ignored")):
        d.rounded_rectangle((x, y + 4, x + 34, y + 34), radius=6, fill=color_)
        d.text((x + 48, y), label, font=body, fill=INK)
        x += 48 + _text_w(d, label, body) + 60
    y += 90

    for line in finding_lines:
        d.text((M, y), line, font=body, fill=INK)
        y += 48

    d.text((M, H - M + 10), "Made with Render QA. Images were checked on this computer and not uploaded anywhere.",
           font=font(24), fill=MUTED)
    return page


def _findings(result: CheckResult) -> list[str]:
    c = result.comparison
    out = [
        f"{c.recall:.0%} of the lines in your model view appear in the render.",
        f"{1 - c.precision:.0%} of the lines in the render are new (not in your model).",
    ]
    if result.missing_areas or result.added_areas:
        out.append(
            f"{_areas(result.missing_areas)} missing or moved, {_areas(result.added_areas)} added by the AI."
        )
    else:
        out.append("No clear problem areas found.")
    out += result.warnings
    return out


def _areas(n: int) -> str:
    return f"{n} area" if n == 1 else f"{n} areas"


def to_png_bytes(image: Image.Image) -> bytes:
    buf = io.BytesIO()
    image.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def to_pdf_bytes(image: Image.Image) -> bytes:
    buf = io.BytesIO()
    image.convert("RGB").save(buf, "PDF", resolution=200.0)
    return buf.getvalue()


@dataclass
class ToolSummary:
    tool: str
    average: float
    count: int
    level: str


def build_comparison_summary(
    tools: list[ToolSummary],
    table: list[tuple[str, dict[str, float]]],
    when: datetime | None = None,
) -> Image.Image:
    """Leaderboard bars plus a job-by-tool score grid."""
    when = when or datetime.now()
    W, M = 2000, 80
    tool_names = [t.tool for t in tools]
    bar_h, bar_gap = 64, 26
    row_h = 58
    H = 260 + len(tools) * (bar_h + bar_gap) + 120 + (len(table) + 1) * row_h + 120
    page = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(page)
    d.text((M, M), "AI tool comparison", font=font(60, True), fill=INK)
    n_jobs = len(table)
    d.text((M, M + 84), f"{n_jobs} job{'s' if n_jobs != 1 else ''} · {when:%d %b %Y}", font=font(30), fill=MUTED)

    y = 260
    label_w = 480
    track = W - 2 * M - label_w - 200
    body, bold = font(32), font(32, True)
    for rank, t in enumerate(tools, 1):
        d.text((M, y + 12), f"{rank}. {t.tool}", font=bold, fill=INK)
        x0 = M + label_w
        d.rounded_rectangle((x0, y, x0 + track, y + bar_h), radius=12, fill=(243, 243, 245))
        w = max(12, round(track * t.average / 100))
        d.rounded_rectangle((x0, y, x0 + w, y + bar_h), radius=12, fill=LEVEL_COLORS[t.level])
        d.text((x0 + track + 24, y + 12), f"{t.average:.0f}", font=bold, fill=INK)
        d.text((x0 + track + 90, y + 16), f"({t.count} render{'s' if t.count != 1 else ''})", font=font(24), fill=MUTED)
        y += bar_h + bar_gap

    y += 60
    first = 520
    cw = (W - 2 * M - first) // max(1, len(tool_names))
    small = font(26, True)
    d.text((M, y - 16), "Job", font=small, fill=MUTED)
    for i, name in enumerate(tool_names):
        for j, line in enumerate(_wrap(d, name, small, cw - 10)[:2]):
            d.text((M + first + i * cw, y - 16 + j * 30), line, font=small, fill=MUTED)
    y += row_h
    for job, scores in table:
        d.line((M, y - 12, W - M, y - 12), fill=LINE, width=2)
        d.text((M, y), _wrap(d, job, body, first - 20)[0], font=body, fill=INK)
        for i, name in enumerate(tool_names):
            v = scores.get(name)
            d.text((M + first + i * cw, y), "–" if v is None else f"{v:.0f}", font=body, fill=INK)
        y += row_h
    d.text((M, H - M), "Higher is better. 100 means the render kept your model's geometry exactly.",
           font=font(24), fill=MUTED)
    return page
