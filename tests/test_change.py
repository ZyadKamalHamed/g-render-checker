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


def test_different_noise_render_of_same_scene_counts_as_unchanged():
    base = photoreal_like(material_scene(), seed=5)
    again = photoreal_like(material_scene(), seed=6)
    zone = region_mask(base.shape[:2], material_rect(2))
    assert changed_fraction(base, again, zone) < NOTHING_CHANGED_BELOW
