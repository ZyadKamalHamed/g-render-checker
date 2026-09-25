"""Tolerant edge comparison using distance transforms.

A line in the original counts as "kept" if the render has a line within
``tolerance`` pixels of it, and vice versa. This is far more forgiving (and
more meaningful) than a pixel-exact difference.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class EdgeComparison:
    missing: np.ndarray  # original lines with no render line nearby (red)
    extra: np.ndarray  # render lines with no original line nearby (blue)
    recall: float  # share of original lines found in the render
    precision: float  # share of render lines that belong to the original
    f1: float  # combined fidelity, 0-1
    chamfer_px: float  # mean distance between the two sets of lines
    original_count: int
    render_count: int


def distance_to_edges(edges: np.ndarray) -> np.ndarray:
    """Distance (px) from every pixel to the nearest edge pixel."""
    if not edges.any():
        return np.full(edges.shape, np.inf, np.float32)
    inverted = np.where(edges, 0, 255).astype(np.uint8)
    return cv2.distanceTransform(inverted, cv2.DIST_L2, cv2.DIST_MASK_PRECISE)


def compare_edges(
    original: np.ndarray,
    render: np.ndarray,
    tolerance: float = 4,
    count_mask: np.ndarray | None = None,
) -> EdgeComparison:
    """Compare two boolean edge maps of the same size.

    ``count_mask`` (True = score this pixel) excludes ignored areas from the
    counts. Lines just outside it can still be used as matches, so a line
    sitting on the edge of an ignored area isn't unfairly flagged.
    """
    if original.shape != render.shape:
        raise ValueError("edge maps must be the same size")
    dist_to_render = distance_to_edges(render)
    dist_to_original = distance_to_edges(original)

    orig = original if count_mask is None else original & count_mask
    rend = render if count_mask is None else render & count_mask

    missing = orig & (dist_to_render > tolerance)
    extra = rend & (dist_to_original > tolerance)

    n_orig = int(orig.sum())
    n_rend = int(rend.sum())
    matched_orig = n_orig - int(missing.sum())
    matched_rend = n_rend - int(extra.sum())

    if n_orig == 0 and n_rend == 0:
        recall = precision = f1 = 1.0
    else:
        recall = matched_orig / n_orig if n_orig else 0.0
        precision = matched_rend / n_rend if n_rend else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    chamfer = _symmetric_chamfer(dist_to_render[orig], dist_to_original[rend])
    return EdgeComparison(missing, extra, recall, precision, f1, chamfer, n_orig, n_rend)


def _symmetric_chamfer(a: np.ndarray, b: np.ndarray) -> float:
    parts = [float(np.mean(x)) for x in (a, b) if x.size and np.isfinite(x).all()]
    return float(np.mean(parts)) if parts else float("nan")
