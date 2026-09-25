import cv2
import numpy as np
import pytest

from core import Settings
from core.prompt_test import (
    EDIT, FROM_MODEL, FROM_PREVIOUS, GUARDRAIL, ModelEntry, Prompt, PromptTest, Slot, analysis_signature,
    ancestors, base_for_model, chain_problems, default_prompts, move_prompt, quality_series, remove_prompt,
    resolve_base, run_test, summarise, zone_mask,
)
from tests.synthetic import material_rect, material_scene, photoreal_like, png_bytes, region_mask, shift_colour


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
    A = ModelEntry(id="A", tool="Leonardo", model="GPT 2.5 Flare", slots={
        "p1": Slot(png_bytes(a1), rating=5), "p2": Slot(png_bytes(a2), rating=4), "p3": Slot(png_bytes(a3))})
    B = ModelEntry(id="B", tool="Leonardo", model="Nano Banana Pro", slots={
        "p1": Slot(png_bytes(b1)), "p2": Slot(png_bytes(b2)), "p3": Slot(png_bytes(b3))})
    t.models = [A, B]
    return t


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
    assert res.renders[("A", "p2")].base_label.startswith("P1")


def test_degrading_model_has_lower_quality(chain_results):
    t, res = chain_results
    assert res.renders[("B", "p3")].quality < res.renders[("A", "p3")].quality - 5
    assert res.renders[("B", "p3")].step == 2


def test_ignored_prompt_is_flagged(chain_results):
    t, res = chain_results
    assert res.renders[("B", "p3")].nothing_changed is True
    assert res.renders[("A", "p3")].nothing_changed is False


def test_quality_series_has_baseline_and_steps(chain_results):
    t, res = chain_results
    rows = [r for r in quality_series(t, res) if r["model"] == "B"]
    assert [r["step"] for r in rows] == [0, 1, 2]
    assert rows[0]["quality"] == 100


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
    assert any("compared with prompt 1" in n for n in res.renders[("A", "p3")].notes)


def test_weights_are_settings():
    s = Settings(weight_kept=500, weight_rating=-3).validated()
    assert s.weight_kept == 100 and s.weight_rating == 0
    assert Settings().weight_drift == 20 and Settings().weight_quality == 15


@pytest.mark.parametrize("name,expected", [
    ("nano_p3.png", 3), ("Prompt 4 - flare.jpg", 4), ("render_05.webp", 5), ("gpt-2.png", 2),
    ("flare.png", None), ("p12.png", None), ("gpt-2.5-flare_p3.png", 3), ("gpt-2.5-flare.png", None),
])
def test_prompt_from_filename(name, expected):
    from core.prompt_test import prompt_from_filename
    assert prompt_from_filename(name, 7) == expected


def test_assign_files_fills_detected_then_empty_edit_slots():
    from core.prompt_test import assign_files
    t = PromptTest()  # 6 edit prompts + 1 guardrail
    m = ModelEntry(id="m", tool="Leonardo")
    m.slots[t.prompts[0].id] = Slot(image=b"old", filename="old.png")
    files = [("nano_p3.png", b"3"), ("extra.png", b"x"), ("again_p3.png", b"3b"), ("p7.png", b"7")]
    files += [(f"more{c}.png", b"m") for c in "abcde"]
    lines = assign_files(t, m, files)
    assert m.slots[t.prompts[2].id].image == b"3" and m.slots[t.prompts[2].id].filename == "nano_p3.png"
    assert m.slots[t.prompts[6].id].image == b"7"  # a guardrail prompt named in the file takes it
    assert m.slots[t.prompts[1].id].image == b"x"  # first leftover goes to the first empty edit slot
    assert m.slots[t.prompts[0].id].image == b"old"  # filled slots are never overwritten by leftovers
    assert lines[0] == "nano_p3.png → Prompt 3"
    assert lines[1] == "extra.png → Prompt 2"
    assert lines[2] == "again_p3.png → Prompt 4"  # prompt 3 was already taken in this drop
    assert lines[-1] == "moree.png → not used (no empty prompt left)"


def test_ratings_missing_counts_only_renders_that_ran():
    t = _chain_test()
    del t.models[1].slots["p3"]  # B has no render for prompt 3, so there's nothing to rate
    res = run_test(t, Settings())
    b = next(s for s in summarise(t, res, Settings()) if s.model_id == "B")
    assert b.ran == 2 and b.ratings_missing == 2


def test_rating_without_a_render_is_ignored():
    t = _chain_test()
    t.models[1].slots["p4"] = Slot(rating=1)  # rated, but there's no render and no such prompt run
    t.prompts.append(Prompt(id="p4", title="Add people"))
    res = run_test(t, Settings())
    b = next(s for s in summarise(t, res, Settings()) if s.model_id == "B")
    assert b.rating is None
