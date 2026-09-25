"""The full render check: fit, align, detect lines, compare, score, draw."""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from .align import align_edges, auto_align, fit_to_shape
from .compare import EdgeComparison, compare_edges
from .edges import detect_edges, params_for_original, params_for_render
from .imageio import fit_within
from .overlay import count_problem_areas, make_overlay
from .settings import Settings, score_level

# Keep only an alignment that improves the match by at least this much (F1, 0-1).
ALIGN_MIN_GAIN = 0.005


@dataclass
class CheckResult:
    score: float  # 0-100
    level: str  # good / ok / bad
    label: str  # plain-English verdict
    original: np.ndarray  # BGR, working size
    render: np.ndarray  # BGR, fitted and (if it helped) aligned to the original
    overlay: np.ndarray  # BGR, problem areas drawn on the render
    original_edges: np.ndarray
    render_edges: np.ndarray
    comparison: EdgeComparison
    aligned: bool
    missing_areas: int = 0  # separate places where model geometry is missing or moved
    added_areas: int = 0  # separate places where the AI added geometry
    notes: list[str] = field(default_factory=list)  # quiet, informational
    warnings: list[str] = field(default_factory=list)  # worth the user's attention

    @property
    def recall(self) -> float:
        return self.comparison.recall

    @property
    def precision(self) -> float:
        return self.comparison.precision

    @property
    def chamfer_px(self) -> float:
        return self.comparison.chamfer_px


def prepare_ignore_mask(mask: np.ndarray | None, shape_hw: tuple[int, int]) -> np.ndarray:
    """Resize a user-painted mask (any size, True/nonzero = ignore) to ``shape_hw``."""
    h, w = shape_hw
    if mask is None:
        return np.zeros((h, w), bool)
    m = (mask > 0).astype(np.uint8)
    if m.shape != (h, w):
        m = cv2.resize(m, (w, h), interpolation=cv2.INTER_NEAREST)
    return m > 0


def _scoring_area(valid: np.ndarray, ignored: np.ndarray) -> np.ndarray:
    # Shrink the valid area a little so the edge of padding or of a warped
    # image doesn't register as a line.
    margin = max(3, round(0.004 * max(valid.shape)))
    kernel = np.ones((2 * margin + 1, 2 * margin + 1), np.uint8)
    inner = cv2.erode(valid.astype(np.uint8), kernel, borderType=cv2.BORDER_CONSTANT, borderValue=1) > 0
    return inner & ~ignored


def check_render(
    original: np.ndarray,
    render: np.ndarray,
    settings: Settings | None = None,
    ignore_mask: np.ndarray | None = None,
) -> CheckResult:
    s = (settings or Settings()).validated()
    notes: list[str] = []
    warnings: list[str] = []

    original = fit_within(original, s.work_size)
    shape = original.shape[:2]
    ignored = prepare_ignore_mask(ignore_mask, shape)

    fitted = fit_to_shape(render, shape, s.fit_mode)
    if fitted.aspect_difference >= 0.01:
        how = {"crop": "trimmed", "pad": "padded", "stretch": "stretched"}[s.fit_mode]
        msg = f"The render is a different shape from your model view, so we {how} it to match."
        (warnings if fitted.aspect_difference > 0.15 else notes).append(msg)

    orig_edges = detect_edges(original, params_for_original(s.original_sensitivity))
    rend_params = params_for_render(s.render_sensitivity)

    rend_img, valid = fitted.image, fitted.valid
    rend_edges = detect_edges(rend_img, rend_params)
    comparison = compare_edges(orig_edges, rend_edges, s.match_tolerance_px, _scoring_area(valid, ignored))
    aligned = False

    if s.auto_align:
        attempts = [
            auto_align(original, fitted.image, fitted.valid),
            align_edges(orig_edges, rend_edges, fitted.image, fitted.valid),
        ]
        best = None
        for al in attempts:
            if not al.ok:
                continue
            a_edges = detect_edges(al.image, rend_params)
            a_cmp = compare_edges(orig_edges, a_edges, s.match_tolerance_px, _scoring_area(al.valid, ignored))
            if a_cmp.f1 > (best[2].f1 if best else comparison.f1 + ALIGN_MIN_GAIN):
                best = (al, a_edges, a_cmp)
        if best:
            al, rend_edges, comparison = best
            rend_img, valid, aligned = al.image, al.valid, True
            if al.displacement > 0.06:
                warnings.append(
                    "The render looks like it's from a slightly different camera angle. "
                    "We lined it up automatically, but it's worth a quick look."
                )
            else:
                notes.append("We nudged the render slightly to line it up with your model.")
        elif any(a.reason == "views too different" for a in attempts):
            warnings.append(
                "These two images look like they're from different camera angles. "
                "The score may not be fair. Try exporting the render from the same view."
            )
        elif not any(a.ok for a in attempts):
            notes.append("We couldn't line the images up automatically, so they were compared as they are.")

    if comparison.original_count == 0:
        warnings.append(
            "We couldn't find any lines in your model view (or it's all ignored). "
            "Try a view with visible edges, or ignore less of it."
        )

    score = round(100 * comparison.f1, 1)
    if not aligned and score < 35 and not any("camera" in w for w in warnings):
        warnings.append(
            "The images are very different. If they're from different camera angles, the score won't be meaningful."
        )
    level, label = score_level(score, s)

    shown_ignored = ignored | ~valid
    overlay = make_overlay(rend_img, comparison.missing, comparison.extra, shown_ignored)
    return CheckResult(
        score=score,
        level=level,
        label=label,
        original=original,
        render=rend_img,
        overlay=overlay,
        original_edges=orig_edges,
        render_edges=rend_edges,
        comparison=comparison,
        aligned=aligned,
        missing_areas=count_problem_areas(comparison.missing),
        added_areas=count_problem_areas(comparison.extra),
        notes=notes,
        warnings=warnings,
    )


def preview_edges(
    original: np.ndarray, render: np.ndarray, settings: Settings | None = None
) -> tuple[np.ndarray, np.ndarray]:
    """Edge maps for tuning sensitivity (render fitted to the original, not aligned)."""
    s = (settings or Settings()).validated()
    original = fit_within(original, s.work_size)
    fitted = fit_to_shape(render, original.shape[:2], s.fit_mode)
    return (
        detect_edges(original, params_for_original(s.original_sensitivity)),
        detect_edges(fitted.image, params_for_render(s.render_sensitivity)),
    )
