"""Materials: find the flat-colour areas of a model view and check renders keep them.

A SketchUp-style view paints each material one flat colour, so grouping its
colours gives regions that line up with the same materials in every render.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

AMBER = (11, 158, 245)  # BGR for #F59E0B

_CLUSTER_SIDE = 400  # px, long side used to find seed colours
_BIN = 6  # Lab units per quantisation cube
_SEED_SHARE = 0.005  # a seed colour must cover this share of the image
_SEED_MERGE_DE = 8
_MAX_REGIONS = 12
_ASSIGN_DE = 12
_MIN_PIXELS = 200  # fewer visible pixels than this and a region isn't scored

_COLOUR_DE = 10  # render -> render: region mean may move this far
_TEXTURE_RANGE = (0.6, 1.67)
_SPLIT_SHARE, _SPLIT_DE = 0.25, 25
_DISTINCT_MODEL_DE, _DISTINCT_RENDER_DE = 15, 6
_ORDER_DL, _ORDER_SLACK = 15, 2


@dataclass
class MaterialRegion:
    id: int  # 0 = largest
    lab: np.ndarray  # float32 (3,), mean Lab (L 0-100)
    bgr: tuple[int, int, int]  # mean colour, for swatches
    mask: np.ndarray  # bool, image shape (already eroded)
    area_share: float


@dataclass
class RegionCheck:
    id: int
    kept: bool
    reason: str = ""


@dataclass
class MaterialResult:
    score: float  # 0-1, area-weighted share kept (1.0 if nothing could be scored)
    kept_count: int
    total: int  # regions actually scored
    changed_mask: np.ndarray  # bool, union of failed regions
    regions: list[RegionCheck] = field(default_factory=list)


def to_lab(bgr: np.ndarray) -> np.ndarray:
    """float32 Lab with L 0-100 and a/b centred on 0."""
    return cv2.cvtColor(bgr.astype(np.float32) / 255.0, cv2.COLOR_BGR2LAB)


def _de(a, b) -> np.ndarray:
    return np.linalg.norm(np.asarray(a, np.float32) - np.asarray(b, np.float32), axis=-1)


def match_global(a_lab: np.ndarray, b_lab: np.ndarray, area: np.ndarray) -> np.ndarray:
    """Shift ``b_lab`` so its mean over ``area`` equals ``a_lab``'s."""
    if area is None or not area.any():
        return b_lab
    return b_lab + (a_lab[area].mean(axis=0) - b_lab[area].mean(axis=0))


def _erode(mask: np.ndarray, r: int) -> np.ndarray:
    k = np.ones((2 * r + 1, 2 * r + 1), np.uint8)
    return cv2.erode(mask.astype(np.uint8), k) > 0


def segment_materials(model_view: np.ndarray) -> list[MaterialRegion]:
    h, w = model_view.shape[:2]
    lab = to_lab(model_view)

    scale = min(1.0, _CLUSTER_SIDE / max(h, w))
    small = cv2.resize(lab, (max(1, round(w * scale)), max(1, round(h * scale))), interpolation=cv2.INTER_NEAREST)
    px = small.reshape(-1, 3)
    bins = np.floor(px / _BIN).astype(np.int32)
    uniq, inverse, counts = np.unique(bins, axis=0, return_inverse=True, return_counts=True)
    inverse = inverse.reshape(-1)
    order = np.argsort(-counts)
    seeds: list[np.ndarray] = []
    for i in order:
        if counts[i] < _SEED_SHARE * len(px):
            break
        colour = px[inverse == i].mean(axis=0)
        if all(_de(colour, s) > _SEED_MERGE_DE for s in seeds):
            seeds.append(colour)
        if len(seeds) == _MAX_REGIONS:
            break
    if not seeds:
        return []

    best = np.full((h, w), np.inf, np.float32)
    label = np.full((h, w), -1, np.int32)
    for k, s in enumerate(seeds):
        d = _de(lab, s)
        closer = (d < best) & (d <= _ASSIGN_DE)
        label[closer] = k
        best = np.minimum(best, d)

    r = max(2, round(0.003 * max(h, w)))
    total = h * w
    candidates = []
    for k in range(len(seeds)):
        raw = label == k
        if not raw.any():
            continue
        touches = raw[0].any() or raw[-1].any() or raw[:, 0].any() or raw[:, -1].any()
        mask = _erode(raw, r)
        if mask.sum() < _SEED_SHARE * total:
            continue
        mean = lab[mask].mean(axis=0)
        chroma = float(np.hypot(mean[1], mean[2]))
        background = touches and mean[0] > 92 and chroma < 6
        candidates.append((mask, mean, background))

    backgrounds = [c for c in candidates if c[2]]
    if backgrounds:
        biggest = max(backgrounds, key=lambda c: c[0].sum())
        candidates = [c for c in candidates if c is not biggest]
    candidates.sort(key=lambda c: -int(c[0].sum()))

    regions = []
    for i, (mask, mean, _) in enumerate(candidates):
        bgr = model_view[mask].mean(axis=0)
        regions.append(MaterialRegion(
            id=i, lab=mean.astype(np.float32), bgr=tuple(int(round(v)) for v in bgr),
            mask=mask, area_share=float(mask.sum() / total),
        ))
    return regions


def swatch(region: MaterialRegion, size: int = 48) -> np.ndarray:
    return np.full((size, size, 3), region.bgr, np.uint8)


def _area(shape, excluded, valid) -> np.ndarray:
    area = np.ones(shape, bool) if valid is None else valid.astype(bool).copy()
    if excluded is not None:
        area &= ~excluded.astype(bool)
    return area


def _weighted_median(values: np.ndarray, weights: np.ndarray) -> np.ndarray:
    out = np.zeros(values.shape[1], np.float32)
    for c in range(values.shape[1]):
        order = np.argsort(values[:, c])
        cum = np.cumsum(weights[order])
        out[c] = values[order[np.searchsorted(cum, cum[-1] / 2)], c]
    return out


def _result(checks: list[RegionCheck], sizes: dict[int, int], regions, area) -> MaterialResult:
    by_id = {r.id: r for r in regions}
    scored = [c for c in checks if c.id in sizes]
    total_px = sum(sizes.values())
    kept_px = sum(sizes[c.id] for c in scored if c.kept)
    changed = np.zeros(area.shape, bool)
    for c in scored:
        if not c.kept:
            changed |= by_id[c.id].mask & area
    return MaterialResult(
        score=kept_px / total_px if total_px else 1.0,
        kept_count=sum(c.kept for c in scored),
        total=len(scored),
        changed_mask=changed,
        regions=checks,
    )


def _texture(lab: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    L = lab[..., 0]
    gx = cv2.Sobel(L, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(L, cv2.CV_32F, 0, 1, ksize=3)
    return L, np.hypot(gx, gy)


def _in_range(a: float, b: float, eps: float = 0.5) -> bool:
    ratio = (b + eps) / (a + eps)
    return _TEXTURE_RANGE[0] <= ratio <= _TEXTURE_RANGE[1]


def materials_between_renders(base, render, regions, excluded=None, valid=None) -> MaterialResult:
    """Did each material outside the change zone keep its colour and texture?"""
    area = _area(base.shape[:2], excluded, valid)
    lab_a, lab_b = to_lab(base), to_lab(render)
    La, Ga = _texture(lab_a)
    Lb, Gb = _texture(lab_b)

    stats = {}
    for r in regions:
        m = r.mask & area
        n = int(m.sum())
        if n >= _MIN_PIXELS:
            stats[r.id] = (m, n, lab_a[m].mean(axis=0), lab_b[m].mean(axis=0))

    # Robust global shift: most materials should agree on it, so a changed one
    # doesn't drag every other material off with it.
    shift = np.zeros(3, np.float32)
    if stats:
        diffs = np.array([s[2] - s[3] for s in stats.values()], np.float32)
        weights = np.array([s[1] for s in stats.values()], np.float32)
        shift = _weighted_median(diffs, weights)

    checks = []
    for r in regions:
        if r.id not in stats:
            checks.append(RegionCheck(r.id, True, "not enough visible"))
            continue
        m, _, mean_a, mean_b = stats[r.id]
        if _de(mean_a, mean_b + shift) > _COLOUR_DE:
            checks.append(RegionCheck(r.id, False, "colour changed"))
        elif not (_in_range(float(La[m].std()), float(Lb[m].std()))
                  and _in_range(float(Ga[m].mean()), float(Gb[m].mean()))):
            checks.append(RegionCheck(r.id, False, "texture changed"))
        else:
            checks.append(RegionCheck(r.id, True))
    return _result(checks, {i: s[1] for i, s in stats.items()}, regions, area)


def _splits(values: np.ndarray) -> bool:
    if len(values) < 20:
        return False
    rng = np.random.default_rng(0)
    if len(values) > 4000:
        values = values[rng.choice(len(values), 4000, replace=False)]
    cv2.setRNGSeed(0)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.5)
    _, labels, centres = cv2.kmeans(values.astype(np.float32), 2, None, criteria, 3, cv2.KMEANS_PP_CENTERS)
    minor = min(labels.mean(), 1 - labels.mean())
    return minor >= _SPLIT_SHARE and _de(centres[0], centres[1]) > _SPLIT_DE


def materials_from_model(model_view, render, regions, excluded=None, valid=None) -> MaterialResult:
    """Did the render keep the model's materials apart, whole, and in light/dark order?"""
    area = _area(model_view.shape[:2], excluded, valid)
    lab_r = to_lab(render)

    stats = {}
    for r in regions:
        m = r.mask & area
        n = int(m.sum())
        if n >= _MIN_PIXELS:
            stats[r.id] = (lab_r[m], n, lab_r[m].mean(axis=0))

    reasons: dict[int, str] = {}
    for i, (values, _, _) in stats.items():
        if _splits(values):
            reasons[i] = "became two materials"

    model_lab = {r.id: r.lab for r in regions}
    ids = list(stats)
    for x, i in enumerate(ids):
        for j in ids[x + 1:]:
            if _de(model_lab[i], model_lab[j]) > _DISTINCT_MODEL_DE and _de(stats[i][2], stats[j][2]) <= _DISTINCT_RENDER_DE:
                for k in (i, j):
                    reasons.setdefault(k, "merged with another material")
    for x, i in enumerate(ids):
        for j in ids[x + 1:]:
            dl = float(model_lab[i][0] - model_lab[j][0])
            if abs(dl) > _ORDER_DL and (stats[i][2][0] - stats[j][2][0]) * np.sign(dl) < -_ORDER_SLACK:
                for k in (i, j):
                    reasons.setdefault(k, "light/dark order changed")

    checks = []
    for r in regions:
        if r.id not in stats:
            checks.append(RegionCheck(r.id, True, "not enough visible"))
        elif r.id in reasons:
            checks.append(RegionCheck(r.id, False, reasons[r.id]))
        else:
            checks.append(RegionCheck(r.id, True))
    return _result(checks, {i: s[1] for i, s in stats.items()}, regions, area)


def material_overlay(render: np.ndarray, result: MaterialResult, regions: list[MaterialRegion]) -> np.ndarray:
    """The render washed out, with materials that changed outlined in amber."""
    h, w = render.shape[:2]
    gray = cv2.cvtColor(cv2.cvtColor(render, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
    muted = cv2.addWeighted(render, 0.4, gray, 0.6, 0)
    out = cv2.addWeighted(muted, 0.55, np.full_like(render, 255), 0.45, 0)
    thick = max(2, max(h, w) // 500)
    by_id = {r.id: r for r in regions}
    font_scale = max(0.5, max(h, w) / 1600)
    for c in result.regions:
        if c.kept or c.id not in by_id:
            continue
        mask = (by_id[c.id].mask).astype(np.uint8)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(out, contours, -1, AMBER, thick)
        x, y, bw, bh = cv2.boundingRect(mask)
        text = f"M{c.id + 1}: {c.reason}"
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 2)
        tx, ty = min(x + thick * 2, max(0, w - tw - 4)), min(h - 4, y + th + thick * 3)
        cv2.rectangle(out, (tx - 3, ty - th - 4), (tx + tw + 3, ty + 5), (255, 255, 255), -1)
        cv2.putText(out, text, (tx, ty), cv2.FONT_HERSHEY_SIMPLEX, font_scale, AMBER, 2, cv2.LINE_AA)
    return out
