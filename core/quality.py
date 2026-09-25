"""Quality degradation between a model's first render and a later edit of it.

Measured only where no prompt has asked for a change, so a lost detail or a
creeping colour cast shows up, but the requested edit doesn't.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from .materials import to_lab

_EPS = 1e-6
_BORDER = 4


@dataclass
class QualityResult:
    score: float  # 0-100
    parts: dict[str, float]  # "Sharpness", "Colour", "Artefacts", "Resolution"
    notes: list[str] = field(default_factory=list)


def _clip(v: float) -> float:
    return float(np.clip(v, 0, 100))


def _sharpness(ga, gb, area) -> float:
    la = cv2.Laplacian(ga, cv2.CV_32F)[area].var()
    lb = cv2.Laplacian(gb, cv2.CV_32F)[area].var()
    return _clip(100 * min(1.0, (lb + _EPS) / (la + _EPS)))


def _colour(a, b, area) -> float:
    la, lb = to_lab(a)[area], to_lab(b)[area]
    de = float(np.linalg.norm(la.mean(axis=0) - lb.mean(axis=0)))
    chroma = (np.hypot(lb[:, 1], lb[:, 2]).mean() + _EPS) / (np.hypot(la[:, 1], la[:, 2]).mean() + _EPS)
    contrast = (lb[:, 0].std() + _EPS) / (la[:, 0].std() + _EPS)
    return _clip(100 - 4 * de - 100 * abs(chroma - 1) - 100 * abs(contrast - 1))


def _noise(gray, flat, sigma) -> float:
    resid = gray - cv2.GaussianBlur(gray, (0, 0), sigma)
    return float(resid[flat].std()) if flat.any() else 0.0


def _blockiness(gray, area) -> float:
    dx = np.abs(np.diff(gray, axis=1))
    dy = np.abs(np.diff(gray, axis=0))
    ax, ay = area[:, :-1] & area[:, 1:], area[:-1] & area[1:]
    on_x = np.zeros(dx.shape, bool)
    on_x[:, 7::8] = True
    on_y = np.zeros(dy.shape, bool)
    on_y[7::8] = True
    ratios = []
    for d, a, on in ((dx, ax, on_x), (dy, ay, on_y)):
        grid, off = d[a & on], d[a & ~on]
        if grid.size and off.size:
            ratios.append((grid.mean() + _EPS) / (off.mean() + _EPS))
    return float(np.mean(ratios)) if ratios else 1.0


def _artefacts(ga, gb, area) -> float:
    sigma = 1.2 * max(ga.shape) / 1600
    gx = cv2.Sobel(ga, cv2.CV_32F, 1, 0)
    gy = cv2.Sobel(ga, cv2.CV_32F, 0, 1)
    mag = np.hypot(gx, gy)
    flat = area & (mag < np.percentile(mag[area], 40))
    noise = (_noise(gb, flat, sigma) + 0.5) / (_noise(ga, flat, sigma) + 0.5)
    # Only in flat areas, so real edges that happen to sit on the 8 px grid don't count.
    block = _blockiness(gb, flat) / _blockiness(ga, flat)
    # Blockiness ratios grow fast (a single q90 JPEG save is ~1.7x), so penalise on a log scale.
    return _clip(100 - 50 * max(0.0, noise - 1) - 25 * np.log2(max(1.0, block)))


def quality(reference, render, area=None, ref_pixels=0, render_pixels=0,
            ref_aspect=None, render_aspect=None) -> QualityResult:
    h, w = reference.shape[:2]
    inner = np.zeros((h, w), bool)
    inner[_BORDER:h - _BORDER, _BORDER:w - _BORDER] = True
    area = inner if area is None else (area.astype(bool) & inner)
    notes: list[str] = []

    if ref_pixels > 0 and render_pixels > 0:
        resolution = _clip(100 * min(1.0, render_pixels / ref_pixels) ** 0.5)
    else:
        resolution = 100.0
    if ref_aspect and render_aspect and abs(render_aspect / ref_aspect - 1) > 0.01:
        notes.append("Output size changed between steps.")

    if area.sum() < 500:
        notes.append("Almost everything was asked to change, so quality couldn't be measured.")
        parts = {"Sharpness": 100.0, "Colour": 100.0, "Artefacts": 100.0, "Resolution": resolution}
    else:
        ga = cv2.cvtColor(reference, cv2.COLOR_BGR2GRAY).astype(np.float32)
        gb = cv2.cvtColor(render, cv2.COLOR_BGR2GRAY).astype(np.float32)
        parts = {
            "Sharpness": _sharpness(ga, gb, area),
            "Colour": _colour(reference, render, area),
            "Artefacts": _artefacts(ga, gb, area),
            "Resolution": resolution,
        }
    return QualityResult(score=float(np.mean(list(parts.values()))), parts=parts, notes=notes)
