import io

import cv2
import numpy as np
import pytest
from PIL import Image

from core import ImageLoadError, Settings, check_render, load_image, score_level
from core.compare import compare_edges
from core.overlay import BLUE, RED
from core.settings import load_settings, save_settings
from tests.synthetic import FEATURE_BOX, box, draw_scene, harsh_photoreal, photoreal_like, region_mask


@pytest.fixture(scope="module")
def original():
    return draw_scene(extra_boxes=[box()])


def share_inside(mask, region):
    total = mask.sum()
    return (mask & region).sum() / total if total else 0.0


def test_identical_images_score_near_100(original):
    result = check_render(original, original.copy())
    assert result.score >= 98
    assert result.level == "good" and result.label == "Accurate"
    assert result.comparison.missing.sum() == 0


def test_removed_rectangle_shows_red_in_that_region(original):
    render = draw_scene()  # same scene without the feature box
    result = check_render(original, render)
    region = region_mask(result.original.shape[:2], FEATURE_BOX)
    missing = result.comparison.missing
    assert missing.sum() > 300
    assert share_inside(missing, region) > 0.9
    red = np.all(result.overlay == RED, axis=2)
    assert share_inside(red, region) > 0.9
    assert result.score < 98


def test_added_rectangle_shows_blue_in_that_region():
    original = draw_scene()
    render = draw_scene(extra_boxes=[box()])
    result = check_render(original, render)
    region = region_mask(result.original.shape[:2], FEATURE_BOX)
    extra = result.comparison.extra
    assert extra.sum() > 300
    assert share_inside(extra, region) > 0.9
    blue = np.all(result.overlay == BLUE, axis=2)
    assert share_inside(blue, region) > 0.9
    # The new box covers part of the floor line; nothing should be missing elsewhere.
    assert (result.comparison.missing & ~region).sum() < 50


@pytest.mark.parametrize("auto_align", [True, False])
def test_small_shift_still_scores_high(original, auto_align):
    render = draw_scene(extra_boxes=[box()], shift=(3, 2))
    result = check_render(original, render, Settings(auto_align=auto_align))
    assert result.score >= 90


def test_ignore_mask_excludes_area(original):
    render = draw_scene()
    ignore = region_mask(original.shape[:2], FEATURE_BOX, pad=25)
    result = check_render(original, render, ignore_mask=ignore)
    assert result.score >= 97
    assert result.comparison.missing.sum() < 50


def test_ignore_mask_of_different_size_is_resized(original):
    render = draw_scene()
    small = cv2.resize(region_mask(original.shape[:2], FEATURE_BOX, pad=25).astype(np.uint8) * 255, (300, 200))
    result = check_render(original, render, ignore_mask=small)
    assert result.score >= 95


def test_auto_align_recovers_zoom_and_offset(original):
    # Render zoomed in ~4% and offset, like an AI tool slightly reframing the shot.
    h, w = original.shape[:2]
    M = np.float32([[1.04, 0, -18], [0, 1.04, -30]])
    render = cv2.warpAffine(original, M, (w, h), borderValue=(236, 236, 236))
    unaligned = check_render(original, render, Settings(auto_align=False))
    aligned = check_render(original, render)
    assert aligned.aligned
    assert aligned.score >= 90
    assert aligned.score > unaligned.score + 20


def test_auto_align_copes_with_heavy_texture(original):
    # Wood grain and speckle defeat feature matching; lining up the line maps still works.
    h, w = original.shape[:2]
    M = np.float32([[1.05, 0, -25], [0, 1.05, -15]])
    render = harsh_photoreal(cv2.warpAffine(original, M, (w, h), borderValue=(236, 236, 236)))
    unaligned = check_render(original, render, Settings(auto_align=False))
    aligned = check_render(original, render)
    assert aligned.aligned
    assert aligned.score >= 85
    assert aligned.score > unaligned.score + 20


def test_different_aspect_ratio_outpainted_render(original):
    # AI tool returned a wider image with extra content on both sides.
    h, w = original.shape[:2]
    wide = np.full((h, w + 400, 3), 236, np.uint8)
    wide[:, 200 : 200 + w] = original
    cv2.rectangle(wide, (20, 100), (180, 600), (90, 90, 90), 3)
    result = check_render(original, wide)
    assert result.score >= 95
    assert any("different shape" in n for n in result.notes + result.warnings)


def test_photoreal_texture_on_same_geometry_still_scores_well(original):
    result = check_render(original, photoreal_like(original))
    assert result.score >= 85, result.score


def test_heavily_textured_render_of_same_geometry_scores_well(original):
    assert check_render(original, harsh_photoreal(original)).score >= 85


def test_problem_areas_are_counted(original):
    assert check_render(original, original.copy()).missing_areas == 0
    removed = check_render(original, draw_scene())
    assert removed.missing_areas == 1
    added = check_render(draw_scene(), original)
    assert added.added_areas == 1 and added.missing_areas <= 1


def test_photoreal_with_removed_box_scores_lower_than_faithful(original):
    faithful = check_render(original, photoreal_like(original)).score
    changed = check_render(original, photoreal_like(draw_scene())).score
    assert changed < faithful - 3


def test_completely_different_image_scores_low(original):
    rng = np.random.default_rng(1)
    other = np.full_like(original, 236)
    for _ in range(12):
        x, y = rng.integers(0, 1100), rng.integers(0, 700)
        cv2.circle(other, (int(x), int(y)), int(rng.integers(20, 90)), (40, 40, 40), 2)
    result = check_render(original, other)
    assert result.score < 40
    assert result.level == "bad"
    assert result.warnings


def test_large_images_are_downscaled_on_load():
    # A high-res screenshot: the same scene at 3.5x, lines scaled up too.
    big = cv2.resize(draw_scene(), (4200, 2800), interpolation=cv2.INTER_NEAREST)
    buf = io.BytesIO()
    Image.fromarray(big[..., ::-1]).save(buf, "PNG")
    img = load_image(buf.getvalue())
    assert max(img.shape[:2]) <= 2500
    result = check_render(img, img.copy())
    assert max(result.original.shape[:2]) <= Settings().work_size
    assert result.score >= 98


@pytest.mark.parametrize("fmt", ["PNG", "JPEG", "WEBP"])
def test_accepts_common_formats(fmt):
    buf = io.BytesIO()
    Image.new("RGB", (200, 120), (10, 200, 30)).save(buf, fmt)
    img = load_image(buf.getvalue())
    assert img.shape == (120, 200, 3)


def test_transparent_png_goes_on_white():
    buf = io.BytesIO()
    Image.new("RGBA", (100, 100), (0, 0, 0, 0)).save(buf, "PNG")
    assert load_image(buf.getvalue()).min() == 255


@pytest.mark.parametrize("data", [b"", b"not an image at all", b"%PDF-1.4 fake"])
def test_bad_files_give_friendly_error(data):
    with pytest.raises(ImageLoadError) as e:
        load_image(data)
    assert "PNG" in str(e.value) or "empty" in str(e.value)


def test_compare_edges_tolerance():
    a = np.zeros((100, 100), bool)
    a[50, 10:90] = True
    b = np.roll(a, 3, axis=0)
    assert compare_edges(a, b, tolerance=4).f1 == pytest.approx(1.0)
    far = compare_edges(a, np.roll(a, 8, axis=0), tolerance=4)
    assert far.f1 == 0.0 and far.chamfer_px == pytest.approx(8, abs=0.5)


def test_score_levels_follow_thresholds():
    s = Settings(good_threshold=90, ok_threshold=70)
    assert score_level(95, s) == ("good", "Accurate")
    assert score_level(80, s) == ("ok", "Check closely")
    assert score_level(50, s) == ("bad", "Geometry changed a lot")


def test_settings_roundtrip(tmp_path):
    path = tmp_path / "settings.json"
    save_settings(Settings(match_tolerance_px=6, ok_threshold=99, good_threshold=80), path)
    loaded = load_settings(path)
    assert loaded.match_tolerance_px == 6
    assert loaded.ok_threshold <= loaded.good_threshold
    path.write_text("{broken")
    assert load_settings(path) == Settings()


def test_report_png_and_pdf(original):
    from core.report import build_report, to_pdf_bytes, to_png_bytes

    result = check_render(original, draw_scene())
    page = build_report(result, "Gendo", job_name="Lobby view")
    assert page.width == 2400
    assert to_png_bytes(page).startswith(b"\x89PNG")
    assert to_pdf_bytes(page).startswith(b"%PDF")


def test_comparison_summary_image():
    from core.report import ToolSummary, build_comparison_summary

    img = build_comparison_summary(
        [ToolSummary("Gendo", 91, 2, "good"), ToolSummary("Leonardo", 60, 2, "bad")],
        [("Lobby", {"Gendo": 90, "Leonardo": 55}), ("Café", {"Gendo": 92})],
    )
    assert img.width == 2000 and img.height > 500
