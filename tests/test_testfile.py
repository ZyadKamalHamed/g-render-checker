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


def test_bad_values_are_cleaned_up():
    t = _sample()
    data = json.loads(zipfile.ZipFile(io.BytesIO(save_test(t))).read("test.json"))
    data["prompts"][0]["kind"] = "weird"
    slot = data["models"][0]["slots"][t.prompts[0].id]
    slot["rating"], slot["outcome"] = 9, "maybe"
    src = zipfile.ZipFile(io.BytesIO(save_test(t)))
    files = {n: src.read(n) for n in src.namelist()}
    files["test.json"] = json.dumps(data)
    back = load_test(_zip(files))
    s = back.models[0].slots[t.prompts[0].id]
    assert back.prompts[0].kind == "edit" and s.rating is None and s.outcome is None
