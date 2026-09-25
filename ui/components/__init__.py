"""Small self-contained browser components (plain HTML/JS, no build step)."""

from __future__ import annotations

import base64
import hashlib
import io
from pathlib import Path

import numpy as np
import streamlit as st
import streamlit.components.v1 as components
from PIL import Image

from core.imageio import encode_jpeg, fit_within

_HERE = Path(__file__).parent
_mask_painter = components.declare_component("mask_painter", path=str(_HERE / "mask_painter"))
_fader = components.declare_component("fader", path=str(_HERE / "fader"))


def data_url(bgr: np.ndarray, max_side: int = 1400) -> str:
    jpg = encode_jpeg(fit_within(bgr, max_side), quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(jpg).decode()


def image_key(*arrays: np.ndarray) -> str:
    h = hashlib.sha1()
    for a in arrays:
        h.update(str(a.shape).encode())
        h.update(a[::7, ::7].tobytes())
    return h.hexdigest()[:16]


def mask_painter(image: np.ndarray, key: str) -> np.ndarray | None:
    """Let the user brush over areas to ignore. Returns a boolean mask or None."""
    shown = fit_within(image, 1000)
    ikey = image_key(image)
    saved = st.session_state.get(f"{key}__saved") or {}
    strokes = saved.get("strokes") if saved.get("key") == ikey else None
    value = _mask_painter(image=data_url(shown, 1000), key=key, default=None, ikey=ikey, strokes=strokes)
    # ``key`` is reserved by Streamlit, so the image identity travels as
    # ``ikey``; the frontend echoes it back so stale masks are ignored.
    if value and value.get("key") == ikey:
        st.session_state[f"{key}__saved"] = value
    else:
        value = saved if saved.get("key") == ikey else None
    if not value or not value.get("mask"):
        return None
    raw = base64.b64decode(value["mask"].split(",", 1)[1])
    mask = np.asarray(Image.open(io.BytesIO(raw)).convert("L")) > 127
    return mask if mask.any() else None


def fader(original: np.ndarray, render: np.ndarray, key: str) -> None:
    """Fade between the original and the render, entirely in the browser."""
    _fader(original=data_url(original), render=data_url(render), key=key, default=None, ikey=image_key(original, render))
