"""Bringing the render into the same frame as the original.

1. ``fit_to_shape`` makes the render the same size as the original, handling a
   different aspect ratio by cropping, padding or stretching.
2. Two ways to line them up, both reporting failure rather than raising so the
   check can carry on unaligned:
   - ``auto_align``: ORB feature matching and a RANSAC homography. Good when
     both images have plenty of distinctive detail.
   - ``align_edges``: coarse-to-fine ECC on blurred line maps. Copes with
     heavily textured renders, where ORB latches onto wood grain and tiles.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class FitResult:
    image: np.ndarray
    valid: np.ndarray  # True where the pixel came from the render (not padding)
    aspect_difference: float  # 0 = same shape, 0.25 = 25% different


def aspect_difference(a_hw: tuple[int, int], b_hw: tuple[int, int]) -> float:
    ar_a = a_hw[1] / a_hw[0]
    ar_b = b_hw[1] / b_hw[0]
    return abs(ar_b / ar_a - 1.0)


def fit_to_shape(render: np.ndarray, target_hw: tuple[int, int], mode: str = "crop") -> FitResult:
    th, tw = target_hw
    rh, rw = render.shape[:2]
    diff = aspect_difference((th, tw), (rh, rw))
    valid = np.ones((th, tw), bool)

    if mode == "stretch" or diff < 0.01:
        img = cv2.resize(render, (tw, th), interpolation=_interp(rw, tw))
        return FitResult(img, valid, diff)

    if mode == "pad":
        scale = min(tw / rw, th / rh)
        nw, nh = max(1, round(rw * scale)), max(1, round(rh * scale))
        small = cv2.resize(render, (nw, nh), interpolation=_interp(rw, nw))
        img = np.full((th, tw, 3), 255, np.uint8)
        y0, x0 = (th - nh) // 2, (tw - nw) // 2
        img[y0 : y0 + nh, x0 : x0 + nw] = small
        valid[:] = False
        valid[y0 : y0 + nh, x0 : x0 + nw] = True
        return FitResult(img, valid, diff)

    # crop: scale to cover, then take the centre
    scale = max(tw / rw, th / rh)
    nw, nh = max(tw, round(rw * scale)), max(th, round(rh * scale))
    big = cv2.resize(render, (nw, nh), interpolation=_interp(rw, nw))
    y0, x0 = (nh - th) // 2, (nw - tw) // 2
    return FitResult(big[y0 : y0 + th, x0 : x0 + tw].copy(), valid, diff)


def _interp(src: int, dst: int) -> int:
    return cv2.INTER_AREA if dst < src else cv2.INTER_LINEAR


@dataclass
class AlignResult:
    ok: bool
    image: np.ndarray | None = None
    valid: np.ndarray | None = None
    homography: np.ndarray | None = None
    inliers: int = 0
    # Largest corner movement as a fraction of the image diagonal.
    displacement: float = 0.0
    reason: str = ""


MAX_PLAUSIBLE_DISPLACEMENT = 0.25


def auto_align(original: np.ndarray, render: np.ndarray, valid: np.ndarray | None = None) -> AlignResult:
    """Estimate a homography mapping ``render`` onto ``original`` (same size)."""
    h, w = original.shape[:2]
    g1 = _prep(original)
    g2 = _prep(render)

    orb = cv2.ORB_create(nfeatures=5000, scaleFactor=1.2, nlevels=8, fastThreshold=10)
    mask2 = valid.astype(np.uint8) * 255 if valid is not None else None
    k1, d1 = orb.detectAndCompute(g1, None)
    k2, d2 = orb.detectAndCompute(g2, mask2)
    if d1 is None or d2 is None or len(k1) < 20 or len(k2) < 20:
        return AlignResult(False, reason="not enough detail to match")

    matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
    pairs = matcher.knnMatch(d2, d1, k=2)
    good = [p[0] for p in pairs if len(p) == 2 and p[0].distance < 0.8 * p[1].distance]
    if len(good) < 15:
        return AlignResult(False, reason="too few matching points")

    src = np.float32([k2[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst = np.float32([k1[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    reproj = max(3.0, 0.004 * max(h, w))
    H, inlier_mask = cv2.findHomography(src, dst, cv2.RANSAC, reproj, maxIters=5000, confidence=0.995)
    if H is None or inlier_mask is None:
        return AlignResult(False, reason="no consistent match")
    inliers = int(inlier_mask.sum())
    if inliers < 15 or inliers / len(good) < 0.15:
        return AlignResult(False, inliers=inliers, reason="matches were not consistent")

    return _check_and_warp(H, render, valid, inliers)


def align_edges(
    original_edges: np.ndarray, render_edges: np.ndarray, render: np.ndarray, valid: np.ndarray | None = None
) -> AlignResult:
    """Line up two same-size line maps by maximising their overlap (ECC).

    Starts from "no movement", so it handles modest zooms, shifts and camera
    changes, not completely different views.
    """
    if original_edges.sum() < 50 or render_edges.sum() < 50:
        return AlignResult(False, reason="not enough detail to match")
    h, w = original_edges.shape
    criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-5)

    # Affine, coarse to fine. W maps original coordinates to render coordinates.
    W = np.eye(2, 3, dtype=np.float32)
    try:
        for scale, sigma in ECC_LEVELS:
            a, b = _soft(original_edges, scale, sigma), _soft(render_edges, scale, sigma)
            Ws = W.copy()
            Ws[:, 2] *= scale
            _, Ws = cv2.findTransformECC(a, b, Ws, cv2.MOTION_AFFINE, criteria, None, 5)
            W = Ws.copy()
            W[:, 2] /= scale
    except cv2.error:
        return AlignResult(False, reason="no consistent match")
    to_render = np.vstack([W, [0, 0, 1]]).astype(np.float32)

    # Refine with perspective at full size; keep the affine result if that fails.
    try:
        a, b = _soft(original_edges, 1.0, 2.0), _soft(render_edges, 1.0, 2.0)
        _, to_render = cv2.findTransformECC(a, b, to_render, cv2.MOTION_HOMOGRAPHY, criteria, None, 5)
    except cv2.error:
        pass
    try:
        H = np.linalg.inv(to_render.astype(np.float64))
    except np.linalg.LinAlgError:
        return AlignResult(False, reason="implausible shape")
    return _check_and_warp(H / H[2, 2], render, valid)


# (scale, blur sigma at full size) for each ECC pass
ECC_LEVELS = ((0.25, 12.0), (0.5, 6.0), (1.0, 3.0))


def _soft(edges: np.ndarray, scale: float, sigma: float) -> np.ndarray:
    img = cv2.GaussianBlur(edges.astype(np.float32), (0, 0), sigma)
    if scale != 1.0:
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    return img


def _check_and_warp(H: np.ndarray, render: np.ndarray, valid: np.ndarray | None, inliers: int = 0) -> AlignResult:
    """Reject implausible transforms, otherwise warp the render onto the original."""
    h, w = render.shape[:2]
    corners = np.float32([[0, 0], [w, 0], [w, h], [0, h]]).reshape(-1, 1, 2)
    moved = cv2.perspectiveTransform(corners, H)
    displacement = float(np.max(np.linalg.norm(moved - corners, axis=2)) / np.hypot(w, h))
    det = float(np.linalg.det(H[:2, :2]))
    if not (0.4 < det < 2.5) or not cv2.isContourConvex(moved.astype(np.float32)):
        return AlignResult(False, inliers=inliers, displacement=displacement, reason="implausible shape")
    if displacement > MAX_PLAUSIBLE_DISPLACEMENT:
        return AlignResult(False, inliers=inliers, displacement=displacement, reason="views too different")

    warped = cv2.warpPerspective(render, H, (w, h), flags=cv2.INTER_LINEAR, borderValue=(255, 255, 255))
    src_valid = valid.astype(np.uint8) if valid is not None else np.ones(render.shape[:2], np.uint8)
    warped_valid = cv2.warpPerspective(src_valid, H, (w, h), flags=cv2.INTER_NEAREST) > 0
    return AlignResult(True, warped, warped_valid, H, inliers, displacement)


def _prep(bgr: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    return cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
