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
