"""The exec report: a PowerPoint deck in The General Store's slide style.

Built in memory and handed back as bytes for the download button; nothing is
written to disk. Fonts are referenced by name (Cal Sans, Inconsolata, Geom
Light); PowerPoint substitutes them on machines that don't have them.
"""

from __future__ import annotations

import io
import math
from datetime import datetime
from pathlib import Path

from lxml import etree
from PIL import Image
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from pptx.enum.dml import MSO_LINE
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

from .imageio import encode_jpeg, fit_within, load_image
from .prompt_test import (
    FROM_MODEL, FROM_PREVIOUS, GUARDRAIL, OUTCOMES, ModelSummary, PromptTest, TestResults, edit_prompts,
    prompt_number, quality_series,
)

FOOTER = "The General Store — Copyright + Confidential 2026"
COPYRIGHT = "Copyright belongs to The General Store 2026"
LOGO = Path(__file__).resolve().parent.parent / "assets" / "tgs-logo.png"

BLACK, CREAM, CREAM_ALT, GREY, MID_GREY = "000000", "F4EFE4", "ECEBDE", "434343", "666666"
HEAD, MONO, BODY = "Cal Sans", "Inconsolata", "Geom Light"
W, H = 10.0, 5.625
RIGHT_EDGE = 9.3  # keep content clear of the rotated footer
# Line / bar colours: the first matches the slide's text colour, the rest stay readable on both backgrounds.
SERIES = ["C9A96E", "8C8C8C", "E07A5F", "81B29A", "F2CC8F", "7A9CC6", "B5838D", "5E8C61"]

PROMPT_TEXT_LIMIT = 400
APPENDIX_ROWS = 14
MODELS_PER_SLIDE = 8
IMAGE_SIDE = 1200


# ---------------------------------------------------------------- helpers

def _fg(dark: bool) -> str:
    return CREAM if dark else BLACK


def _rgb(hex_: str) -> RGBColor:
    return RGBColor.from_string(hex_)


def _set_background(slide, hex_: str) -> None:
    """A real slide background (not a shape), so it can't be selected by accident."""
    c_sld = slide._element.find(qn("p:cSld"))
    bg = etree.fromstring(
        '<p:bg xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
        f'<p:bgPr><a:solidFill><a:srgbClr val="{hex_}"/></a:solidFill><a:effectLst/></p:bgPr></p:bg>'
    )
    c_sld.insert(list(c_sld).index(c_sld.find(qn("p:spTree"))), bg)


def _text(slide, x, y, w, h, text, font, size, color, bold=False, align=PP_ALIGN.LEFT, anchor=None):
    """A text box; `text` may be a list of lines (one paragraph each)."""
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    if anchor is not None:
        tf.vertical_anchor = anchor
    lines = text if isinstance(text, list) else [text]
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        run = p.add_run()
        run.text = line
        run.font.name, run.font.size, run.font.bold = font, Pt(size), bold
        run.font.color.rgb = _rgb(color)
    return box


def _footer(slide, dark: bool) -> None:
    box = _text(slide, 8.67, 4.11, 2.10, 0.22, FOOTER, MONO, 5, _fg(dark))
    box.rotation = 270


def _slide(prs, dark: bool):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _set_background(slide, BLACK if dark else CREAM)
    _footer(slide, dark)
    return slide


def _title(slide, text: str, dark: bool, size: int = 30) -> None:
    _text(slide, 0.24, 0.24, 8.0, 0.6, text, HEAD, size, _fg(dark))


def _card(slide, x, y, w, h, dark: bool):
    shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    shape.adjustments[0] = 0.08
    shape.fill.background()
    shape.line.color.rgb = _rgb(GREY)
    shape.line.width = Pt(0.75)
    shape.shadow.inherit = False
    tf = shape.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    return shape


def _card_text(card, text: str, dark: bool, size: int = 9) -> None:
    p = card.text_frame.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    run = p.add_run()
    run.text = text
    run.font.name, run.font.size = MONO, Pt(size)
    run.font.color.rgb = _rgb(_fg(dark))


def _rule(slide, x, y, w, color: str, weight: float = 0.75, dotted: bool = False, vertical_h: float = 0):
    x2, y2 = (x, y + vertical_h) if vertical_h else (x + w, y)
    line = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x), Inches(y), Inches(x2), Inches(y2))
    line.line.color.rgb = _rgb(color)
    line.line.width = Pt(weight)
    if dotted:
        line.line.dash_style = MSO_LINE.ROUND_DOT


def _picture(slide, jpg: bytes, x, y, max_w, max_h) -> None:
    """Fits the image in the box, keeping its shape, centred."""
    iw, ih = Image.open(io.BytesIO(jpg)).size
    scale = min(max_w / iw, max_h / ih)
    w, h = iw * scale, ih * scale
    slide.shapes.add_picture(io.BytesIO(jpg), Inches(x + (max_w - w) / 2), Inches(y + (max_h - h) / 2),
                             Inches(w), Inches(h))


def _jpg(data: bytes | None) -> bytes | None:
    """Any uploaded or preview image as a small JPEG for the deck, or None if it can't be read."""
    if not data:
        return None
    try:
        return encode_jpeg(fit_within(load_image(data), IMAGE_SIDE), quality=85)
    except Exception:
        return None


def _style_chart(chart, dark: bool) -> None:
    chart.font.name = MONO
    chart.font.size = Pt(9)
    chart.font.color.rgb = _rgb(_fg(dark))
    for axis in (chart.category_axis, chart.value_axis):
        axis.format.line.color.rgb = _rgb(MID_GREY)
        axis.has_major_gridlines = False
    chart.value_axis.tick_labels.font.color.rgb = _rgb(_fg(dark))
    chart.category_axis.tick_labels.font.color.rgb = _rgb(_fg(dark))


def _table(slide, x, y, w, rows: list[list[str]], dark: bool, col_widths: list[float] | None = None,
           row_h: float = 0.26, size: int = 9):
    shape = slide.shapes.add_table(len(rows), len(rows[0]), Inches(x), Inches(y), Inches(w),
                                   Inches(row_h * len(rows)))
    table = shape.table
    if col_widths:
        for i, cw in enumerate(col_widths):
            table.columns[i].width = Inches(cw)
    for r, row in enumerate(rows):
        table.rows[r].height = Inches(row_h)
        for c, value in enumerate(row):
            cell = table.cell(r, c)
            cell.fill.background()
            cell.margin_top = cell.margin_bottom = Inches(0.02)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            p = cell.text_frame.paragraphs[0]
            p.alignment = PP_ALIGN.LEFT if c == 0 or not _numeric(value) else PP_ALIGN.RIGHT
            run = p.add_run()
            run.text = value.upper() if r == 0 else value
            run.font.name, run.font.size, run.font.bold = MONO, Pt(size), r == 0
            run.font.color.rgb = _rgb(_fg(dark))
    return table


def _numeric(value: str) -> bool:
    return value.replace(".", "", 1).replace("%", "").strip().isdigit()


def _num(value: float | None) -> str:
    return "—" if value is None else f"{value:.0f}"


def _stars(rating: int | None) -> str:
    return "★" * rating + "☆" * (5 - rating) if rating else "Not rated"


def _ranked(summaries: list[ModelSummary]) -> list[ModelSummary]:
    return sorted(summaries, key=lambda s: -1 if s.overall is None else s.overall, reverse=True)


# ---------------------------------------------------------------- slides

def _cover(prs, test: PromptTest, when: datetime) -> None:
    s = _slide(prs, dark=True)
    if LOGO.exists():
        s.shapes.add_picture(str(LOGO), Inches(4.34), Inches(1.98), Inches(1.16), Inches(1.16))
    box = _text(s, 1.34, 2.22, 2.73, 0.9, [test.name or "Prompt test", "THE GENERAL STORE",
                                          f"AI model prompt test · {when:%d %B %Y}"], MONO, 10, CREAM)
    box.text_frame.paragraphs[0].runs[0].font.bold = True


def _agenda(prs, items: list[str]) -> None:
    s = _slide(prs, dark=False)
    _text(s, 0.506, 0.646, 4.523, 0.754, "agenda", HEAD, 64, BLACK)
    step = min(0.6, 4.3 / max(1, len(items)))
    for i, item in enumerate(items):
        y = 0.646 + i * step
        _text(s, 5.249, y, 3.785, 0.3, item, MONO, 14.5, BLACK)
        if i < len(items) - 1:
            _rule(s, 5.249, y + 0.38, 3.523, BLACK if i == 0 else MID_GREY, 0.7 if i == 0 else 0.75)


def _answer_reason(best: ModelSummary) -> str:
    phrases = {
        "kept": lambda v: f"Kept {v:.0f}/100 of what it was told to keep",
        "rating": lambda v: f"Scored {v:.0f}/100 on your ratings",
        "drift": lambda v: f"Scored {v:.0f}/100 for staying close to your model",
        "quality": lambda v: f"Held its image quality at {v:.0f}/100 over the edits",
    }
    parts = {k: getattr(best, k) for k in best.parts_used if getattr(best, k) is not None}
    if not parts:
        return ""
    top = max(parts, key=parts.get)
    return phrases[top](parts[top])


def _statement(prs, big: str, small: str = "", label: str = "") -> None:
    s = _slide(prs, dark=True)
    if label:
        _text(s, 0.24, 0.24, 6.0, 0.3, label.upper(), MONO, 10, CREAM)
    size = 48 if len(big) <= 60 else 36 if len(big) <= 140 else 26 if len(big) <= 320 else 20
    _text(s, 0.6, 0.6, 8.6, 3.4, big, HEAD, size, CREAM_ALT, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    if small:
        _text(s, 0.6, 4.1, 8.6, 0.6, small, MONO, 14, CREAM, align=PP_ALIGN.CENTER)


def _leaderboard(prs, test: PromptTest, ranked: list[ModelSummary]) -> None:
    s = _slide(prs, dark=False)
    _title(s, "Leaderboard", dark=False)
    scored = [m for m in ranked if m.overall is not None]
    if scored:
        data = CategoryChartData()
        data.categories = [m.label for m in scored]
        data.add_series("Overall", [round(m.overall, 1) for m in scored])
        chart_h = min(2.2, 0.35 * len(scored) + 0.5)
        chart = s.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, Inches(0.3), Inches(0.9), Inches(8.9),
                                   Inches(chart_h), data).chart
        _style_chart(chart, dark=False)
        chart.has_legend = False
        chart.has_title = False
        chart.category_axis.reverse_order = True  # best at the top
        chart.value_axis.minimum_scale, chart.value_axis.maximum_scale = 0, 100
        plot = chart.plots[0]
        plot.gap_width = 60
        plot.series[0].format.fill.solid()
        plot.series[0].format.fill.fore_color.rgb = _rgb(BLACK)
        plot.has_data_labels = True
        plot.data_labels.number_format, plot.data_labels.number_format_is_linked = "0", False
        plot.data_labels.font.name, plot.data_labels.font.size = MONO, Pt(9)
    else:
        chart_h = 0.4
        _text(s, 0.3, 0.9, 8.9, 0.4, "No model could be scored yet", MONO, 12, BLACK)

    guards = [p for p in test.prompts if p.kind == GUARDRAIL]
    header = ["AI tool · model", "Overall", "Kept", "Rating", "Drift", "Quality"] + (["Guardrails"] if guards else [])
    rows = [header]
    for m in ranked:
        row = [m.label, _num(m.overall), _num(m.kept), _num(m.rating), _num(m.drift), _num(m.quality)]
        if guards:
            row.append(f"{m.guardrails['refused']} of {len(guards)} refused")
        rows.append(row)
    top = 0.9 + chart_h + 0.15
    row_h = max(0.16, min(0.26, (5.35 - top) / len(rows)))
    widths = [2.7, 0.95, 0.8, 0.9, 0.8, 0.95] + ([1.8] if guards else [])
    _table(s, 0.3, top, sum(widths), rows, dark=False, col_widths=widths, row_h=row_h,
           size=9 if row_h >= 0.22 else 7)


def _chaining(test: PromptTest) -> str:
    edits = edit_prompts(test)
    later = edits[1:]
    if later and all(p.starts_from == FROM_MODEL for p in later):
        return "Every prompt started again from the model view"
    if all(p.starts_from == FROM_PREVIOUS for p in later):
        return "Each prompt edited the render from the prompt before it"
    restarts = []
    if any(p.starts_from == FROM_MODEL for p in later):
        restarts.append("some started again from the model view")
    if any(p.starts_from not in (FROM_MODEL, FROM_PREVIOUS) for p in later):
        restarts.append("some went back to an earlier prompt's render")
    return "Prompts edited earlier renders as a chain; " + " and ".join(restarts)


def _how(prs, test: PromptTest) -> None:
    s = _slide(prs, dark=False)
    _title(s, "How we tested", dark=False)
    columns = [
        ("KEPT", "How much of the linework and materials survived outside the area each prompt was "
                 "allowed to change. Compared with the render it was edited from."),
        ("DRIFT", "How far the result has moved from your original model view, ignoring every area the "
                  "prompts so far were allowed to change."),
        ("QUALITY", "Sharpness, colour, artefacts and resolution compared with the first render in the "
                    "chain. It shows how much each tool degrades the image as edits pile up."),
        ("YOUR RATING", "Your 1–5 star rating of each render, turned into a 0–100 score. Guardrail "
                        "prompts are recorded as refused, partly or complied."),
    ]
    xs = [0.3, 2.55, 4.8, 7.05]
    for i, (head, body) in enumerate(columns):
        _text(s, xs[i], 1.05, 2.05, 0.4, head, MONO, 16.5, BLACK)
        _text(s, xs[i], 1.6, 2.05, 2.2, body, BODY, 10, BLACK)
        if i:
            _rule(s, xs[i] - 0.12, 1.0, 0, BLACK, dotted=True, vertical_h=2.85)
    heads = " · ".join(f"P{n} {p.title}" for n, p in enumerate(test.prompts, 1))
    _text(s, 0.3, 4.1, 8.9, 1.2, [f"PROMPTS: {heads}", _chaining(test)], MONO, 8, BLACK)


def _degradation(prs, test: PromptTest, results: TestResults) -> bool:
    rows = quality_series(test, results)
    if not rows:
        return False
    steps = max(r["step"] for r in rows)
    data = CategoryChartData()
    data.categories = [f"Step {i}" for i in range(steps + 1)]
    lines = {}
    for m in test.models:
        by_step = {}
        for r in rows:
            if r["model"] == m.id:
                by_step.setdefault(r["step"], []).append(r["quality"])
        if by_step:
            values = [round(sum(by_step[i]) / len(by_step[i]), 1) if i in by_step else None
                      for i in range(steps + 1)]
            lines[m.label] = values
            data.add_series(m.label, values)

    s = _slide(prs, dark=True)
    _title(s, "Degradation", dark=True)
    chart = s.shapes.add_chart(XL_CHART_TYPE.LINE_MARKERS, Inches(0.3), Inches(0.9), Inches(8.9), Inches(3.7),
                               data).chart
    _style_chart(chart, dark=True)
    chart.has_title = False
    chart.value_axis.minimum_scale, chart.value_axis.maximum_scale = 0, 110
    chart.has_legend = True
    chart.legend.position = XL_LEGEND_POSITION.BOTTOM
    chart.legend.include_in_layout = False
    chart.legend.font.name, chart.legend.font.size = MONO, Pt(9)
    chart.legend.font.color.rgb = _rgb(CREAM)
    for i, series in enumerate(chart.plots[0].series):
        colour = CREAM if i == 0 else SERIES[(i - 1) % len(SERIES)]
        series.format.line.color.rgb = _rgb(colour)
        series.format.line.width = Pt(2)
        series.smooth = False
        series.marker.format.fill.solid()
        series.marker.format.fill.fore_color.rgb = _rgb(colour)
        series.marker.format.line.color.rgb = _rgb(colour)
    _text(s, 0.3, 4.75, 8.9, 0.5, _degradation_takeaway(lines), MONO, 11, CREAM)
    return True


def _degradation_takeaway(lines: dict[str, list[float | None]]) -> str:
    drops = {}
    for label, values in lines.items():
        known = [v for v in values if v is not None]
        if len(known) >= 2:
            drops[label] = (known[0] - known[-1], known[-1])
    if not drops:
        return "Not enough chained edits yet to show degradation"
    worst = max(drops, key=lambda k: drops[k][0])
    best = min(drops, key=lambda k: drops[k][0])
    if worst == best:
        return f"{worst} ended at {drops[worst][1]:.0f}/100 quality after its edits"
    return (f"{worst} lost the most quality ({drops[worst][0]:.0f} points); "
            f"{best} held up best ({drops[best][0]:.0f} points)")


def _prompt_slides(prs, test: PromptTest, results: TestResults, start_dark: bool) -> int:
    dark = start_dark
    count = 0
    for p in edit_prompts(test):
        n = prompt_number(test, p.id)
        models = test.models or []
        if not any((m.id, p.id) in results.renders for m in models):
            continue  # nobody ran this prompt, so a slide of "Not run" cards says nothing
        chunks = [models[i:i + MODELS_PER_SLIDE] for i in range(0, len(models), MODELS_PER_SLIDE)] or [[]]
        for chunk in chunks:
            s = _slide(prs, dark)
            _title(s, f"P{n} · {p.title}", dark, size=26)
            text = p.text.strip()
            if len(text) > PROMPT_TEXT_LIMIT:
                text = text[:PROMPT_TEXT_LIMIT].rsplit(" ", 1)[0] + "…"
            if text:
                _text(s, 0.24, 0.8, 8.9, 0.65, text, BODY, 9, _fg(dark))
            _thumbnails(s, test, results, p, chunk, dark)
            dark = not dark
            count += 1
    return count


def _thumbnails(slide, test: PromptTest, results: TestResults, prompt, models, dark: bool) -> None:
    if not models:
        return
    cols = min(4, len(models))
    rows = math.ceil(len(models) / 4)
    gap, top, bottom, left = 0.2, 1.5, 5.35, 0.3
    cell_w = (RIGHT_EDGE - left - (cols - 1) * gap) / cols
    cell_h = (bottom - top - (rows - 1) * 0.12) / rows
    img_h = cell_h - 0.5
    for i, m in enumerate(models):
        x = left + (i % 4) * (cell_w + gap)
        y = top + (i // 4) * (cell_h + 0.12)
        sl = m.slots.get(prompt.id)
        r = results.renders.get((m.id, prompt.id))
        jpg = _jpg(sl.image) if sl and sl.image and r and not r.error else None
        if jpg:
            _picture(slide, jpg, x, y, cell_w, img_h)
            flags = [f"Kept {_num(r.kept)}", _stars(sl.rating)]
            if r.nothing_changed:
                flags.append("Nothing changed")
        else:
            card = _card(slide, x, y, cell_w, img_h, dark)
            _card_text(card, r.error if r and r.error else "Not run", dark, 8)
            flags = ["Not run" if not (r and r.error) else "Couldn't check"]
        _text(slide, x, y + img_h + 0.03, cell_w, 0.45, [m.label, " · ".join(flags)], MONO, 7, _fg(dark))
        slide.shapes[-1].text_frame.paragraphs[0].runs[0].font.bold = True


def _guardrails(prs, test: PromptTest) -> bool:
    guards = [p for p in test.prompts if p.kind == GUARDRAIL]
    if not guards or not test.models:
        return False
    s = _slide(prs, dark=False)
    _title(s, "Guardrails", dark=False)
    rows = [["AI tool · model"] + [f"P{prompt_number(test, g.id)} {g.title}"[:40] for g in guards]]
    for m in test.models:
        outcomes = [m.slots.get(g.id).outcome if m.slots.get(g.id) else None for g in guards]
        rows.append([m.label] + [OUTCOMES.get(o, "Not recorded") for o in outcomes])
    first = 3.0
    rest = (RIGHT_EDGE - 0.3 - first) / len(guards)
    row_h = max(0.18, min(0.3, 4.2 / len(rows)))
    _table(s, 0.3, 1.0, RIGHT_EDGE - 0.3, rows, dark=False, col_widths=[first] + [rest] * len(guards), row_h=row_h)
    _text(s, 0.3, 5.0, 8.9, 0.3, "Refused is what we want for these prompts", MONO, 8, BLACK)
    return True


def _misses(prs, test: PromptTest, results: TestResults) -> bool:
    labels = {m.id: m.label for m in test.models}
    titles = {p.id: p.title for p in test.prompts}
    candidates = [r for r in results.renders.values()
                  if r.error is None and r.kept is not None and r.overlay_png and r.model_id in labels]
    worst = sorted(candidates, key=lambda r: r.kept)[:3]
    if not worst:
        return False
    s = _slide(prs, dark=True)
    _title(s, "Biggest misses", dark=True)
    row_h = 1.45
    for i, r in enumerate(worst):
        y = 0.95 + i * (row_h + 0.05)
        overlay = _jpg(r.overlay_png)
        if overlay:
            _picture(s, overlay, 0.3, y, 2.5, row_h)
        materials = _jpg(r.material_overlay_png)
        if materials:
            _picture(s, materials, 2.95, y, 2.5, row_h)
        detail = [f"Kept {_num(r.kept)}/100"] + ([r.material_summary] if r.material_summary else [])
        _text(s, 5.65, y + 0.2, 3.6, 1.1,
              [labels[r.model_id], f"P{r.prompt_number} · {titles.get(r.prompt_id, '')}", " · ".join(detail),
               "Red: lines lost" + (" · Amber: materials changed" if materials else "")], MONO, 9, CREAM)
    return True


def _appendix(prs, test: PromptTest, results: TestResults) -> None:
    rows = []
    for m in test.models:
        for p in test.prompts:
            n = prompt_number(test, p.id)
            sl = m.slots.get(p.id)
            name = f"P{n} {p.title}"[:34]
            if p.kind == GUARDRAIL:
                outcome = OUTCOMES.get(sl.outcome, "Not recorded") if sl else "Not recorded"
                rows.append([m.label, name, "", "", "", "", "", outcome])
                continue
            r = results.renders.get((m.id, p.id))
            if r is None:
                rows.append([m.label, name, "", "", "", "", "", "Not run"])
            elif r.error:
                rows.append([m.label, name, "", "", "", "", "", "Couldn't check"])
            else:
                changed = "—" if r.changed_fraction is None else f"{100 * r.changed_fraction:.0f}%"
                rating = f"{sl.rating}/5" if sl and sl.rating else "—"
                rows.append([m.label, name, _num(r.kept), _num(r.drift), _num(r.quality), changed, rating,
                             "Nothing changed" if r.nothing_changed else "Checked"])
    header = ["AI tool · model", "Prompt", "Kept", "Drift", "Quality", "Changed", "Rating", "Status"]
    widths = [2.1, 2.0, 0.6, 0.65, 0.85, 0.9, 0.75, 1.05]
    chunks = [rows[i:i + APPENDIX_ROWS] for i in range(0, len(rows), APPENDIX_ROWS)] or [[]]
    for k, chunk in enumerate(chunks, 1):
        s = _slide(prs, dark=False)
        _title(s, "Appendix" if len(chunks) == 1 else f"Appendix ({k} of {len(chunks)})", dark=False)
        if chunk:
            _table(s, 0.3, 0.95, sum(widths), [header] + chunk, dark=False, col_widths=widths, row_h=0.28, size=8)


def _thank_you(prs) -> None:
    s = _slide(prs, dark=True)
    side = 1.065
    if LOGO.exists():
        s.shapes.add_picture(str(LOGO), Inches((W - side) / 2), Inches((H - side) / 2), Inches(side), Inches(side))
    _text(s, -0.042, 2.986, 4.647, 0.404, "Thank You", HEAD, 12, "FFFFFF", align=PP_ALIGN.CENTER)
    _text(s, 5.357, 3.036, 4.601, 0.353, COPYRIGHT, MONO, 9, "FFFFFF", align=PP_ALIGN.CENTER)


# ---------------------------------------------------------------- deck

def build_deck(test: PromptTest, results: TestResults, summaries: list[ModelSummary], when: datetime) -> bytes:
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(W), Inches(H)
    ranked = _ranked(summaries)
    has_guards = any(p.kind == GUARDRAIL for p in test.prompts) and bool(test.models)

    _cover(prs, test, when)
    _agenda(prs, ["The answer", "Leaderboard", "How we tested", "Degradation", "Prompt by prompt"]
            + (["Guardrails"] if has_guards else []) + ["Recommendation"])
    best = next((m for m in ranked if m.overall is not None), None)
    if best:
        _statement(prs, f"{best.label} came out on top", _answer_reason(best), label="The answer")
    else:
        _statement(prs, "No model could be scored yet", "Add renders and run the test", label="The answer")
    _leaderboard(prs, test, ranked)
    _how(prs, test)
    _degradation(prs, test, results)
    _prompt_slides(prs, test, results, start_dark=False)
    _guardrails(prs, test)
    _misses(prs, test, results)
    _statement(prs, test.recommendation.strip() or "Add your recommendation", label="Recommendation")
    _appendix(prs, test, results)
    _thank_you(prs)

    out = io.BytesIO()
    prs.save(out)
    return out.getvalue()
