# Prompt Test Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add custom tool and model labels everywhere, plus a new "Prompt test" screen. The screen benchmarks AI image models across a chain of edit prompts using five measures: Kept, Changed, Drift, Quality and Rating. It also covers guardrails, and exports a `.rqtest` file and a TGS-branded `.pptx`.

**Architecture:** Pure image and data logic in new `core/` modules (`models`, `materials`, `change`, `quality`, `prompt_test`, `testfile`, `deck`), each tested on synthetic images. There is a thin Streamlit screen in `ui/prompt_test_page.py` with section modules under `ui/prompt_test/`. Every render is aligned once into the model-view frame via the existing `check_render`, and every later comparison reuses those aligned images.

**Tech Stack:** Python 3.11+, Streamlit 1.64, OpenCV, NumPy, Pillow, pandas and Altair (already installed), plus the new `python-pptx` 1.0.x. Tests use pytest.

**Spec:** `docs/superpowers/specs/2026-09-25-prompt-test-design.md`. It is the authority for all thresholds, formulas and copy. Implementers must read the matching spec section before each task.

## Global Constraints

- **No network calls and no AI models.** Everything runs locally with OpenCV and NumPy.
- **The app never writes images to disk.** Only `settings.json` (existing) and `models.json` (model names only) may be written.
- **The existing 28 tests in `tests/test_core.py` must pass unchanged.**
- **Public behaviour of `check_render` and the two existing screens stays the same**, except that tool and model labels are added.
- **User-facing copy is plain English with no jargon**, matching the existing tone (see `ui/common.py` EXPLANATIONS). Never show a traceback.
- **Working size:** `Settings.work_size` (default 1600). All prompt-test comparisons happen in the model-view frame at that size.
- **Default weights:** Kept 35, Your rating 30, Drift 20, Quality 15.
- **Default model suggestions:** `["GPT 2.5 Flare", "GPT 2.5 Sunburst", "Nano Banana Pro", "Nano Banana 2"]`.
- **Deck footer text, verbatim:** `The General Store — Copyright + Confidential 2026`.
- **Run tests with:** `.venv/bin/python -m pytest -q`.

## Review Focus

1. **A model with a render missing mid-chain** (e.g. no P3). The P4 comparison must fall back to P2 and say so. It must not crash or compare against the model view silently. *Covered by `test_missing_base_render_falls_back` (Task 7).*
2. **An `.rqtest` saved, then reopened after the prompts were reordered or removed.** Stale slot keys for deleted prompts must be dropped, not crash. *Covered by `test_load_drops_slots_for_unknown_prompts` (Task 9).*
3. **A zone painted at the 1000px display size while the analysis runs at 1600.** The masks must be resized correctly (nearest-neighbour), and a mask of a different aspect must not crash. *Covered by `test_zone_mask_resizes_any_size` (Task 7).*
4. **A render at a different aspect or resolution from its base** (common with chained edits in some tools). Quality must flag resolution loss and must not raise. *Covered by `test_quality_resolution_drop` and `test_run_test_handles_different_size_render` (Tasks 6 and 8).*
5. **A deck built with no ratings, no guardrail prompts and a single model.** It must still produce a valid file and skip the slides that need missing data. *Covered by `test_deck_minimal_test` (Task 10).*

---

## File map

| File | Status | Responsibility |
|---|---|---|
| `core/models.py` | new | Labels, known models, `models.json`, and filename guessing |
| `core/imageio.py` | modify | Add `image_pixels(data) -> int` |
| `core/pipeline.py` | modify | `CheckResult.valid`, and `reference_kind` |
| `core/materials.py` | new | Segmentation and the material checks |
| `core/change.py` | new | Normalised ΔE and the changed-in-zone fraction |
| `core/quality.py` | new | Degradation metrics |
| `core/prompt_test.py` | new | Data model, chains, zones, `run_test`, aggregation and signature |
| `core/testfile.py` | new | `.rqtest` save and load |
| `core/deck.py` | new | TGS pptx |
| `core/settings.py` | modify | Weight fields |
| `core/__init__.py` | modify | Exports |
| `assets/tgs-logo.png` | new | Copied from `~/.claude/skills/slides/G-stre-logo.png` |
| `tests/synthetic.py` | modify | `MATERIAL_BOXES`, `material_scene`, `shift_colour`, `png_bytes` |
| `tests/test_models.py`, `test_materials.py`, `test_change.py`, `test_quality.py`, `test_prompt_test.py`, `test_testfile.py`, `test_deck.py` | new | Tests |
| `ui/common.py` | modify | `tool_model_picker()` |
| `ui/check_page.py`, `ui/compare_page.py` | modify | Use the picker and labels |
| `ui/settings_panel.py` | modify | Weight sliders |
| `ui/prompt_test_page.py` | new | Screen entry |
| `ui/prompt_test/__init__.py`, `setup.py`, `renders.py`, `results.py` | new | Screen sections |
| `app.py` | modify | Third page |
| `requirements.txt` | modify | `python-pptx>=1.0,<2` |
| `README.md` | modify | Document the new screen, custom models, `.rqtest` and the privacy wording |

---

### Task 1: Custom model labels (core)

**Files:**
- Create: `core/models.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Produces:
  - `DEFAULT_MODELS: list[str]`
  - `MODELS_FILE: Path` (next to `settings.json`)
  - `label(tool: str, model: str | None) -> str`
  - `known_models(path=MODELS_FILE) -> list[str]`
  - `remember_model(name: str, path=MODELS_FILE) -> None`
  - `guess_model(filename: str, known: list[str]) -> str | None`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_models.py
from core.models import DEFAULT_MODELS, guess_model, known_models, label, remember_model


def test_label_with_and_without_model():
    assert label("Leonardo", "Nano Banana Pro") == "Leonardo · Nano Banana Pro"
    assert label("Leonardo", "") == "Leonardo"
    assert label("Leonardo", None) == "Leonardo"
    assert label("  Gendo ", "  ") == "Gendo"


def test_guess_model_prefers_longest_match():
    known = ["Nano Banana 2", "Nano Banana Pro", "GPT 2.5 Flare"]
    assert guess_model("leonardo_nano-banana-pro_p3.png", known) == "Nano Banana Pro"
    assert guess_model("NanoBanana2-p1.jpg", known) == "Nano Banana 2"
    assert guess_model("gpt2.5flare.png", known) == "GPT 2.5 Flare"
    assert guess_model("render.png", known) is None


def test_known_models_defaults_when_no_file(tmp_path):
    assert known_models(tmp_path / "models.json") == DEFAULT_MODELS


def test_remember_model_round_trip(tmp_path):
    p = tmp_path / "models.json"
    remember_model("Phoenix 1.0", p)
    remember_model("Phoenix 1.0", p)  # no duplicates
    remember_model("nano banana pro", p)  # case-insensitive duplicate of a default
    assert known_models(p) == DEFAULT_MODELS + ["Phoenix 1.0"]


def test_broken_models_file_is_ignored(tmp_path):
    p = tmp_path / "models.json"
    p.write_text("{not json")
    assert known_models(p) == DEFAULT_MODELS
    remember_model("X", tmp_path / "missing-dir" / "models.json")  # must not raise
```

- [ ] **Step 2: Run the tests to verify they fail.** Run `.venv/bin/python -m pytest tests/test_models.py -q`. Expected: ImportError.

- [ ] **Step 3: Implement `core/models.py`**

```python
"""Tool and model names: display labels, remembered model names, filename guessing.

Only model *names* are saved (in models.json next to settings.json), never images.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .settings import SETTINGS_FILE

MODELS_FILE = SETTINGS_FILE.with_name("models.json")
DEFAULT_MODELS = ["GPT 2.5 Flare", "GPT 2.5 Sunburst", "Nano Banana Pro", "Nano Banana 2"]


def label(tool: str, model: str | None) -> str:
    tool, model = (tool or "").strip(), (model or "").strip()
    return f"{tool} · {model}" if model else tool


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def known_models(path: Path = MODELS_FILE) -> list[str]:
    names = list(DEFAULT_MODELS)
    try:
        saved = json.loads(path.read_text())
    except (OSError, ValueError):
        saved = []
    seen = {_norm(n) for n in names}
    for n in saved if isinstance(saved, list) else []:
        if isinstance(n, str) and n.strip() and _norm(n) not in seen:
            names.append(n.strip())
            seen.add(_norm(n))
    return names


def remember_model(name: str, path: Path = MODELS_FILE) -> None:
    name = (name or "").strip()
    if not name or _norm(name) in {_norm(n) for n in known_models(path)}:
        return
    extra = [n for n in known_models(path) if n not in DEFAULT_MODELS] + [name]
    try:
        path.write_text(json.dumps(extra, indent=2))
    except OSError:
        pass


def guess_model(filename: str, known: list[str]) -> str | None:
    target = _norm(filename)
    hits = [n for n in known if _norm(n) and _norm(n) in target]
    return max(hits, key=lambda n: len(_norm(n))) if hits else None
```

- [ ] **Step 4: Run the tests to verify they pass.** Run `.venv/bin/python -m pytest tests/test_models.py -q`. Expected: 5 passed.

- [ ] **Step 5: Commit.** `git add core/models.py tests/test_models.py && git commit -m "Add tool/model labels and remembered model names"`

---

### Task 2: Tool + model picker on the existing screens

**Files:**
- Modify: `.gitignore` (add `models.json`)
- Modify: `ui/common.py` (add `tool_model_picker`; keep `guess_tool` and `tool_index`)
- Modify: `ui/check_page.py:50-54` (step 2 uses the picker; the report gets the label)
- Modify: `ui/compare_page.py:98-101, 111-113, 131-135` (the picker per render; group by label)

**Interfaces:**
- Consumes: `core.models.label`, `known_models`, `remember_model` and `guess_model`.
- Produces: `ui.common.tool_model_picker(key: str, filename: str | None, container=st) -> tuple[str, str, str]`, which returns `(tool, model, label)`.

- [ ] **Step 1: Implement the picker in `ui/common.py`**

```python
def tool_model_picker(key: str, filename: str | None = None, container=None) -> tuple[str, str, str]:
    """Tool (any name allowed) + optional model. Returns (tool, model, label)."""
    c = container or st
    known = known_models()
    left, right = c.columns(2)
    guessed_tool = guess_tool(filename) if filename else None
    tool = left.selectbox("AI tool", AI_TOOLS, index=tool_index(guessed_tool), key=f"{key}_tool",
                          accept_new_options=True, help="Pick one, or type a new name.") or "Other"
    guessed_model = guess_model(filename, known) if filename else None
    model = right.selectbox("Model (optional)", known, index=known.index(guessed_model) if guessed_model else None,
                            key=f"{key}_model", accept_new_options=True, placeholder="e.g. Nano Banana Pro",
                            help="Which model inside the tool. Type a new one to add it.") or ""
    if model:
        remember_model(model)
    return tool, model, label(tool, model)
```

- [ ] **Step 2: Check page.** Replace the `st.selectbox` at step 2 with `tool, model, tool_label = tool_model_picker(tool_key, rend_file.name if rend_file else None)`. Rename the step to "Which AI tool and model made this?". Pass `tool_label` to `_results`, which passes it to `build_report` and uses it in the file name.

- [ ] **Step 3: Compare page.** In `_job_card`, replace the selectbox with `_, _, tool = tool_model_picker(f"j_{jid}_tool_{f.file_id}", f.name, c2)`. Add a caption above: `c2.caption(f"**{f.name}**")`. Everything downstream already groups by the `tool` string, so the leaderboard, CSV and summary now show labels. Change the table heading "AI tool" to "AI tool · model".

- [ ] **Step 4: Verify.** Run `.venv/bin/python -m pytest -q` (all pass). Then start the preview (`preview_start {name}` from `.claude/launch.json`) and open the Check page. Upload `samples/01-model-view.png` and `samples/01-render-leonardo.jpg`. Confirm the tool guesses "Leonardo", that typing a new model is accepted, and that the report download works.

- [ ] **Step 5: Commit.** `git commit -am "Add model picker to Check and Compare screens"`

---

### Task 3: Pipeline hooks (`valid`, `reference_kind`, `image_pixels`)

**Files:**
- Modify: `core/pipeline.py` (`CheckResult` gets `valid: np.ndarray | None = None`; `check_render` gets `reference_kind: str = "model"`)
- Modify: `core/imageio.py` (add `image_pixels`)
- Modify: `tests/synthetic.py` (add helpers used by later tasks)
- Test: `tests/test_core.py` (append 3 tests)

**Interfaces:**
- Produces:
  - `check_render(original, render, settings=None, ignore_mask=None, reference_kind="model") -> CheckResult`, whose `.valid` is a bool array of the working-size shape
  - `image_pixels(data: bytes) -> int`, the width×height from the header (0 if unreadable)
  - synthetic helpers: `MATERIAL_BOXES`, `material_scene(fills: dict[int, tuple] | None = None, split: int | None = None) -> np.ndarray`, `shift_colour(img, bgr_delta) -> np.ndarray`, `png_bytes(img) -> bytes`, `material_rect(i) -> tuple[int,int,int,int]`

- [ ] **Step 1: Add the synthetic helpers**

```python
# tests/synthetic.py (append)
# Distinct flat materials for the material and prompt-test tests. (x0, y0, x1, y1, fill BGR)
MATERIAL_BOXES = [
    (60, 100, 360, 700, (40, 90, 150)),     # dark timber
    (420, 420, 820, 700, (200, 200, 195)),  # pale terrazzo
    (880, 160, 1140, 520, (150, 110, 40)),  # blue-grey metal
    (460, 110, 780, 330, (60, 160, 90)),    # green laminate
]


def material_rect(i: int) -> tuple[int, int, int, int]:
    return MATERIAL_BOXES[i][:4]


def material_scene(fills: dict | None = None, split: int | None = None, size=(W, H)) -> np.ndarray:
    """Flat-colour 'SketchUp' view. ``fills`` overrides box colours; ``split`` paints the
    right half of that box a very different colour (one material becomes two)."""
    w, h = size
    img = np.full((h, w, 3), 245, np.uint8)
    cv2.line(img, (0, 720), (w, 720), (120, 120, 120), 2)
    for i, (x0, y0, x1, y1, fill) in enumerate(MATERIAL_BOXES):
        fill = (fills or {}).get(i, fill)
        cv2.rectangle(img, (x0, y0), (x1, y1), fill, -1)
        if split == i:
            cv2.rectangle(img, ((x0 + x1) // 2, y0), (x1, y1), (230, 60, 200), -1)
        cv2.rectangle(img, (x0, y0), (x1, y1), (30, 30, 30), 2)
    for y in range(180, 700, 90):
        cv2.line(img, (60, y), (360, y), (30, 30, 30), 2)
    return img


def shift_colour(img: np.ndarray, bgr_delta) -> np.ndarray:
    return np.clip(img.astype(np.int16) + np.array(bgr_delta, np.int16), 0, 255).astype(np.uint8)


def png_bytes(img: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return buf.tobytes()
```

- [ ] **Step 2: Write the failing tests** (append to `tests/test_core.py`)

```python
def test_check_render_exposes_valid_mask(original):
    result = check_render(original, original.copy())
    assert result.valid is not None and result.valid.shape == result.original.shape[:2]
    assert result.valid.all()


def test_reference_kind_render_scores_photoreal_pair_high():
    from tests.synthetic import material_scene
    a = photoreal_like(material_scene(), seed=3)
    b = photoreal_like(material_scene(), seed=4)
    as_model = check_render(a, b, reference_kind="model")
    as_render = check_render(a, b, reference_kind="render")
    assert as_render.score >= 85
    assert as_render.score >= as_model.score - 1


def test_image_pixels_reads_header():
    from core.imageio import image_pixels
    from tests.synthetic import png_bytes
    assert image_pixels(png_bytes(np.zeros((40, 60, 3), np.uint8))) == 2400
    assert image_pixels(b"nope") == 0
```

- [ ] **Step 3: Run them to verify they fail.** Run `.venv/bin/python -m pytest tests/test_core.py -q`. Expected: 3 failures (`valid` attribute, `reference_kind` keyword, and the import).

- [ ] **Step 4: Implement**
  - In `core/pipeline.py`, add `valid: np.ndarray | None = None` as the last field of `CheckResult`. In `check_render`, add the keyword `reference_kind: str = "model"`, and pick the original's edge parameters with `params_for_render(s.render_sensitivity) if reference_kind == "render" else params_for_original(s.original_sensitivity)`. Pass `valid=valid` into `CheckResult`.
  - In `core/imageio.py`:

```python
def image_pixels(data: bytes) -> int:
    """Width x height from the file header (0 if unreadable). Cheap: doesn't decode pixels."""
    try:
        with Image.open(io.BytesIO(data)) as im:
            w, h = im.size
            return int(w) * int(h)
    except Exception:
        return 0
```

- [ ] **Step 5: Run the full suite.** Run `.venv/bin/python -m pytest -q`. Expected: all pass (the 28 old tests plus the new ones).

- [ ] **Step 6: Commit.** `git commit -am "Expose valid mask and reference kind in check_render"`

---

### Task 4: Materials (`core/materials.py`)

Read spec § "Materials" first. The constants live there.

**Files:**
- Create: `core/materials.py`
- Test: `tests/test_materials.py`

**Interfaces:**
- Produces:

```python
@dataclass
class MaterialRegion:
    id: int                   # 0 = largest
    lab: np.ndarray           # float32 (3,), mean Lab (OpenCV 8-bit Lab scaled to L 0-100, a/b -128..127)
    bgr: tuple[int, int, int] # mean colour for swatches
    mask: np.ndarray          # bool, image shape (already eroded)
    area_share: float

@dataclass
class RegionCheck:
    id: int
    kept: bool
    reason: str               # "" | "colour changed" | "texture changed" | "became two materials" | "merged with another material" | "light/dark order changed" | "not enough visible"

@dataclass
class MaterialResult:
    score: float              # 0-1 area-weighted share kept (1.0 if nothing scorable)
    kept_count: int
    total: int                # regions actually scored
    changed_mask: np.ndarray  # bool, union of failed regions
    regions: list[RegionCheck]

def to_lab(bgr) -> np.ndarray                                # float32 L 0-100, a/b centred
def segment_materials(model_view_bgr) -> list[MaterialRegion]
def match_global(a_lab, b_lab, area) -> np.ndarray           # b shifted so its mean over area == a's
def materials_between_renders(base, render, regions, excluded=None, valid=None) -> MaterialResult
def materials_from_model(model_view, render, regions, excluded=None, valid=None) -> MaterialResult
def material_overlay(render, result, regions) -> np.ndarray   # BGR, amber outlines on failed regions
def swatch(region, size=48) -> np.ndarray                     # BGR square of the region's colour
```

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_materials.py
import numpy as np
import pytest

from core.materials import (
    material_overlay, materials_between_renders, materials_from_model, segment_materials, swatch,
)
from tests.synthetic import MATERIAL_BOXES, material_rect, material_scene, photoreal_like, region_mask, shift_colour


@pytest.fixture(scope="module")
def model():
    return material_scene()


@pytest.fixture(scope="module")
def regions(model):
    return segment_materials(model)


def _region_at(regions, i):
    x0, y0, x1, y1 = material_rect(i)
    cy, cx = (y0 + y1) // 2, (x0 + x1) // 2 - 20
    hits = [r for r in regions if r.mask[cy, cx]]
    assert len(hits) == 1, f"box {i} not in exactly one region"
    return hits[0]


def test_segmentation_finds_each_box_and_skips_background(model, regions):
    ids = {_region_at(regions, i).id for i in range(len(MATERIAL_BOXES))}
    assert len(ids) == len(MATERIAL_BOXES)
    assert not any(r.mask[20, 20] for r in regions)  # near-white border background excluded
    assert all(0 < r.area_share < 1 for r in regions)
    assert swatch(regions[0]).shape == (48, 48, 3)


def test_global_warm_shift_keeps_all_materials(model, regions):
    base = photoreal_like(model, seed=1)
    warm = shift_colour(base, (-12, 0, 14))
    res = materials_between_renders(base, warm, regions)
    assert res.score > 0.95 and res.kept_count == res.total


def test_recoloured_box_is_caught(regions):
    base = photoreal_like(material_scene(), seed=1)
    changed = photoreal_like(material_scene(fills={1: (40, 40, 200)}), seed=1)
    res = materials_between_renders(base, changed, regions)
    target = _region_at(regions, 1)
    assert res.score < 0.9
    assert not next(r for r in res.regions if r.id == target.id).kept
    assert (res.changed_mask & target.mask).sum() > 0.8 * target.mask.sum()
    assert material_overlay(changed, res, regions).shape == changed.shape


def test_zone_excludes_recoloured_box(regions):
    base = photoreal_like(material_scene(), seed=1)
    changed = photoreal_like(material_scene(fills={1: (40, 40, 200)}), seed=1)
    zone = region_mask(base.shape[:2], material_rect(1), pad=15)
    res = materials_between_renders(base, changed, regions, excluded=zone)
    assert res.score >= 0.99


def test_photoreal_version_of_model_passes(model, regions):
    res = materials_from_model(model, photoreal_like(model, seed=2), regions)
    assert res.score > 0.9


def test_swapped_light_and_dark_materials_fail(model, regions):
    # timber (dark, 0) and terrazzo (pale, 1) swap colours: light/dark order flips
    swapped = material_scene(fills={0: MATERIAL_BOXES[1][4], 1: MATERIAL_BOXES[0][4]})
    res = materials_from_model(model, photoreal_like(swapped, seed=2), regions)
    failed = {r.id for r in res.regions if not r.kept}
    assert _region_at(regions, 0).id in failed and _region_at(regions, 1).id in failed


def test_merged_materials_fail(model, regions):
    merged = material_scene(fills={2: MATERIAL_BOXES[3][4]})  # metal becomes the laminate colour
    res = materials_from_model(model, photoreal_like(merged, seed=2), regions)
    failed = {r.id: r.reason for r in res.regions if not r.kept}
    assert _region_at(regions, 2).id in failed


def test_split_material_fails_consistency(model, regions):
    res = materials_from_model(model, photoreal_like(material_scene(split=1), seed=2), regions)
    r = next(r for r in res.regions if r.id == _region_at(regions, 1).id)
    assert not r.kept and r.reason == "became two materials"
```

- [ ] **Step 2: Run them to verify they fail** (ImportError).

- [ ] **Step 3: Implement `core/materials.py`** exactly per spec § Materials:
  - **Segmentation:** Lab via `cv2.cvtColor(bgr, COLOR_BGR2LAB)` converted to float with L×100/255 and a,b−128. Downsample to about 400px long side. Bin to 6-unit cubes with `np.unique(..., return_counts=True)` on `(lab // 6)`, seeds ≥0.5%, merge seeds within ΔE 8 (keep the more populous), cap at 12. Assign full-size pixels to the nearest seed by ΔE ≤12, erode each mask by `max(2, round(0.003*long_side))` px, drop regions below 0.5%, drop the background region (L>92, chroma<6, touches the border), re-id by area, and set `lab`/`bgr` means from the full-size pixels.
  - **`match_global`:** add `(mean_a − mean_b)` over `area` to b.
  - **Render→render:** use `area = valid & ~excluded` (defaults: all True / none). For each region with ≥200 px in the area: take ΔE of the means after `match_global` (≤10 passes). Texture passes when the std-of-L ratio and the mean-Sobel-magnitude ratio of L are both within [0.6, 1.67]. Record reasons in that order.
  - **Model→render:** normalise the render against the model the same way. Then:
    - consistency: `cv2.kmeans` with k=2 on up to 4000 sampled pixels of the region, fixed `cv2.KMEANS_PP_CENTERS`, 3 attempts, and `cv2.setRNGSeed(0)` for determinism
    - distinctness for pairs with model ΔE>15 (render ΔE must be >6)
    - L order for pairs with model ΔL>15 (the sign must match with 2 slack)
  - **Score:** area-weighted over scored regions. If there are none, score 1.0 and total 0.
  - **`material_overlay`:** wash out like `core.overlay.make_overlay` (0.4/0.6 grey mix then 0.55 white), draw `cv2.findContours` of each failed region in amber BGR (11,158,245) with thickness `max(2, long_side//500)`, and put a reason label via `cv2.putText` near the top-left of the region's bounding box.

- [ ] **Step 4: Run the tests.** Run `.venv/bin/python -m pytest tests/test_materials.py -q`. Expected: 8 passed. If a threshold test is borderline, fix the implementation to match the spec. Only change a spec constant if the synthetic case shows the spec value is wrong, and if so update the spec in the same commit.

- [ ] **Step 5: Commit.** `git add core/materials.py tests/test_materials.py && git commit -m "Add material segmentation and material checks"`

---

### Task 5: Changed-in-zone (`core/change.py`)

**Files:**
- Create: `core/change.py`
- Test: `tests/test_change.py`

**Interfaces:**
- Consumes: `core.materials.to_lab`, `match_global`
- Produces:
  - `NOTHING_CHANGED_BELOW = 0.15`
  - `delta_e_map(base, render, match_area) -> np.ndarray` (float32 ΔE per pixel after global match and a light blur)
  - `changed_fraction(base, render, zone, valid=None) -> float | None` (None when the zone is empty)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_change.py
import numpy as np

from core.change import NOTHING_CHANGED_BELOW, changed_fraction
from tests.synthetic import material_rect, material_scene, photoreal_like, region_mask


def test_unchanged_zone_is_near_zero():
    base = photoreal_like(material_scene(), seed=5)
    zone = region_mask(base.shape[:2], material_rect(2))
    assert changed_fraction(base, base.copy(), zone) < NOTHING_CHANGED_BELOW


def test_repainted_zone_is_mostly_changed():
    base = photoreal_like(material_scene(), seed=5)
    new = photoreal_like(material_scene(fills={2: (30, 200, 240)}), seed=5)
    zone = region_mask(base.shape[:2], material_rect(2), pad=0)
    assert changed_fraction(base, new, zone) > 0.5


def test_empty_zone_returns_none():
    base = material_scene()
    assert changed_fraction(base, base, np.zeros(base.shape[:2], bool)) is None
```

- [ ] **Step 2: Run them to verify they fail.**
- [ ] **Step 3: Implement.** `match_area = valid & ~zone` (falling back to `valid` if that has fewer than 1000 px). Compute the ΔE map as the Euclidean distance in Lab after `match_global`. Blur each Lab image with a Gaussian of sigma `1.5 * long_side/1600` before differencing. The fraction is `mean(dE[zone & valid] > 12)`.
- [ ] **Step 4: Run them to verify they pass** (3 passed).
- [ ] **Step 5: Commit.** `git add core/change.py tests/test_change.py && git commit -m "Add changed-in-zone check"`

---

### Task 6: Quality (`core/quality.py`)

Read spec § Quality first.

**Files:**
- Create: `core/quality.py`
- Test: `tests/test_quality.py`

**Interfaces:**
- Produces:

```python
@dataclass
class QualityResult:
    score: float                      # 0-100
    parts: dict[str, float]           # keys: "Sharpness", "Colour", "Artefacts", "Resolution"
    notes: list[str]

def quality(reference, render, area=None, ref_pixels=0, render_pixels=0, ref_aspect=None, render_aspect=None) -> QualityResult
```

`ref_pixels` and `render_pixels` are the original file pixel counts (0 means unknown, which gives Resolution 100). The aspect arguments are width/height from the files. The note "Output size changed between steps" is added when they differ by more than 1%.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_quality.py
import cv2
import numpy as np

from core.quality import quality
from tests.synthetic import material_scene, photoreal_like, region_mask, shift_colour


def ref():
    return photoreal_like(material_scene(), seed=7)


def test_identical_is_100():
    r = ref()
    q = quality(r, r.copy(), ref_pixels=100, render_pixels=100)
    assert q.score >= 99.5 and all(v >= 99.5 for v in q.parts.values())


def test_blur_lowers_sharpness():
    r = ref()
    q = quality(r, cv2.GaussianBlur(r, (0, 0), 2.0))
    assert q.parts["Sharpness"] < 70 and q.score < 95


def test_warm_saturated_lowers_colour():
    r = ref()
    hsv = cv2.cvtColor(shift_colour(r, (-20, 0, 25)), cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[..., 1] = np.clip(hsv[..., 1] * 1.4, 0, 255)
    warm = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)
    assert quality(r, warm).parts["Colour"] < 80


def test_heavy_jpeg_lowers_artefacts():
    r = ref()
    ok, buf = cv2.imencode(".jpg", r, [cv2.IMWRITE_JPEG_QUALITY, 8])
    q = quality(r, cv2.imdecode(buf, cv2.IMREAD_COLOR))
    assert q.parts["Artefacts"] < 85


def test_quality_resolution_drop():
    r = ref()
    q = quality(r, r.copy(), ref_pixels=4_000_000, render_pixels=1_000_000, ref_aspect=1.5, render_aspect=1.33)
    assert abs(q.parts["Resolution"] - 50) < 1
    assert any("size changed" in n for n in q.notes)


def test_changes_outside_area_are_ignored():
    r = ref()
    changed = r.copy()
    changed[100:400, 100:400] = cv2.GaussianBlur(changed[100:400, 100:400], (0, 0), 4)
    area = ~region_mask(r.shape[:2], (100, 100, 400, 400), pad=10)
    assert quality(r, changed, area=area).score >= 98
```

- [ ] **Step 2: Run them to verify they fail.**
- [ ] **Step 3: Implement per spec**, working in grey or Lab restricted to `area & ~border` (exclude a 4px border):
  - Sharpness uses `cv2.Laplacian(gray, CV_32F)` variance over the area.
  - Colour uses `to_lab` from `core.materials`.
  - Noise is `gray − GaussianBlur(gray, 0, sigma≈1.2·scale)` (≈5px kernel), taking the std over flat pixels (reference Sobel magnitude below its 40th percentile).
  - Blockiness is the mean |horizontal diff| at columns where `x % 8 == 7`, divided by the mean at other columns (plus the same for rows, averaged).
  - Clip every part to [0, 100]. Use a guard ε=1e-6 on the ratios. `score = mean(parts)`.
- [ ] **Step 4: Run them to verify they pass** (6 passed). Tune the implementation, not the tests, unless the spec formula provably can't separate the synthetic cases. In that case adjust the spec coefficient in the same commit.
- [ ] **Step 5: Commit.** `git add core/quality.py tests/test_quality.py && git commit -m "Add quality degradation metrics"`

---

### Task 7: Prompt test data model, chains and zones

**Files:**
- Create: `core/prompt_test.py` (the data and chain part)
- Test: `tests/test_prompt_test.py`

**Interfaces:**
- Consumes: `core.materials.MaterialRegion`, `core.models.label`
- Produces:

```python
EDIT, GUARDRAIL = "edit", "guardrail"
FROM_MODEL, FROM_PREVIOUS = "model", "previous"
OUTCOMES = {"refused": "Refused", "partly": "Partly", "complied": "Complied"}

@dataclass Prompt(id, title, text="", kind=EDIT, starts_from=FROM_PREVIOUS, zone: np.ndarray|None=None, zone_materials: list[int]=field(default_factory=list))
@dataclass Slot(image: bytes|None=None, filename="", outcome: str|None=None, rating: int|None=None)
@dataclass ModelEntry(id, tool, model="", slots: dict[str, Slot]=field(default_factory=dict)); property label
@dataclass PromptTest(name="Prompt test", model_view: bytes|None=None, model_view_name="", prompts=field(default_factory=default_prompts), models=field(default_factory=list), recommendation="")

def new_id() -> str
def default_prompts() -> list[Prompt]
def slot(model: ModelEntry, prompt_id: str) -> Slot                     # get-or-create
def prompt_number(test, prompt_id) -> int                                # 1-based
def edit_prompts(test) -> list[Prompt]
def resolve_base(test, prompt) -> str                                    # prompt id or FROM_MODEL (ignores which renders exist)
def chain_problems(test) -> list[str]
def ancestors(test, prompt) -> list[Prompt]                               # root..prompt (edit prompts only), by resolve_base
def base_for_model(test, model, prompt) -> tuple[str, str | None]         # (base id or FROM_MODEL, note or None), walking back past missing renders
def zone_mask(prompt, shape_hw, regions) -> np.ndarray                    # painted (resized nearest) | selected materials; all-False if none
def move_prompt(test, prompt_id, delta: int) -> None
def remove_prompt(test, prompt_id) -> None                               # also drops slots and repoints starts_from that referenced it to "previous"
```

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_prompt_test.py
import numpy as np

from core.prompt_test import (
    EDIT, FROM_MODEL, FROM_PREVIOUS, GUARDRAIL, ModelEntry, Prompt, PromptTest, Slot, ancestors,
    base_for_model, chain_problems, default_prompts, move_prompt, remove_prompt, resolve_base, zone_mask,
)


def test_default_prompts_match_spec():
    ps = default_prompts()
    assert [p.title for p in ps] == [
        "Render to realistic, keep details", "Add confusing details", "Change multiple materials at once",
        "Add people", "Replace product", "Experimental activation",
        "Copyright trade partner / explicit content",
    ]
    assert ps[0].starts_from == FROM_MODEL and all(p.starts_from == FROM_PREVIOUS for p in ps[1:])
    assert [p.kind for p in ps] == [EDIT] * 6 + [GUARDRAIL]
    assert len({p.id for p in ps}) == 7


def test_resolve_previous_chain_and_explicit():
    t = PromptTest()
    p = t.prompts
    assert resolve_base(t, p[0]) == FROM_MODEL
    assert resolve_base(t, p[1]) == p[0].id
    p[3].starts_from = p[0].id  # branch off prompt 1
    assert resolve_base(t, p[3]) == p[0].id
    assert [a.id for a in ancestors(t, p[3])] == [p[0].id, p[3].id]
    assert [a.id for a in ancestors(t, p[5])] == [p[0].id, p[3].id, p[4].id, p[5].id]


def test_previous_skips_guardrail_prompts():
    t = PromptTest()
    t.prompts.insert(2, Prompt(id="g", title="Guard", kind=GUARDRAIL))
    assert resolve_base(t, t.prompts[3]) == t.prompts[1].id


def test_broken_order_is_reported_and_treated_as_previous():
    t = PromptTest()
    p = t.prompts
    p[1].starts_from = p[4].id
    assert chain_problems(t) and "2" in chain_problems(t)[0]
    assert resolve_base(t, p[1]) == p[0].id


def test_missing_base_render_falls_back():
    t = PromptTest()
    p = t.prompts
    m = ModelEntry(id="m", tool="Leonardo", model="Nano Banana Pro")
    for i in (0, 1, 3):  # no render for prompt 3 (index 2)
        m.slots[p[i].id] = Slot(image=b"x", filename=f"p{i+1}.png")
    base, note = base_for_model(t, m, p[3])
    assert base == p[1].id and "3" in note and "2" in note
    base, note = base_for_model(t, m, p[1])
    assert base == p[0].id and note is None
    m2 = ModelEntry(id="n", tool="Leonardo", slots={p[1].id: Slot(image=b"x")})
    assert base_for_model(t, m2, p[1])[0] == FROM_MODEL


def test_zone_mask_resizes_any_size():
    p = Prompt(id="z", title="z", zone=np.zeros((500, 700), bool))
    p.zone[100:200, 100:300] = True
    m = zone_mask(p, (800, 1200), regions=[])
    assert m.shape == (800, 1200) and 0.02 < m.mean() < 0.06
    assert not zone_mask(Prompt(id="e", title="e"), (80, 120), []).any()


def test_zone_mask_includes_selected_materials():
    from core.materials import segment_materials
    from tests.synthetic import material_scene
    img = material_scene()
    regions = segment_materials(img)
    p = Prompt(id="z", title="z", zone_materials=[regions[0].id])
    m = zone_mask(p, img.shape[:2], regions)
    assert (m & regions[0].mask).sum() == regions[0].mask.sum()


def test_move_and_remove_prompt():
    t = PromptTest()
    ids = [p.id for p in t.prompts]
    move_prompt(t, ids[2], -1)
    assert [p.id for p in t.prompts][:3] == [ids[0], ids[2], ids[1]]
    move_prompt(t, ids[0], -1)  # already first: no-op
    assert t.prompts[0].id == ids[0]
    t.prompts[4].starts_from = ids[3]
    m = ModelEntry(id="m", tool="X", slots={ids[3]: Slot(image=b"1")})
    t.models.append(m)
    remove_prompt(t, ids[3])
    assert ids[3] not in [p.id for p in t.prompts]
    assert ids[3] not in m.slots
    assert all(p.starts_from != ids[3] for p in t.prompts)


def test_model_label():
    assert ModelEntry(id="a", tool="Leonardo", model="GPT 2.5 Flare").label == "Leonardo · GPT 2.5 Flare"
```

- [ ] **Step 2: Run them to verify they fail.**
- [ ] **Step 3: Implement.** The defaults use the titles above. `resolve_base`:
  - For `FROM_MODEL`, return `FROM_MODEL`.
  - For an explicit id that is an earlier *edit* prompt, return it.
  - Otherwise (`previous`, a broken order, an unknown id, or pointing at a guardrail), return the nearest earlier edit prompt, or `FROM_MODEL` if there is none.

  `chain_problems` messages use the form `"Prompt {n} starts from prompt {k}, which comes after it. It will use the previous prompt instead."` and `"Prompt {n} starts from a prompt that no longer exists…"`. The note in `base_for_model` reads `"Prompt {n} had no render, so this was compared with prompt {k}."`, or `"...with the model view."`. Guardrail prompts may still have `resolve_base` (for display), but they are never in `ancestors`.
- [ ] **Step 4: Run them to verify they pass** (10 passed).
- [ ] **Step 5: Commit.** `git add core/prompt_test.py tests/test_prompt_test.py && git commit -m "Add prompt test data model and chain resolution"`

---

### Task 8: Running a test, aggregation and weights

**Files:**
- Modify: `core/prompt_test.py` (append the run and aggregate part)
- Modify: `core/settings.py` (weights), `core/__init__.py` (exports)
- Test: `tests/test_prompt_test.py` (append)

**Interfaces:**
- Consumes: `check_render(..., reference_kind)`, `CheckResult.valid/.render/.overlay/.score`, `segment_materials`, `materials_between_renders`, `materials_from_model`, `material_overlay`, `changed_fraction`, `NOTHING_CHANGED_BELOW`, `quality`, `image_pixels`, `load_image`, `encode_png`, `encode_jpeg`, `fit_within`
- Produces:

```python
# settings.py: Settings gains weight_kept=35, weight_rating=30, weight_drift=20, weight_quality=15 (validated to 0..100 ints)

@dataclass
class RenderResult:  # fields exactly as spec § Per-render result, plus:
    prompt_number: int
    material_summary: str      # "7 of 8 materials kept" or ""
    lines: float

@dataclass
class TestResults:
    renders: dict[tuple[str, str], RenderResult]   # (model_id, prompt_id)
    regions: list[MaterialRegion]
    signature: str
    when: datetime

@dataclass
class ModelSummary:
    model_id: str; label: str
    overall: float | None; kept: float | None; drift: float | None; quality: float | None; rating: float | None
    ran: int; total_edit: int; ratings_missing: int; nothing_changed: int
    guardrails: dict[str, int]    # keys refused/partly/complied/not_recorded
    parts_used: list[str]

def analysis_signature(test, settings) -> str
def run_test(test, settings, progress=None) -> TestResults   # progress(done:int, total:int, text:str)
def summarise(test, results, settings) -> list[ModelSummary]  # sorted by overall desc, then kept desc; None last
def quality_series(test, results) -> list[dict]               # rows {model, label, step, prompt, quality} for charts
```

- [ ] **Step 1: Write the failing tests** (append)

```python
import cv2
from core import Settings
from core.prompt_test import analysis_signature, run_test, summarise
from tests.synthetic import material_rect, material_scene, photoreal_like, png_bytes, region_mask, shift_colour


def _chain_test():
    """Model view + 3 chained edit prompts. Model A is clean; model B degrades and ignores prompt 3."""
    mv = material_scene()
    t = PromptTest(model_view=png_bytes(mv), model_view_name="mv.png")
    t.prompts = [
        Prompt(id="p1", title="Realistic", starts_from=FROM_MODEL),
        Prompt(id="p2", title="Recolour laminate", zone=region_mask(mv.shape[:2], material_rect(3), pad=12)),
        Prompt(id="p3", title="Recolour metal", zone=region_mask(mv.shape[:2], material_rect(2), pad=12)),
    ]
    a1 = photoreal_like(mv, seed=11)
    a2 = photoreal_like(material_scene(fills={3: (40, 40, 200)}), seed=11)
    a3 = photoreal_like(material_scene(fills={3: (40, 40, 200), 2: (30, 200, 240)}), seed=11)
    b1 = a1.copy()
    b2 = shift_colour(cv2.GaussianBlur(a2, (0, 0), 1.2), (-8, 0, 10))
    b3 = shift_colour(cv2.GaussianBlur(b2, (0, 0), 1.2), (-8, 0, 10))  # ignored prompt 3: zone unchanged
    A = ModelEntry(id="A", tool="Leonardo", model="GPT 2.5 Flare",
                   slots={"p1": Slot(png_bytes(a1), rating=5), "p2": Slot(png_bytes(a2), rating=4), "p3": Slot(png_bytes(a3))})
    B = ModelEntry(id="B", tool="Leonardo", model="Nano Banana Pro",
                   slots={"p1": Slot(png_bytes(b1)), "p2": Slot(png_bytes(b2)), "p3": Slot(png_bytes(b3))})
    t.models = [A, B]
    return t


import pytest

@pytest.fixture(scope="module")
def chain_results():
    t = _chain_test()
    return t, run_test(t, Settings())


def test_run_test_scores_every_slot(chain_results):
    t, res = chain_results
    assert len(res.renders) == 6
    assert all(r.error is None for r in res.renders.values())
    assert res.renders[("A", "p1")].quality is None  # root is the baseline
    assert res.renders[("A", "p2")].kept > 80


def test_degrading_model_has_lower_quality(chain_results):
    t, res = chain_results
    assert res.renders[("B", "p3")].quality < res.renders[("A", "p3")].quality - 5
    assert res.renders[("B", "p3")].step == 2


def test_ignored_prompt_is_flagged(chain_results):
    t, res = chain_results
    assert res.renders[("B", "p3")].nothing_changed is True
    assert res.renders[("A", "p3")].nothing_changed is False


def test_summaries_renormalise_missing_parts(chain_results):
    t, res = chain_results
    s = {m.model_id: m for m in summarise(t, res, Settings())}
    a, b = s["A"], s["B"]
    assert a.ratings_missing == 1 and b.ratings_missing == 3 and b.rating is None
    assert "rating" not in b.parts_used
    expected_b = (35 * b.kept + 20 * b.drift + 15 * b.quality) / 70
    assert abs(b.overall - expected_b) < 0.01
    assert summarise(t, res, Settings())[0].model_id == "A"


def test_signature_ignores_ratings_but_not_zones(chain_results):
    t, _ = chain_results
    sig = analysis_signature(t, Settings())
    t.models[0].slots["p3"].rating = 2
    assert analysis_signature(t, Settings()) == sig
    t.prompts[1].zone = t.prompts[1].zone.copy()
    t.prompts[1].zone[0:5, 0:5] = True
    assert analysis_signature(t, Settings()) != sig


def test_run_test_handles_different_size_render():
    t = _chain_test()
    img = cv2.imdecode(np.frombuffer(t.models[0].slots["p2"].image, np.uint8), cv2.IMREAD_COLOR)
    t.models[0].slots["p2"].image = png_bytes(cv2.resize(img, (900, 700)))
    t.models = t.models[:1]
    res = run_test(t, Settings())
    r = res.renders[("A", "p2")]
    assert r.error is None and r.quality_parts["Resolution"] < 100


def test_bad_image_is_recorded_not_raised():
    t = _chain_test()
    t.models[0].slots["p2"].image = b"not an image"
    res = run_test(t, Settings())
    assert res.renders[("A", "p2")].error
    assert res.renders[("A", "p3")].error is None  # falls back to p1 as base
```

- [ ] **Step 2: Run them to verify they fail.**
- [ ] **Step 3: Implement `run_test`**:
  1. `mv = fit_within(load_image(test.model_view), s.work_size)` (raise `ValueError("Add a model view first.")` if missing). `regions = segment_materials(mv)`.
  2. For each model, for each **edit** prompt in order, with a slot image: decode (on `ImageLoadError`, record the error and continue).
     - Drift: `dr = check_render(mv, img, s, ignore_mask=union(zone_mask(a) for a in ancestors), reference_kind="model")`.
     - Store `aligned[(m,p)] = (dr.render, dr.valid)` and `drift = dr.score`.
  3. Then, per slot (same loop, after alignment), with `base_id, note = base_for_model(...)`, treating a base that errored as missing (walk further back). Use `zone = zone_mask(prompt, mv.shape[:2], regions)`.
     - If the base is the model view: `lines = check_render(mv, img, s, ignore_mask=zone).score`, and the materials use `materials_from_model(mv, aligned, regions, excluded=zone, valid=valid)`.
     - Otherwise: `base_img, base_valid = aligned[(m, base_id)]`, `lines = check_render(base_img, aligned_img, s, ignore_mask=zone | ~base_valid | ~valid, reference_kind="render").score`, and the materials use `materials_between_renders(base_img, aligned_img, regions, excluded=zone, valid=valid & base_valid)`.
     - `kept = 0.6*lines + 0.4*100*mat.score` if `mat.total` else `lines`.
     - `changed_fraction(base_img_or_mv_aligned, aligned_img, zone, valid)`, where the base for the model view case is `mv`.
     - Quality: root = the first ancestor that has an aligned render (for this model). If the root is this prompt, `quality=None, step=0`. Otherwise use `quality(root_img, aligned_img, area=valid & root_valid & ~union(zones of ancestors after root), ref_pixels=image_pixels(root bytes), render_pixels=image_pixels(bytes), ref_aspect, render_aspect)`, where the aspect comes from the decoded original sizes, and `step` = the index in the ancestors-with-renders list.
     - Overlays: `overlay_png = encode_png(fit_within(<the Kept check_render>.overlay, 1200))`, and `material_overlay_png` only when a region failed.
     - `aligned_render_jpg = encode_jpeg(fit_within(aligned_img, 1200), 85)`, and `base_jpg` the same for the base image.
     - `notes`/`warnings`: the Kept check's notes/warnings, plus the base note, plus `"No change zone, so everything counts as should-stay-the-same."` for a non-root prompt with no zone, plus `"Nothing changed in the zone. The model may have ignored the prompt."`, plus the quality notes, plus `"No materials could be compared, so Kept uses lines only."` when `mat.total == 0`.
     - Wrap each slot in `try/except Exception` and record `error="Couldn't check this one. Try exporting it again as PNG."` so one bad slot never stops the run.
  4. `progress(done, total, f"Checking {label}, prompt {n} ({done+1} of {total})")`.

  **`summarise`:** follow spec § Aggregation. The rating maps as `(r-1)/4*100`. Iterate the edit prompts for `total_edit`. Guardrail counts come from the guardrail prompts' `outcome`. Weights come from `s.weight_*`, renormalised over the non-None parts. `overall=None` if nothing is present.

  **`analysis_signature`:** a sha1 over the model_view bytes, `(p.id, p.kind, p.starts_from, zone.tobytes()+shape, sorted zone_materials)` in order, each slot's image sha1 (not ratings or outcomes), and `Settings` without the weight fields (`dataclasses.replace(s, weight_...=0)`).

  **`quality_series`:** for each model and each edit prompt with a result, output `step`, and `quality` = 100 for the root.

  **Settings:** add the four fields and clamp each to 0..100 in `validated()`.

- [ ] **Step 4: Run the full suite.** Expected: all pass. The prompt-test run takes a few seconds; keep the module-scoped fixture.
- [ ] **Step 5: Commit.** `git commit -am "Run prompt tests: kept, changed, drift, quality and model summaries"`

---

### Task 9: `.rqtest` save/load (`core/testfile.py`)

**Files:**
- Create: `core/testfile.py`
- Test: `tests/test_testfile.py`

**Interfaces:**
- Produces:
  - `FORMAT = "render-qa-test"`, `VERSION = 1`
  - `class TestFileError(ValueError)`
  - `save_test(test: PromptTest) -> bytes`
  - `load_test(data: bytes) -> PromptTest`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_testfile.py
import io
import json
import zipfile

import numpy as np
import pytest

from core.prompt_test import GUARDRAIL, ModelEntry, PromptTest, Slot
from core.testfile import TestFileError, load_test, save_test


def _sample():
    t = PromptTest(name="Bake-off", model_view=b"\x89PNGmv", model_view_name="view.png", recommendation="Use A")
    t.prompts[1].zone = np.zeros((50, 80), bool)
    t.prompts[1].zone[10:20, 10:30] = True
    t.prompts[2].zone_materials = [1, 3]
    t.prompts[2].text = "Swap timber for oak"
    p7 = t.prompts[6]
    t.models = [ModelEntry(id="m1", tool="Leonardo", model="Nano Banana Pro", slots={
        t.prompts[0].id: Slot(image=b"\xff\xd8jpg", filename="p1.jpg", rating=4),
        p7.id: Slot(outcome="refused"),
    })]
    return t


def test_round_trip():
    t = _sample()
    back = load_test(save_test(t))
    assert back.name == "Bake-off" and back.recommendation == "Use A"
    assert back.model_view == t.model_view and back.model_view_name == "view.png"
    assert [p.id for p in back.prompts] == [p.id for p in t.prompts]
    assert back.prompts[6].kind == GUARDRAIL
    assert np.array_equal(back.prompts[1].zone, t.prompts[1].zone)
    assert back.prompts[0].zone is None
    assert back.prompts[2].zone_materials == [1, 3] and back.prompts[2].text == "Swap timber for oak"
    m = back.models[0]
    assert m.label == "Leonardo · Nano Banana Pro"
    s1 = m.slots[t.prompts[0].id]
    assert s1.image == b"\xff\xd8jpg" and s1.filename == "p1.jpg" and s1.rating == 4
    assert m.slots[t.prompts[6].id].outcome == "refused" and m.slots[t.prompts[6].id].image is None


def _zip(files: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for k, v in files.items():
            z.writestr(k, v)
    return buf.getvalue()


def test_not_a_zip():
    with pytest.raises(TestFileError, match="Render QA test"):
        load_test(b"hello")


def test_newer_version():
    with pytest.raises(TestFileError, match="newer"):
        load_test(_zip({"test.json": json.dumps({"format": "render-qa-test", "version": 99})}))


def test_missing_image_entry():
    data = json.loads(zipfile.ZipFile(io.BytesIO(save_test(_sample()))).read("test.json"))
    with pytest.raises(TestFileError):
        load_test(_zip({"test.json": json.dumps(data)}))  # images missing


def test_load_drops_slots_for_unknown_prompts():
    t = _sample()
    t.models[0].slots["deleted-prompt"] = Slot(rating=3)
    back = load_test(save_test(t))
    assert "deleted-prompt" not in back.models[0].slots
```

- [ ] **Step 2: Run them to verify they fail.**
- [ ] **Step 3: Implement per spec § Saving.**
  - The image extension comes from the filename suffix (or is sniffed: `\x89PNG`→png, `\xff\xd8`→jpg, `RIFF`→webp, else bin).
  - Zones are saved as PNG via `cv2.imencode(".png", mask.astype(np.uint8)*255)` and loaded via `cv2.imdecode(..., IMREAD_GRAYSCALE) > 127`.
  - Guards: every read is inside `try`. `zipfile.BadZipFile` gives "This isn't a Render QA test file." A wrong `format` gives the same message. `version > VERSION` gives "This test was saved by a newer Render QA. Update Render QA to open it." A missing entry (KeyError) or bad JSON gives "This test file is damaged or incomplete." The sum of `info.file_size` must be ≤1.5e9 and there must be ≤500 entries, else "This test file is too large to open."
  - Slots whose prompt id isn't in the prompts list are dropped.
  - Use `ZIP_DEFLATED` for JSON and zones, and `ZIP_STORED` for images (already compressed).
- [ ] **Step 4: Run them to verify they pass** (5 passed).
- [ ] **Step 5: Commit.** `git add core/testfile.py tests/test_testfile.py && git commit -m "Save and open prompt tests as .rqtest files"`

---

### Task 10: TGS PowerPoint (`core/deck.py`)

Read spec § Exec report and the TGS rules in `~/.claude/skills/slides/SKILL.md` (Canvas, Fonts, Colours, Footer, Content/Statement/Agenda/Comparison slides, cards).

**Files:**
- Create: `core/deck.py`, `assets/tgs-logo.png` (copy)
- Modify: `requirements.txt` (`python-pptx>=1.0,<2`); install into `.venv`
- Test: `tests/test_deck.py`

**Interfaces:**
- Consumes: `PromptTest`, `TestResults`, `ModelSummary`, `quality_series`, `prompt_number`, `edit_prompts`, `OUTCOMES`
- Produces: `FOOTER = "The General Store — Copyright + Confidential 2026"` and `build_deck(test, results, summaries, when: datetime) -> bytes`

- [ ] **Step 1: Setup.** Run `cp ~/.claude/skills/slides/G-stre-logo.png assets/tgs-logo.png`, then `.venv/bin/pip install "python-pptx>=1.0,<2"`, then add the line to `requirements.txt`.

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_deck.py
import io
from datetime import datetime

import pytest
from pptx import Presentation

from core import Settings
from core.deck import FOOTER, build_deck
from core.prompt_test import GUARDRAIL, ModelEntry, Prompt, PromptTest, Slot, run_test, summarise
from tests.test_prompt_test import _chain_test


def _texts(slide):
    return " ".join(sh.text_frame.text for sh in slide.shapes if sh.has_text_frame)


@pytest.fixture(scope="module")
def deck_and_test():
    t = _chain_test()
    t.prompts.append(Prompt(id="g", title="Explicit content", kind=GUARDRAIL))
    t.models[0].slots["g"] = Slot(outcome="refused")
    t.recommendation = "Adopt GPT 2.5 Flare for concept renders."
    res = run_test(t, Settings())
    data = build_deck(t, res, summarise(t, res, Settings()), datetime(2026, 9, 25))
    return Presentation(io.BytesIO(data)), t


def test_deck_structure(deck_and_test):
    prs, t = deck_and_test
    # cover, agenda, answer, leaderboard, how, degradation, 3 prompt slides, guardrails, misses, recommendation, appendix
    assert len(prs.slides) == 15
    assert abs(prs.slide_width / 914400 - 10) < 0.01 and abs(prs.slide_height / 914400 - 5.625) < 0.01
    charts = [sh for s in prs.slides for sh in s.shapes if sh.has_chart]
    assert len(charts) >= 2
    assert all(FOOTER in _texts(s) for s in prs.slides)
    assert "Adopt GPT 2.5 Flare" in " ".join(_texts(s) for s in prs.slides)
    assert "Refused" in " ".join(_texts(s) for s in prs.slides)


def test_deck_minimal_test():
    t = _chain_test()
    t.models = t.models[1:]  # one model, no ratings
    for s in t.models[0].slots.values():
        s.rating = None
    res = run_test(t, Settings())
    prs = Presentation(io.BytesIO(build_deck(t, res, summarise(t, res, Settings()), datetime(2026, 9, 25))))
    texts = " ".join(_texts(s) for s in prs.slides)
    assert "Guardrails" not in [s.shapes.title.text if s.shapes.title else "" for s in prs.slides]
    assert "Add your recommendation" in texts
    assert len(prs.slides) >= 10
```

- [ ] **Step 3: Run them to verify they fail.**
- [ ] **Step 4: Implement `core/deck.py`.**
  - Start from `Presentation()` with width `Inches(10)` and height `Inches(5.625)`, using `slide_layouts[6]`.
  - Helpers:
    - `_bg(slide, dark)`: a full-slide rectangle with no line, sent to the back
    - `_text(slide, x, y, w, h, text, font, size, color, bold=False, align=LEFT)`
    - `_footer(slide, dark)`: the spec position, rotation 270
    - `_card(slide, x, y, w, h, dark)`: a rounded rectangle, `adjustments[0]=0.08`, 0.75pt `#434343` line
    - `_picture(slide, jpg_bytes, x, y, max_w, max_h)`: preserves aspect and centres in the box
  - Colours: BLACK `000000`, CREAM `F4EFE4`. Fonts: "Cal Sans", "Inconsolata", "Geom Light".
  - Slides follow spec § Exec report 1–11:
    - Leaderboard and degradation use `slide.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, …, CategoryChartData)` and `XL_CHART_TYPE.LINE_MARKERS` (categories "Step 0..N", one series per model, missing values as None).
    - Chart text is Inconsolata, colour-matched to the slide.
    - The table uses `add_table`, with Inconsolata 9pt cells.
    - Prompt slides alternate cream and black starting cream, with up to 4 thumbnails per row and 2 rows max (8 models). Beyond 8, add another slide for the same prompt.
    - The guardrails slide is skipped when there are no guardrail prompts.
    - Biggest misses uses the 3 lowest-`kept` render results that have overlays; the slide is skipped if there are none.
    - The appendix splits into chunks of 14 rows.
    - The answer line is built from the best summary, using its highest part: "Kept {k}/100 of what it was told to keep", "Scored {r}/100 on your ratings", "Stayed closest to your model ({d}/100)" or "Showed the least degradation ({q}/100)".
    - Give every slide a title shape via a text box. For the "Guardrails" check, set `slide.shapes.title` to None-safe by never using a title placeholder, so the test's title lookup returns "" for all slides. (The minimal test only asserts no crash plus the recommendation text.)
  - Save to `io.BytesIO` and return its bytes.
- [ ] **Step 5: Run them to verify they pass.** Run `.venv/bin/python -m pytest tests/test_deck.py -q` (2 passed). Also write a sample deck to the scratchpad and render it to images with `soffice --headless --convert-to pdf` if LibreOffice is available (skip if not). Look at slides 1, 4, 6 and 7 to check the layout.
- [ ] **Step 6: Commit.** `git add core/deck.py assets tests/test_deck.py requirements.txt && git commit -m "Build the exec PowerPoint in TGS style"`

---

### Task 11: Prompt test screen: setup section

**Files:**
- Create: `ui/prompt_test/__init__.py`, `ui/prompt_test/setup.py`, `ui/prompt_test_page.py`
- Modify: `app.py` (a third `st.Page(prompt_test_page.render, title="Prompt test", icon=":material/science:", url_path="prompt-test")`), `core/__init__.py` (export `PromptTest`)

**Interfaces:**
- Consumes: the `core.prompt_test` data API, `core.testfile`, `core.materials.segment_materials/swatch`, `ui.components.mask_painter`, `ui.common.read_upload/step`
- Produces:
  - `ui.prompt_test.state() -> PromptTest` (session singleton)
  - `ui.prompt_test.regions() -> list[MaterialRegion]` (cached by model view sha1 via `st.cache_data`-free memo in session state)
  - `ui.prompt_test.setup.render_header()`, `render_model_view()`, `render_prompts()`

- [ ] **Step 1: Session state and the header**
  - `state()` creates `st.session_state.ptest = PromptTest()` once, plus `ptest_nonce = 0`.
  - The header has **Open test**: `st.file_uploader("Open a saved test", type=["rqtest"], key=f"pt_open_{nonce}")`. On upload, call `load_test`. On success, replace the state, clear results and all widget keys starting with `pt_`, bump the nonce, show `st.toast("Test opened")` and call `st.rerun()`. On `TestFileError`, show `st.error(str(e))`.
  - **Download test** is `st.download_button("Download test", save_test(t), f"{safe_filename(t.name)}.rqtest", "application/zip", on_click="ignore")`, with the caption "Nothing is saved automatically. Download the test to keep it."
  - Test name: `st.text_input` bound via `on_change` to `t.name`.
- [ ] **Step 2: Model view.**
  - Step 1 heading "Add your model view". An uploader keyed with the nonce. When a new file arrives, store `t.model_view = file.getvalue()` and `t.model_view_name`, then bump the nonce so the uploader empties.
  - Show a thumbnail of the stored bytes (decode via `read_upload`-style `_decode`, i.e. `load_image` cached), with a "Replace" hint.
- [ ] **Step 3: Prompts.**
  - Step 2 heading "Your prompts". Show `chain_problems` as `st.warning`.
  - For each prompt, show `st.expander(f"{n}. {p.title}" + suffix, expanded=False)`. The suffix is `"  ·  Guardrail"`, or `"  ·  from prompt {k}"` when `resolve_base` isn't the immediately previous edit prompt (or "from the model view" for non-first).
  - Inside the expander:
    - `st.text_input("Headline", key=f"pt_title_{p.id}")` and `st.text_area("Full prompt", key=f"pt_text_{p.id}", placeholder="Paste the exact prompt you used")`
    - `st.radio("Type", ["Edit", "Guardrail"], horizontal=True)`
    - for edit prompts, `st.selectbox("Starts from", options)`, where the options are `["previous", "model"] + earlier edit prompt ids`, with a format_func showing "Previous prompt", "The model view" and "Prompt {k}: {title}"
    - a row of `st.button("Move up")`, `st.button("Move down")` and `st.button("Remove", type="tertiary")`, each using `on_click` callbacks that call `move_prompt`/`remove_prompt`
  - Widget values are written back to the dataclass in `on_change` callbacks. The widget keys are initialised from the dataclass only when absent, the same pattern as `ui/settings_panel.py`.
  - The change zone (edit prompts only, and only once a model view exists) is `st.toggle("Change zone", key=f"pt_zone_on_{p.id}", value=p.zone is not None or bool(p.zone_materials))`. When on:
    - caption "Paint where you asked the AI to change things. Everything else is judged on staying the same."
    - `mask = mask_painter(mv_img, key=f"pt_zone_{p.id}")`, then `p.zone = mask`
    - to restore strokes after opening a file, if `p.zone` exists but the painter has no saved strokes, show a small preview of the stored zone overlaid on the view with the caption "Saved zone. Paint to replace it."
    - material chips: `st.image([swatch(r) for r in regions])` captioned "M1".."Mn", then `st.multiselect("Also include these materials", [r.id for r in regions], format_func=lambda i: f"M{i+1}", key=f"pt_mat_{p.id}")`, then `p.zone_materials = …`
    - when the toggle is off: `p.zone=None; p.zone_materials=[]`
  - A prompt with no zone that isn't first gets the caption "No change zone, so everything counts as should-stay-the-same."
  - Below the list: `st.button("Add prompt", icon=":material/add:")`, which appends `Prompt(id=new_id(), title=f"Prompt {len+1}")`.
- [ ] **Step 4: Page entry.** `ui/prompt_test_page.render()` shows the title "Prompt test" and the lede "Run the same prompts through several AI models and see which keeps your design, changes what you asked, and holds its quality.", then calls the setup functions (the renders and results sections follow in Tasks 12–13 and are stubbed as no-ops here).
- [ ] **Step 5: Verify in the browser.**
  - Run `preview_start`, open `/prompt-test`, and upload `samples/01-model-view.png`.
  - Expand prompt 6, turn on the zone, paint, pick a material, reorder, remove and add a prompt.
  - Download the test, reload the page, open the file, and confirm the prompts, zone preview and materials came back.
  - Check `read_console_messages` and `preview_logs` for errors.
- [ ] **Step 6: Commit.** `git add ui app.py core/__init__.py && git commit -m "Prompt test screen: model view, prompts and change zones"`

---

### Task 12: Prompt test screen: models, renders and ratings

**Files:**
- Create: `ui/prompt_test/renders.py`
- Modify: `ui/prompt_test_page.py` (call it)
- Modify: `core/prompt_test.py` (add `prompt_from_filename`)
- Test: `tests/test_prompt_test.py` (append)

**Interfaces:**
- Consumes: `ui.common.tool_model_picker`, and the `core.prompt_test` data API
- Produces:
  - `render_models()`
  - `assign_files(test, model, files: list[tuple[str, bytes]]) -> list[str]` (pure, in `core/prompt_test.py`; returns "file → Prompt n" lines)

- [ ] **Step 1: Test the filename-to-prompt assignment** (a pure function, placed in `core/prompt_test.py` as `prompt_from_filename(name, count) -> int | None` and used by `assign_files`)

```python
from core.prompt_test import prompt_from_filename


@pytest.mark.parametrize("name,expected", [
    ("nano_p3.png", 3), ("Prompt 4 - flare.jpg", 4), ("render_05.webp", 5), ("gpt-2.png", 2),
    ("flare.png", None), ("p12.png", None),
])
def test_prompt_from_filename(name, expected):
    assert prompt_from_filename(name, 7) == expected
```

  Rules: first try `(?:^|[^a-z0-9])(?:p|prompt)\s*0*(\d{1,2})(?![0-9])`, then fall back to the last standalone number `(?:^|[^0-9.])0*(\d{1,2})(?=\.[a-z]+$)`. The result is valid only if it's in 1..count. The trailing number before the extension is what "render_05" and "gpt-2" match. Make sure "2.5" in "gpt-2.5-flare_p3" resolves to 3 via the first rule.

- [ ] **Step 2: Implement and pass.**
- [ ] **Step 3: Build the section.**
  - Step 3 heading "Models and renders".
  - Inside `st.form("pt_add_model", clear_on_submit=True, border=True)`: `tool_model_picker("pt_new")` (a form-compatible variant: the picker has no side effects inside forms except `remember_model` on submit) and `st.form_submit_button("Add model")`. On submit, append `ModelEntry(id=new_id(), tool, model)`, unless an entry with the same label exists (then show an info message).
  - Then `tabs = st.tabs([m.label for m in t.models])`. In each tab:
    - "Remove this model" (tertiary)
    - `st.file_uploader("Drop all this model's renders at once", accept_multiple_files=True, key=f"pt_bulk_{m.id}_{nonce}")`. When files arrive, run `assign_files`, show the summary lines as `st.caption`, and bump the nonce.
    - For each prompt, a bordered container with columns `[0.6, 2.2, 1.6]`: the number and title | the image area | the rating/outcome.
      - Edit prompts: if the slot has an image, show the thumbnail (≤300px) and filename, plus a "Remove" tertiary button. Otherwise show an uploader keyed `pt_up_{m.id}_{p.id}_{nonce}` that stores its bytes on arrival.
      - Rating: `st.feedback("stars", key=f"pt_rate_{m.id}_{p.id}", on_change=…)`, which gives a 0..4 index (store `idx+1`). Initialise the key from `slot.rating-1` when absent.
      - Guardrail prompts: `st.radio("Outcome", ["refused","partly","complied", None], format_func=OUTCOMES.get or "Not recorded", horizontal=True)` plus an optional image uploader.
  - `assign_files` fills the detected prompt slots, then assigns anything left over to empty edit slots in order. It returns lines like `"nano_p3.png → Prompt 3"` or `"extra.png → not used (no empty prompt left)"`.
- [ ] **Step 4: Verify in the browser.** Add two models ("Leonardo" · "Nano Banana Pro" and "Leonardo" · "GPT 2.5 Flare"). Bulk-drop `samples/01-render-*.jpg` and confirm the assignment captions. Rate some slots, set a guardrail outcome, then download and reopen the test and confirm the ratings and outcome persist.
- [ ] **Step 5: Commit.** `git commit -am "Prompt test screen: models, renders, ratings and guardrail outcomes"`

---

### Task 13: Prompt test screen: run, results and downloads, plus weight settings

**Files:**
- Create: `ui/prompt_test/results.py`
- Modify: `ui/prompt_test_page.py`, `ui/settings_panel.py` (four weight sliders in a "Prompt test weights" sub-section, keys `adv_w_kept`, `adv_w_rating`, `adv_w_drift`, `adv_w_quality`, added to `_FIELDS`)

**Interfaces:**
- Consumes: `run_test`, `summarise`, `quality_series`, `analysis_signature`, `build_deck`, `current_settings`
- Produces: `render_run_and_results()`

- [ ] **Step 1: Recommendation, and the run.**
  - Step 4 is `st.text_area("Your recommendation (used in the exec report)", key="pt_reco")`, synced to `t.recommendation`.
  - The big button "Run all checks ({N} renders)" is disabled when there's no model view or no render. Its caption explains why.
  - On click, use `st.progress` with the `run_test` progress callback, wrapped in `try/except Exception` with the friendly `st.error`. Store `st.session_state.ptest_results`.
- [ ] **Step 2: Results.**
  - If `results.signature != analysis_signature(t, settings)`, show `st.info("Something changed since the last run. Press **Run all checks** to update.")`.
  - The headline markdown is "**{best.label}** came out on top with **{overall:.0f}/100**", plus caveats: "{label}: {ran} of {total} prompts", "{n} ratings missing".
  - Leaderboard: an Altair bar (reuse the compare page style and LEVEL_COLORS via `score_level`), plus `st.dataframe` with ProgressColumns for Overall/Kept/Your rating/Drift/Quality, and text columns Guardrails ("Refused 1 · Complied 0"), Prompts run and Notes.
  - "Quality over edits": `alt.Chart(pd.DataFrame(quality_series(...))).mark_line(point=True)` with x=`step:O` ("Edit number"), y=`quality:Q` in the domain [0, 105], and color=`label:N`, followed by the caption "Measured on the parts no prompt has touched yet. A flat line means no degradation."
  - Grid: for each edit prompt, the subheader "{n}. {title}", then `st.columns(min(4, len(models)))`, wrapping rows. Each cell shows `st.image(overlay_png)`, the markdown "**{label}**: Kept {kept:.0f} · Drift {drift:.0f} · Quality {q or '—'}", the stars as "★"*rating, `⚠` captions for warnings, and a `st.button("Details", key=...)` that sets `st.session_state.pt_detail=(m,p)` and calls `_detail_dialog()`. The dialog is decorated `@st.dialog("Details", width="large")` and shows the overlay + legend, the material overlay (if any) with the material summary, `fader(base, render)` (decode the stored JPEGs), a small table of all scores and quality parts, and the notes and warnings.
  - "Not run" cells show `st.caption("Not run")`. Error cells show `st.warning(error)`.
  - Downloads:
    - `st.download_button("Download exec report (PowerPoint)", build_deck(...), f"{safe_filename(t.name)}-report-{date}.pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation", type="primary", on_click="ignore")`. Cache the deck bytes in session keyed by `(signature, ratings/outcomes/recommendation/name hash, weights)` so it isn't rebuilt on every rerun.
    - "Download results (CSV)" with one row per model × prompt: Model, Prompt, Kept, Lines, Materials kept, Changed %, Drift, Quality, the quality parts, Rating, Outcome, Warnings. Encode as `utf-8-sig`.
    - A reminder caption: "Download the test too if you might want to come back to it."
- [ ] **Step 3: Weight sliders.** In `settings_panel`, below the existing columns, add `st.markdown("**Prompt test weights**")` and 4 sliders (0–100). Add them to `_FIELDS` so `current_settings()` includes them. Add the caption "They're balanced automatically, so only their size relative to each other matters."
- [ ] **Step 4: Verify in the browser, end to end.**
  - Build a test with `samples/01-model-view.png` as the model view. Model A uses `01-render-leonardo.jpg` for P1 and `01-render-gendo.jpg` for P2. Model B uses `01-render-veras.webp` for P1 and `test_images/…png`, if it's the same view, or a blurred copy made in the scratchpad for P2. Paint a zone on P2.
  - Run it. Check the leaderboard, the line chart, the grid and the dialog with the fader.
  - Change a rating: the overall updates without the stale banner. Change a zone: the stale banner appears.
  - Download the pptx and CSV, and confirm the pptx opens with `python-pptx`.
  - Check the console and logs. Take a screenshot for the user.
- [ ] **Step 5: Run the full test suite, then commit.** `git commit -am "Prompt test screen: run, leaderboard, degradation chart, grid, exec report"`

---

### Task 14: README and final polish

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Document the changes.**
  - A new "### Run a prompt test" section for designers covering: the model view, prompts (headline/full text, edit vs guardrail, starts from, reorder), change zones (paint + materials), models and renders (bulk drop naming tip: put `p1`…`p7` in file names), ratings, running, what each score means (Kept, Changed flag, Drift, Quality, Your rating, Guardrails, Overall weights), downloading the test (`.rqtest`) and the exec PowerPoint.
  - Update "Check a render" step 3 and "Compare AI tools" to mention the model picker.
  - Privacy: add "Prompt tests are only kept if you download them as a `.rqtest` file. Model names you type are remembered in `models.json` (names only)." The "Updating" section should keep `models.json` too.
  - Fine-tuning: add the "Prompt test weights".
- [ ] **Step 2: Final checks.** Run `.venv/bin/python -m pytest -q` (all green) and `git status` (clean apart from the README).
- [ ] **Step 3: Commit.** `git commit -am "Document prompt tests and custom models"`
- [ ] **Step 4: Whole-branch review.** Dispatch one fresh reviewer subagent over `git diff dc07619..HEAD` against the spec. Fix the confirmed findings and commit.
