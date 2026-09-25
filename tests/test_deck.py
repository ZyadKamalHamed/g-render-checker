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


def _has_slide(prs, title):
    """A slide whose own title is ``title`` (the agenda lists the same words, so it doesn't count)."""
    for slide in prs.slides:
        lines = [sh.text_frame.text for sh in slide.shapes if sh.has_text_frame]
        if title in lines and "agenda" not in lines:
            return True
    return False


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
    # cover, agenda, answer, leaderboard, how, degradation, 3 prompt slides, guardrails, misses,
    # recommendation, appendix, thank you
    assert len(prs.slides) == 14
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
    assert not _has_slide(prs, "Guardrails")
    assert _has_slide(prs, "Degradation") and _has_slide(prs, "Biggest misses")
    assert "Add your recommendation" in texts
    assert len(prs.slides) >= 10


def test_deck_skips_slides_with_nothing_to_show():
    """One model, one prompt, and its only render can't be read: no degradation or misses slides."""
    t = _chain_test()
    t.prompts = t.prompts[:1]
    t.models = [ModelEntry(id="A", tool="Leonardo", slots={"p1": Slot(image=b"not an image", filename="bad.png")})]
    res = run_test(t, Settings())
    prs = Presentation(io.BytesIO(build_deck(t, res, summarise(t, res, Settings()), datetime(2026, 9, 25))))
    for title in ("Degradation", "Biggest misses", "Guardrails"):
        assert not _has_slide(prs, title), title
    assert _has_slide(prs, "Leaderboard")
    assert any("No model could be scored yet" in _texts(s) for s in prs.slides)


def test_answer_makes_no_unchecked_ranking_claim():
    """The winner's best part isn't necessarily better than everyone else's, so don't say "least"/"closest"."""
    t = _chain_test()
    res = run_test(t, Settings())
    prs = Presentation(io.BytesIO(build_deck(t, res, summarise(t, res, Settings()), datetime(2026, 9, 25))))
    texts = " ".join(_texts(s) for s in prs.slides)
    assert "came out on top" in texts
    assert "least degradation" not in texts and "closest to your model" not in texts


def test_chaining_describes_restarts_from_an_earlier_prompt():
    t = _chain_test()
    t.prompts[2].starts_from = "p1"  # P3 edits P1's render again, not the model view
    res = run_test(t, Settings())
    prs = Presentation(io.BytesIO(build_deck(t, res, summarise(t, res, Settings()), datetime(2026, 9, 25))))
    texts = " ".join(_texts(s) for s in prs.slides)
    assert "started again from the model view" not in texts
    assert "went back to an earlier prompt" in texts


def test_deck_many_models_and_missing_renders():
    """Nine models (one prompt slide overflows) where most slots are empty or broken."""
    t = _chain_test()
    extra = [ModelEntry(id=f"x{i}", tool="Tool", model=f"Model {i}") for i in range(7)]
    extra[0].slots["p1"] = Slot(image=b"not an image", filename="bad.png")
    t.models += extra
    res = run_test(t, Settings())
    prs = Presentation(io.BytesIO(build_deck(t, res, summarise(t, res, Settings()), datetime(2026, 9, 25))))
    texts = " ".join(_texts(s) for s in prs.slides)
    assert "Not run" in texts
    assert sum("P1 · Realistic" in _texts(s) for s in prs.slides) >= 2  # 9 models → two P1 slides


def test_deck_skips_prompts_no_model_ran():
    t = _chain_test()
    t.prompts.append(Prompt(id="p4", title="Add people"))  # nobody has a render for this one
    res = run_test(t, Settings())
    prs = Presentation(io.BytesIO(build_deck(t, res, summarise(t, res, Settings()), datetime(2026, 9, 25))))
    assert not any("P4 · Add people" in _texts(s) for s in prs.slides)
    assert any("P3 · Recolour metal" in _texts(s) for s in prs.slides)
