"""Line (edge) detection tuned separately for clean viewports and photoreal renders.

Viewport screenshots are mostly flat colour with crisp lines, so a light blur
and moderate thresholds pick up the geometry. Photoreal renders are full of
texture, shadow and reflection detail, so they get edge-preserving smoothing,
a stronger blur, higher thresholds, and short fragments are thrown away.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

# Sizes below are tuned for a ~1600px working image and scaled from there.
REFERENCE_SIDE = 1600


@dataclass(frozen=True)
class EdgeParams:
    blur: int  # Gaussian kernel size (odd)
    low: float  # Canny low threshold
    high: float  # Canny high threshold
    min_length: int  # drop connected edge fragments smaller than this many pixels
    smooth: bool  # edge-preserving (bilateral) smoothing first


def sensitivity_to_thresholds(sensitivity: float) -> tuple[float, float]:
    """Map a 0-100 sensitivity to Canny thresholds (higher = more lines)."""
    s = float(np.clip(sensitivity, 0, 100))
    high = 300.0 - 2.6 * s
    return 0.4 * high, high


def params_for_original(sensitivity: float) -> EdgeParams:
    low, high = sensitivity_to_thresholds(sensitivity)
    return EdgeParams(blur=3, low=low, high=high, min_length=10, smooth=False)


def params_for_render(sensitivity: float) -> EdgeParams:
    low, high = sensitivity_to_thresholds(sensitivity)
    return EdgeParams(blur=5, low=low, high=high, min_length=30, smooth=True)


def _odd(n: float) -> int:
    n = max(1, int(round(n)))
    return n if n % 2 else n + 1


def detect_edges(bgr: np.ndarray, params: EdgeParams) -> np.ndarray:
    """Return a boolean edge map the same size as the image."""
    scale = max(bgr.shape[:2]) / REFERENCE_SIDE
    img = bgr
    if params.smooth:
        d = _odd(9 * scale)
        img = cv2.bilateralFilter(img, d, sigmaColor=40, sigmaSpace=d)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    k = _odd(params.blur * max(scale, 0.6))
    if k > 1:
        gray = cv2.GaussianBlur(gray, (k, k), 0)
    edges = cv2.Canny(gray, params.low, params.high, L2gradient=True)
    min_len = max(1, int(round(params.min_length * scale)))
    if min_len > 1:
        edges = remove_small_fragments(edges, min_len)
    return edges > 0


def remove_small_fragments(edges: np.ndarray, min_pixels: int) -> np.ndarray:
    n, labels, stats, _ = cv2.connectedComponentsWithStats(
        (edges > 0).astype(np.uint8), connectivity=8
    )
    if n <= 1:
        return edges
    keep = stats[:, cv2.CC_STAT_AREA] >= min_pixels
    keep[0] = False
    return np.where(keep[labels], 255, 0).astype(np.uint8)


def edges_to_image(edges: np.ndarray) -> np.ndarray:
    """Dark lines on white, for previewing what was detected."""
    img = np.full(edges.shape + (3,), 255, np.uint8)
    img[edges] = (40, 40, 40)
    return img
