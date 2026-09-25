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
