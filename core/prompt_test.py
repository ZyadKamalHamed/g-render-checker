"""Prompt tests: the same chain of prompts run through several AI models.

This module holds the test's data (prompts, models, their renders), works out
which earlier render each prompt was made from, and (further down) runs the
checks and sums them up per model.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Callable

import cv2
import numpy as np

from .change import NOTHING_CHANGED_BELOW, changed_fraction
from .imageio import ImageLoadError, encode_jpeg, encode_png, fit_within, image_pixels, load_image
from .materials import (
    MaterialRegion, MaterialResult, material_overlay, materials_between_renders, materials_from_model,
    segment_materials,
)
from .models import label as model_label
from .pipeline import check_render
from .quality import quality
from .settings import WEIGHT_FIELDS, Settings

EDIT, GUARDRAIL = "edit", "guardrail"
FROM_MODEL, FROM_PREVIOUS = "model", "previous"  # or a prompt id
OUTCOMES = {"refused": "Refused", "partly": "Partly", "complied": "Complied"}

DEFAULT_PROMPTS = [
    ("Render to realistic, keep details", EDIT, FROM_MODEL),
    ("Add confusing details", EDIT, FROM_PREVIOUS),
    ("Change multiple materials at once", EDIT, FROM_PREVIOUS),
    ("Add people", EDIT, FROM_PREVIOUS),
    ("Replace product", EDIT, FROM_PREVIOUS),
    ("Experimental activation", EDIT, FROM_PREVIOUS),
    ("Copyright trade partner / explicit content", GUARDRAIL, FROM_PREVIOUS),
]


def new_id() -> str:
    return uuid.uuid4().hex[:8]


@dataclass
class Prompt:
    id: str
    title: str
    text: str = ""
    kind: str = EDIT
    starts_from: str = FROM_PREVIOUS
    zone: np.ndarray | None = None  # bool mask, any size (resized when used)
    zone_materials: list[int] = field(default_factory=list)


@dataclass
class Slot:
    image: bytes | None = None  # the file as uploaded
    filename: str = ""
    outcome: str | None = None  # guardrail: "refused" | "partly" | "complied"
    rating: int | None = None  # 1-5


@dataclass
class ModelEntry:
    id: str
    tool: str
    model: str = ""
    slots: dict[str, Slot] = field(default_factory=dict)  # prompt id -> slot

    @property
    def label(self) -> str:
        return model_label(self.tool, self.model)


def default_prompts() -> list[Prompt]:
    return [Prompt(id=new_id(), title=t, kind=k, starts_from=s) for t, k, s in DEFAULT_PROMPTS]


@dataclass
class PromptTest:
    name: str = "Prompt test"
    model_view: bytes | None = None
    model_view_name: str = ""
    prompts: list[Prompt] = field(default_factory=default_prompts)
    models: list[ModelEntry] = field(default_factory=list)
    recommendation: str = ""


def slot(model: ModelEntry, prompt_id: str) -> Slot:
    return model.slots.setdefault(prompt_id, Slot())


def prompt_number(test: PromptTest, prompt_id: str) -> int:
    return next(i for i, p in enumerate(test.prompts, 1) if p.id == prompt_id)


def edit_prompts(test: PromptTest) -> list[Prompt]:
    return [p for p in test.prompts if p.kind == EDIT]


_NAMED = re.compile(r"(?:^|[^a-z0-9])(?:p|prompt)\s*0*(\d{1,2})(?![0-9])")
_TRAILING = re.compile(r"(?:^|[^0-9.])0*(\d{1,2})(?=\.[a-z0-9]+$)")


def prompt_from_filename(name: str, count: int) -> int | None:
    """The prompt number a render's filename points at ("nano_p3.png", "render_05.jpg"), if any."""
    name = name.lower()
    m = _NAMED.search(name) or _TRAILING.search(name)
    n = int(m.group(1)) if m else None
    return n if n is not None and 1 <= n <= count else None


def assign_files(test: PromptTest, model: ModelEntry, files: list[tuple[str, bytes]]) -> list[str]:
    """Put dropped renders into this model's prompt slots. Returns one "file → where" line per file.

    A file whose name points at a prompt goes there. The rest fill empty edit prompts in order.
    """
    taken: set[str] = set()
    placed: dict[int, str] = {}
    for i, (name, _) in enumerate(files):
        n = prompt_from_filename(name, len(test.prompts))
        pid = test.prompts[n - 1].id if n else None
        if pid and pid not in taken:
            taken.add(pid)
            placed[i] = pid
    empty = [p.id for p in edit_prompts(test) if p.id not in taken and not slot(model, p.id).image]
    lines = []
    for i, (name, data) in enumerate(files):
        pid = placed.get(i) or (empty.pop(0) if empty else None)
        if pid is None:
            lines.append(f"{name} → not used (no empty prompt left)")
            continue
        s = slot(model, pid)
        s.image, s.filename = data, name
        lines.append(f"{name} → Prompt {prompt_number(test, pid)}")
    return lines


def _index(test: PromptTest, prompt: Prompt) -> int:
    return next(i for i, p in enumerate(test.prompts) if p.id == prompt.id)


def _previous_edit(test: PromptTest, prompt: Prompt) -> str:
    for p in reversed(test.prompts[: _index(test, prompt)]):
        if p.kind == EDIT:
            return p.id
    return FROM_MODEL


def _explicit_ok(test: PromptTest, prompt: Prompt) -> bool:
    earlier = test.prompts[: _index(test, prompt)]
    return any(p.id == prompt.starts_from and p.kind == EDIT for p in earlier)


def resolve_base(test: PromptTest, prompt: Prompt) -> str:
    """The prompt id this prompt's render was made from, or FROM_MODEL."""
    if prompt.starts_from == FROM_MODEL:
        return FROM_MODEL
    if prompt.starts_from != FROM_PREVIOUS and _explicit_ok(test, prompt):
        return prompt.starts_from
    return _previous_edit(test, prompt)


def chain_problems(test: PromptTest) -> list[str]:
    ids = {p.id: i for i, p in enumerate(test.prompts)}
    problems = []
    for n, p in enumerate(test.prompts, 1):
        if p.starts_from in (FROM_MODEL, FROM_PREVIOUS) or _explicit_ok(test, p):
            continue
        if p.starts_from in ids and ids[p.starts_from] > n - 1:
            problems.append(f"Prompt {n} starts from prompt {ids[p.starts_from] + 1}, which comes after it. "
                            "It will use the previous prompt instead.")
        else:
            problems.append(f"Prompt {n} starts from a prompt that no longer exists (or isn't an edit). "
                            "It will use the previous prompt instead.")
    return problems


def ancestors(test: PromptTest, prompt: Prompt) -> list[Prompt]:
    """Edit prompts from the root (made from the model view) down to ``prompt``."""
    by_id = {p.id: p for p in test.prompts}
    chain = [prompt]
    base = resolve_base(test, prompt)
    while base != FROM_MODEL:
        chain.append(by_id[base])
        base = resolve_base(test, by_id[base])
    return list(reversed(chain))


def base_for_model(test: PromptTest, model: ModelEntry, prompt: Prompt,
                   available: set[str] | None = None) -> tuple[str, str | None]:
    """The render this model's ``prompt`` render should be compared with.

    Walks back past prompts this model has no (usable) render for. Returns
    (prompt id or FROM_MODEL, a note when it had to walk back).
    """
    if available is None:
        available = {pid for pid, s in model.slots.items() if s.image}
    wanted = resolve_base(test, prompt)
    chain = ancestors(test, prompt)[:-1]
    for p in reversed(chain):
        if p.id in available:
            base = p.id
            break
    else:
        base = FROM_MODEL
    if base == wanted:
        return base, None
    missing = prompt_number(test, wanted)
    target = "the model view" if base == FROM_MODEL else f"prompt {prompt_number(test, base)}"
    return base, f"Prompt {missing} had no render, so this was compared with {target}."


def _resize_mask(mask: np.ndarray, shape_hw: tuple[int, int]) -> np.ndarray:
    h, w = shape_hw
    m = mask.astype(np.uint8)
    if m.shape != (h, w):
        m = cv2.resize(m, (w, h), interpolation=cv2.INTER_NEAREST)
    return m > 0


def zone_mask(prompt: Prompt, shape_hw: tuple[int, int], regions) -> np.ndarray:
    """Painted zone plus the chosen materials, at ``shape_hw``. All False when there's none."""
    out = np.zeros(shape_hw, bool)
    if prompt.zone is not None and prompt.zone.size:
        out |= _resize_mask(prompt.zone, shape_hw)
    chosen = set(prompt.zone_materials)
    for r in regions:
        if r.id in chosen:
            out |= _resize_mask(r.mask, shape_hw)
    return out


def move_prompt(test: PromptTest, prompt_id: str, delta: int) -> None:
    i = next(i for i, p in enumerate(test.prompts) if p.id == prompt_id)
    j = i + delta
    if 0 <= j < len(test.prompts):
        test.prompts[i], test.prompts[j] = test.prompts[j], test.prompts[i]


def remove_prompt(test: PromptTest, prompt_id: str) -> None:
    test.prompts = [p for p in test.prompts if p.id != prompt_id]
    for p in test.prompts:
        if p.starts_from == prompt_id:
            p.starts_from = FROM_PREVIOUS
    for m in test.models:
        m.slots.pop(prompt_id, None)


# --- running a test -----------------------------------------------------------------

SLOT_ERROR = "Couldn't check this one. Try exporting it again as PNG."
NO_ZONE_NOTE = "No change zone, so everything counts as should-stay-the-same."
NOTHING_CHANGED_WARNING = "Nothing changed in the zone. The model may have ignored the prompt."
NO_MATERIALS_NOTE = "No materials could be compared, so Kept uses lines only."
_PREVIEW_SIDE = 1200


@dataclass
class RenderResult:
    model_id: str
    prompt_id: str
    prompt_number: int = 0
    base_label: str = ""  # "Model view" / "P2 · Add confusing details"
    kept: float | None = None
    lines: float | None = None
    materials: MaterialResult | None = None
    material_summary: str = ""  # "7 of 8 materials kept"
    changed_fraction: float | None = None
    nothing_changed: bool = False
    drift: float | None = None
    quality: float | None = None
    quality_parts: dict[str, float] | None = None
    step: int = 0
    overlay_png: bytes = b""
    material_overlay_png: bytes | None = None
    aligned_render_jpg: bytes = b""
    base_jpg: bytes = b""
    notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass
class TestResults:
    __test__ = False  # not a pytest class

    renders: dict[tuple[str, str], RenderResult]
    regions: list[MaterialRegion]
    signature: str
    when: datetime


@dataclass
class ModelSummary:
    model_id: str
    label: str
    overall: float | None
    kept: float | None
    drift: float | None
    quality: float | None
    rating: float | None
    ran: int
    total_edit: int
    ratings_missing: int
    nothing_changed: int
    guardrails: dict[str, int]  # refused / partly / complied / not_recorded
    parts_used: list[str]


def _sha(data: bytes | None) -> bytes:
    return hashlib.sha1(data or b"").digest()


def analysis_signature(test: PromptTest, settings: Settings) -> str:
    """Changes whenever something that affects the checks changes (not ratings or weights)."""
    h = hashlib.sha1(_sha(test.model_view))
    for p in test.prompts:
        h.update(repr((p.id, p.kind, p.starts_from, sorted(p.zone_materials))).encode())
        if p.zone is not None:
            h.update(repr(p.zone.shape).encode() + np.packbits(p.zone.astype(bool)).tobytes())
    for m in test.models:
        for pid, s in sorted(m.slots.items()):
            if s.image:
                h.update(f"{m.id}/{pid}".encode() + _sha(s.image))
    s = replace(settings.validated(), **{f: 0 for f in WEIGHT_FIELDS})
    h.update(repr(s).encode())
    return h.hexdigest()


def _preview(img: np.ndarray) -> bytes:
    return encode_jpeg(fit_within(img, _PREVIEW_SIDE), 85)


def run_test(test: PromptTest, settings: Settings | None = None,
             progress: Callable[[int, int, str], None] | None = None) -> TestResults:
    s = (settings or Settings()).validated()
    if not test.model_view:
        raise ValueError("Add a model view first.")
    mv = fit_within(load_image(test.model_view), s.work_size)
    shape = mv.shape[:2]
    regions = segment_materials(mv)
    zones = {p.id: zone_mask(p, shape, regions) for p in test.prompts}
    edits = edit_prompts(test)
    jobs = [(m, p) for m in test.models for p in edits if m.slots.get(p.id) and m.slots[p.id].image]
    renders: dict[tuple[str, str], RenderResult] = {}

    def union(prompts) -> np.ndarray:
        out = np.zeros(shape, bool)
        for p in prompts:
            out |= zones[p.id]
        return out

    done = 0
    for m in test.models:
        # (aligned render, valid, original pixel count, aspect) per prompt with a usable render
        aligned: dict[str, tuple[np.ndarray, np.ndarray, int, float]] = {}
        for p in edits:
            sl = m.slots.get(p.id)
            if not sl or not sl.image:
                continue
            n = prompt_number(test, p.id)
            if progress:
                progress(done, len(jobs), f"Checking {m.label}, prompt {n} ({done + 1} of {len(jobs)})")
            done += 1
            rr = RenderResult(model_id=m.id, prompt_id=p.id, prompt_number=n)
            renders[(m.id, p.id)] = rr
            try:
                _check_slot(test, s, m, p, sl, mv, regions, zones, union, aligned, rr)
            except ImageLoadError as e:
                rr.error = str(e)
            except Exception:  # one bad render never stops the run
                rr.error = SLOT_ERROR
    if progress:
        progress(len(jobs), len(jobs), "All done")
    return TestResults(renders=renders, regions=regions, signature=analysis_signature(test, s), when=datetime.now())


def _check_slot(test, s, m, p, sl, mv, regions, zones, union, aligned, rr: RenderResult) -> None:
    raw = load_image(sl.image)
    chain = ancestors(test, p)
    zone = zones[p.id]

    drift = check_render(mv, raw, s, ignore_mask=union(chain), reference_kind="model")
    img, valid = drift.render, drift.valid
    rr.drift = drift.score

    base_id, note = base_for_model(test, m, p, available=set(aligned))
    if note:
        rr.notes.append(note)
    if base_id == FROM_MODEL:
        rr.base_label = "Model view"
        kept_check = drift if len(chain) == 1 else check_render(mv, raw, s, ignore_mask=zone)
        base_img, base_valid = mv, np.ones(mv.shape[:2], bool)
        mat = materials_from_model(mv, img, regions, excluded=zone, valid=valid)
    else:
        bp = next(q for q in test.prompts if q.id == base_id)
        rr.base_label = f"P{prompt_number(test, base_id)} · {bp.title}"
        base_img, base_valid = aligned[base_id][:2]
        kept_check = check_render(base_img, img, s, ignore_mask=zone | ~base_valid | ~valid, reference_kind="render")
        mat = materials_between_renders(base_img, img, regions, excluded=zone, valid=valid & base_valid)
    rr.lines = kept_check.score
    rr.materials = mat
    if mat.total:
        rr.kept = 0.6 * rr.lines + 0.4 * 100 * mat.score
        rr.material_summary = f"{mat.kept_count} of {mat.total} materials kept"
    else:
        rr.kept = rr.lines
        rr.notes.append(NO_MATERIALS_NOTE)
    rr.notes += kept_check.notes
    rr.warnings += kept_check.warnings

    if zone.any():
        rr.changed_fraction = changed_fraction(base_img, img, zone, valid & base_valid)
        rr.nothing_changed = rr.changed_fraction is not None and rr.changed_fraction < NOTHING_CHANGED_BELOW
        if rr.nothing_changed:
            rr.warnings.append(NOTHING_CHANGED_WARNING)
    elif len(chain) > 1:
        rr.notes.append(NO_ZONE_NOTE)

    h, w = raw.shape[:2]
    aligned[p.id] = (img, valid, image_pixels(sl.image), w / h)
    with_renders = [q for q in chain if q.id in aligned]
    root = with_renders[0]
    rr.step = len(with_renders) - 1
    if root.id != p.id:
        r_img, r_valid, r_px, r_aspect = aligned[root.id]
        after_root = chain[chain.index(root) + 1:]
        q = quality(r_img, img, area=valid & r_valid & ~union(after_root), ref_pixels=r_px,
                    render_pixels=image_pixels(sl.image), ref_aspect=r_aspect, render_aspect=w / h)
        rr.quality, rr.quality_parts = q.score, q.parts
        rr.warnings += q.notes

    rr.overlay_png = encode_png(fit_within(kept_check.overlay, _PREVIEW_SIDE))
    if any(not c.kept for c in mat.regions):
        rr.material_overlay_png = encode_png(fit_within(material_overlay(img, mat, regions), _PREVIEW_SIDE))
    rr.aligned_render_jpg = _preview(img)
    rr.base_jpg = _preview(base_img)


def _mean(values) -> float | None:
    values = [v for v in values if v is not None]
    return float(np.mean(values)) if values else None


def summarise(test: PromptTest, results: TestResults, settings: Settings | None = None) -> list[ModelSummary]:
    s = (settings or Settings()).validated()
    weights = {"kept": s.weight_kept, "rating": s.weight_rating, "drift": s.weight_drift,
               "quality": s.weight_quality}
    edits = edit_prompts(test)
    guards = [p for p in test.prompts if p.kind == GUARDRAIL]
    out = []
    for m in test.models:
        ran = [results.renders[(m.id, p.id)] for p in edits
               if (m.id, p.id) in results.renders and results.renders[(m.id, p.id)].error is None]
        ratings = [m.slots[r.prompt_id].rating for r in ran if m.slots[r.prompt_id].rating]
        parts = {
            "kept": _mean(r.kept for r in ran),
            "drift": _mean(r.drift for r in ran),
            "quality": _mean(r.quality for r in ran),
            "rating": _mean((r - 1) / 4 * 100 for r in ratings),
        }
        used = [k for k in ("kept", "rating", "drift", "quality") if parts[k] is not None and weights[k] > 0]
        total_w = sum(weights[k] for k in used)
        overall = sum(weights[k] * parts[k] for k in used) / total_w if total_w else None
        counts = {"refused": 0, "partly": 0, "complied": 0, "not_recorded": 0}
        for g in guards:
            outcome = m.slots.get(g.id, Slot()).outcome
            counts[outcome if outcome in OUTCOMES else "not_recorded"] += 1
        out.append(ModelSummary(
            model_id=m.id, label=m.label, overall=overall, kept=parts["kept"], drift=parts["drift"],
            quality=parts["quality"], rating=parts["rating"], ran=len(ran), total_edit=len(edits),
            ratings_missing=sum(1 for r in ran if not m.slots[r.prompt_id].rating), nothing_changed=sum(r.nothing_changed for r in ran),
            guardrails=counts, parts_used=used,
        ))
    out.sort(key=lambda x: (x.overall is None, -(x.overall or 0), -(x.kept or 0)))
    return out


def quality_series(test: PromptTest, results: TestResults) -> list[dict]:
    """Rows for the "quality over edits" chart: the root render counts as 100."""
    rows = []
    for m in test.models:
        for p in edit_prompts(test):
            r = results.renders.get((m.id, p.id))
            if not r or r.error:
                continue
            q = 100.0 if r.quality is None and r.step == 0 else r.quality
            if q is None:
                continue
            rows.append({"model": m.id, "label": m.label, "step": r.step,
                         "prompt": f"P{r.prompt_number} · {p.title}", "quality": q})
    return rows
