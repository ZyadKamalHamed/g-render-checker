"""Did anything actually change inside a prompt's change zone?"""

from __future__ import annotations

import cv2
import numpy as np

from .materials import match_global, to_lab

NOTHING_CHANGED_BELOW = 0.15  # share of the zone that must change before we say it did
CHANGED_DE = 12


def delta_e_map(base: np.ndarray, render: np.ndarray, match_area: np.ndarray | None) -> np.ndarray:
    """Per-pixel colour difference after cancelling any global colour shift and a light blur."""
    sigma = 1.5 * max(base.shape[:2]) / 1600
    a = cv2.GaussianBlur(to_lab(base), (0, 0), sigma)
    b = cv2.GaussianBlur(to_lab(render), (0, 0), sigma)
    b = match_global(a, b, match_area)
    return np.linalg.norm(a - b, axis=-1)


def changed_fraction(base, render, zone, valid=None) -> float | None:
    """Share of the zone that changed noticeably; None when there's no zone."""
    zone = zone.astype(bool)
    valid = np.ones(zone.shape, bool) if valid is None else valid.astype(bool)
    inside = zone & valid
    if not inside.any():
        return None
    match_area = valid & ~zone
    if match_area.sum() < 1000:
        match_area = valid
    de = delta_e_map(base, render, match_area)
    return float((de[inside] > CHANGED_DE).mean())
