# Prompt Test: design spec

**Date:** 2026-09-25
**Status:** Approved in conversation (user waived written review)

## Goal

Render QA can already score how well one AI render keeps the geometry of a model view, and rank tools across jobs. This adds a way to benchmark AI image models across a **scripted series of edit prompts** and present the result to execs.

The user plans to run this once as a bake-off. The inputs are one model view, their 7 prompts, and several Leonardo models (GPT 2.5 Flare, GPT 2.5 Sunburst, Nano Banana Pro, Nano Banana 2). The output is a leaderboard and a TGS-branded PowerPoint.

The questions it has to answer:

1. **Kept:** did the model keep what it was told not to change (geometry and materials), outside the area it was told to change?
2. **Changed:** did it change anything at all where it was told to?
3. **Drift:** how far has the result moved from the original design?
4. **Quality:** does image quality degrade over repeated edits? (The claim to test is that Nano Banana degrades and GPT 2.5 does not.)
5. **Your rating:** a human 1–5 judgement of how well the edit was done.
6. **Guardrails:** did the model refuse copyright or explicit prompts?

## Decisions made with the user

| Topic | Decision |
|---|---|
| Structure | New third screen, **"Prompt test"**. The existing two screens keep working as they do now. |
| Custom models | Tool + free-text **Model** on every screen. Labels read "Leonardo · Nano Banana Pro". |
| Edit baseline | Per-prompt **"Starts from"**: *Previous prompt* (chain, default), *Prompt 1*, any earlier prompt, or *Model view*. |
| Change zones | Painted once per prompt on the model view. Materials can be added to a zone by picking detected material swatches. |
| Changed judgement | **Both** an automatic "nothing changed in the zone" flag (a warning, never a penalty) **and** the user's 1–5 stars. |
| Saving | **Export/import** a single `.rqtest` file. The app never writes images to disk. |
| Overall score | Weighted: **Kept 35, Your rating 30, Drift 20, Quality 15**. Adjustable in Advanced settings. Missing parts are left out and the weights re-normalised. |
| Prompts | Default list of the user's 7. Editable (title, full text), can be added, removed and reordered. Collapsed headline, expand to see the full prompt. |
| Guardrail prompt | Prompt 7 is kind *Guardrail*: outcome Refused / Partly / Complied, and no image is required. Shown as its own column and not blended into the overall score. |
| Report | Editable **.pptx** in the TGS slide style, with native PowerPoint charts. Generated locally. |
| Jev / TypeSafe | Not used. It only accepts text, and it would break the offline promise. |

## Default prompts

| # | Title | Kind | Starts from |
|---|---|---|---|
| 1 | Render to realistic, keep details | Edit | Model view |
| 2 | Add confusing details | Edit | Previous |
| 3 | Change multiple materials at once | Edit | Previous |
| 4 | Add people | Edit | Previous |
| 5 | Replace product | Edit | Previous |
| 6 | Experimental activation | Edit | Previous |
| 7 | Copyright trade partner / explicit content | Guardrail | Previous |

Full prompt text defaults to an empty string with the placeholder "Paste the exact prompt you used".

## Architecture

The app keeps its split: `core/` holds pure image logic and data with no Streamlit, and `ui/` holds the Streamlit screens. New units:

| File | Responsibility |
|---|---|
| `core/models.py` | Tool and model labels, the remembered list of model names (`models.json`), and guessing the model from a filename. |
| `core/materials.py` | Splitting a model view into flat-colour material regions, and the two material checks (model→render and render→render). |
| `core/change.py` | Normalised colour difference between two aligned images, and the "changed inside zone" fraction. |
| `core/quality.py` | Degradation metrics of a render against its reference (sharpness, colour creep, artefacts, resolution). |
| `core/prompt_test.py` | Data model (`PromptTest`, `Prompt`, `ModelEntry`, `Slot`), chain resolution, running all checks, per-model aggregation. |
| `core/testfile.py` | Saving and loading `.rqtest` zip files (versioned). |
| `core/deck.py` | Building the TGS PowerPoint from test results. |
| `assets/tgs-logo.png` | The TGS logo, copied from the slides kit. |
| `ui/prompt_test_page.py` | Screen entry point and layout. |
| `ui/prompt_test/` | Sections of the screen: `setup.py` (test name, model view, prompts), `renders.py` (models, slots, ratings), `results.py` (leaderboard, charts, grid, downloads). |

Changed files: `core/pipeline.py` (reference kind, reusable alignment), `core/settings.py` (weights), `core/__init__.py`, `ui/common.py` (tool/model picker), `ui/check_page.py`, `ui/compare_page.py`, `ui/settings_panel.py` (weights), `app.py` (third page), `requirements.txt` (`python-pptx`), `README.md`.

## Data model (`core/prompt_test.py`)

```python
EDIT, GUARDRAIL = "edit", "guardrail"
FROM_MODEL, FROM_PREVIOUS = "model", "previous"  # or a prompt id

@dataclass
class Prompt:
    id: str                 # short uuid
    title: str
    text: str = ""
    kind: str = EDIT
    starts_from: str = FROM_PREVIOUS
    zone: np.ndarray | None = None      # bool mask, any size (resized when used)
    zone_materials: list[int] = []      # material ids added to the zone

@dataclass
class Slot:
    image: bytes | None = None          # original file bytes, as uploaded
    filename: str = ""
    outcome: str | None = None          # guardrail: "refused" | "partly" | "complied"
    rating: int | None = None           # 1-5

@dataclass
class ModelEntry:
    id: str
    tool: str
    model: str = ""
    slots: dict[str, Slot] = {}         # prompt id -> slot
    label -> "Tool · Model" or "Tool"

@dataclass
class PromptTest:
    name: str = "Prompt test"
    model_view: bytes | None = None
    model_view_name: str = ""
    prompts: list[Prompt] = default_prompts()
    models: list[ModelEntry] = []
    recommendation: str = ""
```

**Chain resolution:** `resolve_base(test, prompt) -> prompt id | FROM_MODEL`.
- `previous` means the nearest earlier *edit* prompt. The first edit prompt resolves to the model view.
- An explicit id must refer to an **earlier** prompt, otherwise it is a *broken order*. `chain_problems(test)` returns user-facing warnings for the UI.
- For each model, if the base prompt has no render in that model's slot, walk further back to the most recent ancestor that has one (or the model view). The result carries a note: "P3 had no render, so compared with P2".
- `ancestors(prompt)` is the chain from the root to this prompt. It is used for zone unions (Drift) and for Quality's reference (the root render: the first render in the ancestry, which is the one made from the model view).

## Scoring

All images are analysed at the existing working size (`Settings.work_size`, 1600px long side). The model view sets the frame, and every render is fitted and aligned to it.

### Alignment reuse (`core/pipeline.py`)

- `CheckResult` gains `valid: np.ndarray | None` (the pixels that came from the render after fitting and alignment).
- `check_render` gains `reference_kind: "model" | "render" = "model"`. With `"render"`, the reference's lines are detected with the **render** edge parameters, since both images are photoreal.
- Every render is brought into the **model-view frame** once, via its Drift check `check_render(model_view, render, …)`, which returns the aligned render and `valid`. All later comparisons (Kept against a base render, materials, Changed, Quality) use these aligned images, so they share one frame and size.
- The existing 28 tests must pass unchanged.

### Kept (0–100)

For an edit prompt whose base is `B` (the model view or a render):

- **Lines:** `check_render(B, render, ignore_mask=zone | ~B.valid, reference_kind=kind(B))`, with both images in the model-view frame. The line score is `100 × F1`.
- **Materials:**
  - If B is the model view: `materials_from_model(model_view, render_aligned, regions, excluded=zone)`.
  - If B is a render: `materials_between_renders(base_aligned, render_aligned, regions, excluded=zone)`.
  - The result is `MaterialResult(score 0–1, kept_count, total, changed_mask, per_region list)`.
- **Kept** = `0.6 × lines + 0.4 × 100 × materials.score`. If there are no scorable material regions, Kept = lines.

### Materials (`core/materials.py`)

**Segmentation, done once per test from the model view:**
1. Convert to Lab at working size. Downsample to about 400px for clustering.
2. Quantise the colours: bin Lab values into 6-unit cubes and take the bins holding at least 0.5% of pixels as seeds, most populous first. Merge seeds within ΔE 8 of each other, keeping at most 12.
3. Assign every full-size pixel to its nearest seed if it's within ΔE 12. Anything else, such as lines and anti-aliasing, is unassigned (−1).
4. Erode each region by `max(2, 0.003 × long side)` px so the lines around it don't count as material. Drop regions under 0.5% of the image after erosion.
5. The largest region that is near-white (L > 92, chroma < 6) **and** touches the image border counts as background (a SketchUp sky or void) and is excluded.
6. Output a list of `MaterialRegion(id, lab_mean, bgr, mask, area_share)`. The ids are stable (ordered by area), and each region gets a swatch image for the UI.

**Global normalisation:** before comparing, shift image B's Lab so its mean over the shared scored area matches image A's. This stops a global warm or bright shift being counted against every material. Colour creep is caught by Quality instead.

**Render → render (base render vs new render):** for each region, excluding zone and invalid pixels, with at least 200 px remaining:
- Colour check: ΔE between the region means is 10 or less.
- Texture check: the ratio of the std of L is between 0.6 and 1.67, **and** the ratio of mean gradient magnitude is in the same range.
- A region is *kept* if both checks pass.
- Score = area-weighted share of kept regions.

**Model view → render (prompt 1):** for each region:
- Consistency: in the render, run 2-cluster k-means on the region's Lab values. If the minor cluster is 25% or more of the region and the two cluster centres are more than ΔE 25 apart, the region fails ("became two materials").
- Distinctness: for every pair of regions whose model colours differ by more than ΔE 15, the render means (after normalisation) must differ by more than ΔE 6. Both regions in a failing pair fail ("merged").
- Lightness order: for pairs whose model L values differ by more than 15, the render must keep the same L order, with 2 units of slack. Both regions fail if not.
- Score = area-weighted share of regions that passed everything.

The **material overlay** is the render, washed out the same way as the existing overlay, with failed regions outlined in amber (#F59E0B) and a small label. It is shown in the cell detail and on the "biggest misses" slide.

### Changed flag (`core/change.py`)

- Only for edit prompts that have a zone. The zone is the painted mask plus the masks of `zone_materials`, resized to the working size.
- `changed_fraction` = share of zone pixels (valid only) where the normalised Lab ΔE between the base (aligned) and the render (aligned) is above 12, after a light blur (sigma about 1.5 px at 1600).
- `nothing_changed = changed_fraction < 0.15`. It shows the warning "Nothing changed in the zone. The model may have ignored the prompt." It is **not** a penalty.
- With no zone, the value is `None` and the UI nudges: "No change zone, so everything counts as should-stay-the-same."

### Drift (0–100)

`check_render(model_view, render, ignore_mask=union(zones of ancestors and this prompt), reference_kind="model")`, giving `100 × F1`. For the root prompt, Drift equals its Kept line score.

### Quality (0–100, `core/quality.py`)

- Reference = the model's **root render** in this prompt's ancestry. The root itself has no Quality score (it's the 100 baseline) and isn't averaged.
- Compare area = valid pixels outside the union of the zones of every prompt **after** the root in the ancestry, including this one. Both images are already in the model-view frame.
- Sub-scores, each clipped to 0–100:
  - **Sharpness:** ratio of the variance of the Laplacian (grey, in the area) of render to reference. `100 × min(1, ratio)`.
  - **Colour creep:** without normalisation, find the mean ΔE between the area means, the chroma ratio and the L-std (contrast) ratio. `100 − 4·ΔE − 100·|chroma−1| − 100·|contrast−1|`.
  - **Artefacts:**
    - Noise: std of the high-pass residual (image minus a 5px Gaussian) in flat areas, meaning pixels where the reference's gradient is below its 40th percentile.
    - Blockiness: mean gradient on the 8-px grid lines divided by the mean gradient off the grid.
    - Take the render/reference ratio of each. `100 − 50·max(0, noise−1) − 50·max(0, block−1)`.
  - **Resolution:** original pixel counts from the file headers. `100 × min(1, px_render / px_reference) ^ 0.5`.
- **Quality** = mean of the four. The four sub-scores and the chain **step** number (depth after the root) are stored for the chart.
- If the aspect ratio differs from the reference by more than 1%, add the warning "Output size changed between steps".

### Per-render result

```python
@dataclass
class RenderResult:
    model_id: str; prompt_id: str
    base_label: str               # "Model view" / "P2 · Add confusing details"
    kept: float; lines: float; materials: MaterialResult | None
    changed_fraction: float | None; nothing_changed: bool
    drift: float
    quality: float | None; quality_parts: dict[str, float] | None; step: int
    overlay_png: bytes; material_overlay_png: bytes | None
    aligned_render_jpg: bytes; base_jpg: bytes   # for the fader and the deck
    notes: list[str]; warnings: list[str]
    error: str | None
```

`run_test(test, settings, progress_cb) -> TestResults` runs each (model, edit prompt) slot that has an image. A failure in one slot records `error` and carries on.

### Aggregation (per model)

- `kept`, `drift` = mean over the edit prompts that were run.
- `quality` = mean over the non-root edit prompts that have Quality.
- `rating` = mean over rated edit prompts, mapped to 0–100 as `(r − 1) / 4 × 100`.
- `overall` = the weighted sum of the parts present, with weights re-normalised over those parts.
- Also store: `ran`/`total_edit` ("5 of 6 prompts"), `ratings_missing`, `nothing_changed_count`, and `guardrails` (counts of refused/partly/complied/not recorded across guardrail prompts).
- The leaderboard sorts by overall, descending. Ties are broken by Kept.

Weights live in `Settings`: `weight_kept=35, weight_rating=30, weight_drift=20, weight_quality=15`. They are 0–100 integers, normalised at use, and the Advanced settings panel gains four sliders for them.

## Custom models (`core/models.py`, all screens)

- `AI_TOOLS` stays as the suggestion list. Every tool picker uses `st.selectbox(accept_new_options=True)`, so any tool name can be typed in. "Other" stays.
- There's a new **Model** picker (optional) next to it, with `accept_new_options=True`. Its options come from `known_models()`, which is the default list `["GPT 2.5 Flare", "GPT 2.5 Sunburst", "Nano Banana Pro", "Nano Banana 2"]` plus names saved in `models.json` next to `settings.json` (a list of strings).
- `remember_model(name)` appends a new name to `models.json`. Write failures are ignored silently. The file holds only model names, never images.
- `guess_model(filename, known)`: normalise both to lowercase alphanumerics and pick the **longest** known name contained in the filename, so "nano banana pro" wins over "nano banana".
- `label(tool, model)` returns `"Tool · Model"`, or just `"Tool"` if there's no model.
- The Check page report and the Compare leaderboard/CSV/summary use the label. Compare groups by label.

## Saving (`core/testfile.py`)

A `.rqtest` file is a zip:

```
test.json            {"format": "render-qa-test", "version": 1, name, recommendation,
                      model_view: {"file": "...", "name": "..."},
                      prompts: [{id,title,text,kind,starts_from,zone_file|null,zone_materials}],
                      models: [{id,tool,model,slots:{pid:{file|null,filename,outcome,rating}}}]}
images/model_view.<ext>
images/<model_id>/<prompt_id>.<ext>
zones/<prompt_id>.png          (1-bit mask)
```

- The original file bytes are stored as uploaded, so nothing is re-encoded. Results aren't stored: they are recomputed after opening, which is quick and always matches the current version.
- `load_test(bytes)` raises `TestFileError(message)` with a friendly message for a wrong format, a newer version ("This test was saved by a newer Render QA"), or a missing or corrupt entry. Unknown keys are ignored. `version` is checked so future versions can migrate.
- There's a zip-bomb guard: the total uncompressed size must be at most 1.5 GB, with at most 500 entries.

## The screen (`ui/prompt_test_page.py`)

State: `st.session_state.ptest` (a `PromptTest`), `st.session_state.ptest_results` (`TestResults` plus a signature of the inputs), and a `nonce` used to reset uploaders.

Top to bottom:

1. **Title and lede.** Then a row with **Open test** (uploader for `.rqtest`) and **Download test** (download button). The caption reads "Nothing is saved automatically. Download the test to keep it."
2. **Test name** (text input).
3. **Step 1, model view:** uploader and thumbnail. Replacing it asks nothing, but zones stay (masks are resized).
4. **Step 2, prompts:** one `st.expander` per prompt, labelled `"{n}. {title}"`, with a "Guardrail" or "↳ from P{k}" suffix. Inside:
   - title input, full-text area, kind radio (Edit / Guardrail), and a "Starts from" select
   - buttons: move up, move down, remove
   - edit prompts only: a "Change zone" toggle, which opens the `mask_painter` on the model view (key per prompt id), and a "Also include these materials" multiselect of detected material swatches (a thumbnail strip of swatches is shown above it)
   - **Add prompt** below the list
   - `chain_problems` warnings appear above the list
5. **Step 3, models and renders:**
   - **Add model** form: tool picker plus model picker.
   - Then `st.tabs`, one per model label, each with a remove-model button. Each tab lists the prompts in order:
     - edit prompts: a thumbnail and filename with a Replace/Remove control, or an uploader if the slot is empty. The model and prompt are guessed from filenames only when the user opts to drop several files at once (see below).
     - star rating (`st.feedback("stars")`, keyed per model and prompt)
     - guardrail prompts: an outcome radio (Refused / Partly / Complied / Not recorded) and an optional image
   - A per-model **"Drop all this model's renders"** multi-uploader assigns files to prompts by a number in the filename (`p3`, `prompt 3`, `_3.`, `-03`), filling empty slots in order for anything left over. It shows what went where.
6. **Step 4, recommendation** (text area): "Used in the exec report".
7. **Run all checks** (big primary button). This shows progress: "Checking {label}, P{n} ({k} of {N})".
8. **Results**, shown once results exist. If the inputs changed since the run, a stale banner appears.
   - "**{best}** came out on top with **{overall}/100**", plus caveats (partial prompts, missing ratings).
   - Leaderboard: an Altair bar of overall scores, plus a dataframe with Rank, Model, Overall, Kept, Your rating, Drift, Quality, Guardrails, Prompts run and Notes. Score columns are progress columns.
   - **Quality over edits:** an Altair line chart of step against Quality, one line per model.
   - **Grid:** for each edit prompt, a row of per-model cells showing the overlay thumbnail, Kept, stars, and ⚠ flags. A "Details" button per cell opens an `st.dialog` with the overlay, material overlay, fader (base vs render), all scores, the Quality breakdown and notes/warnings.
   - Downloads: **Exec report (.pptx)** as the primary button, and **Results (CSV)**.

Ratings and outcomes can be changed after a run without re-running. Aggregation is cheap and re-computed on every rerun from the stored per-render results and the current ratings. The stale banner only appears for changes that affect image analysis: images, zones, chains, prompt kinds or settings.

## Exec report (`core/deck.py`)

Uses `python-pptx`, on a 10 × 5.625 in blank canvas, following the TGS design system:
- **Colours:** Black #000000 and Cream #F4EFE4, with text colour flipped to contrast.
- **Fonts:** Cal Sans for headings, Inconsolata for labels and body, Geom Light for supporting copy. If they aren't installed, PowerPoint substitutes them.
- **Footer on every slide:** "The General Store — Copyright + Confidential 2026" in Inconsolata 5pt, rotated 270° at x 8.67, y 4.11, w 2.10, h 0.22 in.
- **Cards:** rounded rectangles with `adjustments[0] = 0.08` and centred text.

Slides:
1. **Cover (black):** TGS logo, the test name, "THE GENERAL STORE", and "AI model prompt test · {date}".
2. **Agenda (cream):** The answer, Leaderboard, How we tested, Degradation, Prompt by prompt, Guardrails, Recommendation.
3. **The answer (black statement):** "{best} came out on top", plus a one-line reason generated from its strongest part (e.g. "Kept 94/100 of what it was told to keep and showed no degradation over 5 edits").
4. **Leaderboard (cream):** a native clustered bar chart of overall scores by model, and a table below it with Kept / Rating / Drift / Quality / Guardrails.
5. **How we tested (cream, 4-column comparison):** Kept, Drift, Quality and Your rating, each explained in plain English, with the prompt headlines listed and the chaining mode stated.
6. **Degradation (black):** a native line chart of Quality by step per model, with one takeaway line (the model with the steepest drop vs the flattest).
7. **One slide per edit prompt (alternating cream/black):** the title, the full prompt text (Geom Light, truncated to about 400 characters), and each model's render thumbnail. There are up to 4 per row; with more than 4 models the images shrink to fit two rows. Under each thumbnail are Kept / stars / flags.
8. **Guardrails (cream):** a table of model by guardrail prompt showing the outcome. Skipped if there are no guardrail prompts.
9. **Biggest misses (black):** the 3 lowest-Kept renders, each showing its overlay and material overlay side by side, with a caption.
10. **Recommendation (black statement):** the user's text. If it's empty, it says "Add your recommendation".
11. **Appendix (cream):** the full score table, with every model × prompt row. It splits across slides at 14 rows.

Images are embedded as JPEG (quality 85, long side 1200 px) to keep the file small. `build_deck(test, results, summaries, when) -> bytes`.

## Error handling

| Situation | Behaviour |
|---|---|
| A slot has no render | The cell shows "Not run". Averages use the prompts that were run, marked "5 of 6 prompts". |
| The base render is missing in a chain | Walk back to the nearest ancestor with a render (or the model view), and note it. |
| The camera or aspect changed | The existing auto-align and warnings apply. An output size change is noted under Quality. |
| An edit prompt has no zone | Nudge in the prompt editor and the cell details. Changed = None. |
| Broken chain order (starts from a later prompt) | Warning above the prompt list. At run time it is treated as "previous". |
| No material regions found | Kept = lines only, with a note. |
| One render fails to load or check | Record the error in the cell and continue. |
| Bad, old or new `.rqtest` | Friendly `TestFileError` message. The current test is left untouched. |
| No model view | The run button is disabled, with a caption. |
| Deck with partial data | The slides that need missing data are skipped, and the rest are still produced. |

## Testing

These are pytest tests on synthetic images generated by `tests/synthetic.py` (extended). No real images are needed.

- `test_models.py`:
  - label formatting
  - `guess_model` picks the longest match
  - `remember_model` round-trips through a temporary file
- `test_materials.py`:
  - segmentation finds the synthetic boxes' fill colours and excludes the background
  - render→render with a global warm shift keeps everything
  - recolouring one box is caught, with its region in `changed_mask`
  - excluding that box via the zone keeps the score at 1.0
  - model→render: `photoreal_like(model)` passes, swapping two boxes' colours fails distinctness or order, and splitting a box into two colours fails consistency
- `test_change.py`: an unchanged zone gives about 0 with `nothing_changed`, and a repainted zone gives above 0.5.
- `test_quality.py`:
  - identical images score 100 or more on every part
  - a Gaussian-blurred copy has lower sharpness
  - a warm, saturated copy has lower colour creep
  - a JPEG quality 10 copy has lower artefacts
  - a half-size copy has lower resolution
  - changes inside excluded zones don't affect the score
- `test_prompt_test.py`:
  - chain resolution for previous, explicit, broken order and a missing base
  - zone unions
  - `run_test` on a two-model synthetic test: the degrading model's quality is lower, and a model that ignores a prompt is flagged `nothing_changed`
  - aggregation with missing ratings re-normalises the weights
- `test_testfile.py`:
  - a save → load round trip is equal (including zones, ratings and outcomes)
  - a wrong format, a newer version, or a corrupt zip each raise `TestFileError`
- `test_deck.py`:
  - the deck opens with python-pptx
  - it has the expected slide count for a 2-model, 7-prompt test
  - the chart parts exist
  - the footer text is on every slide
- The existing `tests/test_core.py` passes unchanged. `check_render` gets a `reference_kind="render"` test.
- Finally, an end-to-end browser run with `samples/` and `test_images/`: build a test, paint a zone, run it, open a cell, download the test and the deck.

## Out of scope

- Any AI or vision model, or cloud call (including Jev).
- Judging *whether* the requested change is good, beyond the user's stars.
- Server-side persistence of tests.
- Editing chart styles in the app.
