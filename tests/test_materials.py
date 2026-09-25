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
