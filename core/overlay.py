"""Drawing the "problem areas" picture shown to the user."""

from __future__ import annotations

import cv2
import numpy as np

# BGR
RED = (38, 38, 220)  # missing or moved from the model
BLUE = (235, 99, 37)  # added by the AI
IGNORED_GREY = (205, 205, 205)


def make_overlay(
    render: np.ndarray,
    missing: np.ndarray,
    extra: np.ndarray,
    ignored: np.ndarray | None = None,
) -> np.ndarray:
    """Wash out the render, then paint problem lines and soft area highlights."""
    h, w = render.shape[:2]
    gray = cv2.cvtColor(cv2.cvtColor(render, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
    muted = cv2.addWeighted(render, 0.4, gray, 0.6, 0)
    out = cv2.addWeighted(muted, 0.55, np.full_like(render, 255), 0.45, 0).astype(np.float32)

    if ignored is not None and ignored.any():
        out[ignored] = out[ignored] * 0.35 + np.array(IGNORED_GREY, np.float32) * 0.65
        _hatch(out, ignored)

    # Soft halos show *where* the trouble is, even when lines are thin.
    for mask, color in ((extra, BLUE), (missing, RED)):
        halo = problem_areas(mask)
        if halo.any():
            soft = cv2.GaussianBlur(halo.astype(np.float32), (0, 0), max(2.0, 0.004 * max(h, w)))
            alpha = (np.clip(soft, 0, 1) * 0.22)[..., None]
            out = out * (1 - alpha) + np.array(color, np.float32) * alpha

    thick = max(1, round(max(h, w) / 900))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * thick + 1, 2 * thick + 1))
    for mask, color in ((extra, BLUE), (missing, RED)):
        if mask.any():
            fat = cv2.dilate(mask.astype(np.uint8), kernel) > 0
            out[fat] = color
    return np.clip(out, 0, 255).astype(np.uint8)


def problem_areas(mask: np.ndarray) -> np.ndarray:
    """Group nearby problem lines into areas, dropping isolated specks."""
    h, w = mask.shape
    if not mask.any():
        return np.zeros_like(mask)
    r = max(3, round(0.012 * max(h, w)))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
    grown = cv2.dilate(mask.astype(np.uint8), kernel)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(grown, connectivity=8)
    counts = np.bincount(labels[mask], minlength=n)
    min_pixels = max(25, round(0.02 * max(h, w)))
    keep = counts >= min_pixels
    keep[0] = False
    return keep[labels]


def count_problem_areas(mask: np.ndarray) -> int:
    """How many separate, noticeable problem areas there are."""
    areas = problem_areas(mask)
    if not areas.any():
        return 0
    h, w = mask.shape
    n, _, stats, _ = cv2.connectedComponentsWithStats(areas.astype(np.uint8), connectivity=8)
    min_area = 0.0015 * h * w  # ignore tiny slivers
    return int((stats[1:, cv2.CC_STAT_AREA] >= min_area).sum())


def _hatch(out: np.ndarray, region: np.ndarray) -> None:
    h, w = region.shape
    yy, xx = np.mgrid[0:h, 0:w]
    step = max(10, max(h, w) // 80)
    stripes = ((xx + yy) % step) < max(1, step // 6)
    sel = region & stripes
    out[sel] = out[sel] * 0.6 + np.array((160, 160, 160), np.float32) * 0.4


def blend(original: np.ndarray, render: np.ndarray, amount: float) -> np.ndarray:
    """0 = original, 1 = render."""
    return cv2.addWeighted(original, 1 - amount, render, amount, 0)
