"""Synthetic viewport-like scenes for testing the core logic."""

from __future__ import annotations

import cv2
import numpy as np

W, H = 1200, 800

# (x0, y0, x1, y1, fill BGR)
BASE_BOXES = [
    (80, 120, 380, 700, (200, 190, 175)),  # tall shelving unit
    (470, 420, 900, 700, (180, 200, 215)),  # counter
    (960, 200, 1120, 520, (170, 170, 200)),  # display fixture
    (520, 120, 760, 300, (210, 215, 200)),  # wall panel
]

# The box used for "removed" / "added" tests, in an otherwise empty area.
FEATURE_BOX = (880, 580, 1100, 740)


def draw_scene(boxes=BASE_BOXES, extra_boxes=(), shift=(0, 0), size=(W, H)) -> np.ndarray:
    w, h = size
    img = np.full((h, w, 3), 236, np.uint8)
    cv2.line(img, (0, 720), (w, 720), (120, 120, 120), 2)  # floor line
    dx, dy = shift
    for x0, y0, x1, y1, fill in list(boxes) + list(extra_boxes):
        p0, p1 = (x0 + dx, y0 + dy), (x1 + dx, y1 + dy)
        cv2.rectangle(img, p0, p1, fill, -1)
        cv2.rectangle(img, p0, p1, (40, 40, 40), 2)
    # Shelves inside the shelving unit, and some joinery detail for texture.
    for y in range(200, 700, 80):
        cv2.line(img, (80 + dx, y + dy), (380 + dx, y + dy), (40, 40, 40), 2)
    for x in range(520, 900, 95):
        cv2.line(img, (x + dx, 420 + dy), (x + dx, 700 + dy), (60, 60, 60), 2)
    cv2.circle(img, (1040 + dx, 360 + dy), 50, (40, 40, 40), 2)
    cv2.putText(img, "A1", (560 + dx, 220 + dy), cv2.FONT_HERSHEY_SIMPLEX, 2.0, (40, 40, 40), 3)
    return img


def box(fill=(150, 170, 200)):
    return (*FEATURE_BOX, fill)


def photoreal_like(img: np.ndarray, seed: int = 0) -> np.ndarray:
    """Add texture, shading and noise so it looks more like an AI render."""
    rng = np.random.default_rng(seed)
    h, w = img.shape[:2]
    out = img.astype(np.float32)
    yy, xx = np.mgrid[0:h, 0:w]
    shading = 0.85 + 0.25 * (xx / w) - 0.1 * (yy / h)
    out *= shading[..., None]
    grain = cv2.GaussianBlur(rng.normal(0, 14, (h, w)).astype(np.float32), (0, 0), 1.5)
    out += grain[..., None]
    out += rng.normal(0, 3, out.shape)
    out = cv2.GaussianBlur(out, (3, 3), 0)
    return np.clip(out, 0, 255).astype(np.uint8)


def region_mask(shape_hw, rect, pad=10) -> np.ndarray:
    x0, y0, x1, y1 = rect
    m = np.zeros(shape_hw, bool)
    m[max(0, y0 - pad) : y1 + pad, max(0, x0 - pad) : x1 + pad] = True
    return m


def harsh_photoreal(img: np.ndarray, seed: int = 0) -> np.ndarray:
    """A tougher render imitation: wood grain, blotchy shadows, specular speckle."""
    rng = np.random.default_rng(seed)
    h, w = img.shape[:2]
    out = photoreal_like(img, seed).astype(np.float32)
    yy, xx = np.mgrid[0:h, 0:w]
    grain = 10 * np.sin(yy / 3.0 + 4 * np.sin(xx / 60.0)) + 6 * np.sin(xx / 7.0)
    out += grain[..., None]
    blotch = cv2.GaussianBlur(rng.normal(0, 1, (h // 20 + 1, w // 20 + 1)).astype(np.float32), (0, 0), 1)
    blotch = cv2.resize(blotch, (w, h), interpolation=cv2.INTER_CUBIC)
    out *= (1 + 0.12 * blotch)[..., None]
    speck = rng.random((h, w)) > 0.997
    out[speck] = 255
    return np.clip(out, 0, 255).astype(np.uint8)


# Distinct flat materials for the material and prompt-test tests. (x0, y0, x1, y1, fill BGR)
MATERIAL_BOXES = [
    (60, 100, 360, 700, (40, 90, 150)),  # dark timber
    (420, 420, 820, 700, (200, 200, 195)),  # pale terrazzo
    (880, 160, 1140, 520, (150, 110, 40)),  # blue-grey metal
    (460, 110, 780, 330, (60, 160, 90)),  # green laminate
]


def material_rect(i: int) -> tuple[int, int, int, int]:
    return MATERIAL_BOXES[i][:4]


def material_scene(fills: dict | None = None, split: int | None = None, size=(W, H)) -> np.ndarray:
    """Flat-colour 'SketchUp' view. ``fills`` overrides box colours; ``split`` paints the
    right half of that box a very different colour (one material becomes two)."""
    w, h = size
    img = np.full((h, w, 3), 245, np.uint8)
    cv2.line(img, (0, 720), (w, 720), (120, 120, 120), 2)
    for i, (x0, y0, x1, y1, fill) in enumerate(MATERIAL_BOXES):
        fill = (fills or {}).get(i, fill)
        cv2.rectangle(img, (x0, y0), (x1, y1), fill, -1)
        if split == i:
            cv2.rectangle(img, ((x0 + x1) // 2, y0), (x1, y1), (230, 60, 200), -1)
        cv2.rectangle(img, (x0, y0), (x1, y1), (30, 30, 30), 2)
    for y in range(180, 700, 90):
        cv2.line(img, (60, y), (360, y), (30, 30, 30), 2)
    return img


def shift_colour(img: np.ndarray, bgr_delta) -> np.ndarray:
    return np.clip(img.astype(np.int16) + np.array(bgr_delta, np.int16), 0, 255).astype(np.uint8)


def png_bytes(img: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return buf.tobytes()
