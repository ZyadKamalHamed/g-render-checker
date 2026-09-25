"""Loading and encoding images with friendly errors."""

from __future__ import annotations

import io

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

# Guard against absurd files (decompression bombs) while still allowing big renders.
Image.MAX_IMAGE_PIXELS = 200_000_000

ACCEPTED_TYPES = ["png", "jpg", "jpeg", "webp"]


class ImageLoadError(ValueError):
    """Raised with a message that is safe to show to a non-technical user."""


def load_image(data: bytes, max_side: int = 2500) -> np.ndarray:
    """Decode PNG/JPG/WEBP bytes into a BGR uint8 array, downscaled if very large."""
    if not data:
        raise ImageLoadError("That file is empty. Try exporting the image again.")
    try:
        with Image.open(io.BytesIO(data)) as im:
            im = ImageOps.exif_transpose(im)
            if im.mode in ("RGBA", "LA", "P"):
                # Put transparent areas on white, like a viewport background.
                im = im.convert("RGBA")
                bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
                im = Image.alpha_composite(bg, im)
            im = im.convert("RGB")
            if max(im.size) > max_side:
                im.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
            rgb = np.asarray(im, dtype=np.uint8)
    except Image.DecompressionBombError:
        raise ImageLoadError("That image is far too large to open. Try exporting it smaller.")
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
        raise ImageLoadError("That file doesn't look like an image, try a PNG or JPG.")
    if rgb.ndim != 3 or min(rgb.shape[:2]) < 32:
        raise ImageLoadError("That image is too small to check. Try a larger export.")
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def to_rgb(bgr: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


def encode_png(bgr: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", bgr)
    if not ok:
        raise RuntimeError("Could not encode image")
    return buf.tobytes()


def encode_jpeg(bgr: np.ndarray, quality: int = 88) -> bytes:
    ok, buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise RuntimeError("Could not encode image")
    return buf.tobytes()


def fit_within(bgr: np.ndarray, max_side: int) -> np.ndarray:
    h, w = bgr.shape[:2]
    scale = max_side / max(h, w)
    if scale >= 1:
        return bgr
    return cv2.resize(bgr, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)
