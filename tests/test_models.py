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
