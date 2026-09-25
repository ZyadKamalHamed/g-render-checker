"""Shared state for the Prompt test screen.

The test lives in ``st.session_state.ptest``. Every widget key on this screen
starts with ``pt_`` so opening a saved test can wipe them in one go.
"""

from __future__ import annotations

import hashlib

import numpy as np
import streamlit as st

from core.imageio import ImageLoadError, fit_within
from core.materials import MaterialRegion, segment_materials
from core.prompt_test import PromptTest

from ..common import _decode
from ..settings_panel import current_settings


def state() -> PromptTest:
    if "ptest" not in st.session_state:
        st.session_state.ptest = PromptTest()
        st.session_state.ptest_nonce = 0
    return st.session_state.ptest


def nonce() -> int:
    return st.session_state.get("ptest_nonce", 0)


def bump_nonce() -> None:
    """Gives every uploader a fresh key, so it empties after its file has been taken."""
    st.session_state.ptest_nonce = nonce() + 1


def replace_test(test: PromptTest) -> None:
    for key in [k for k in st.session_state if isinstance(k, str) and k.startswith("pt_")]:
        del st.session_state[key]
    st.session_state.ptest = test
    st.session_state.pop("ptest_results", None)
    st.session_state.pop("ptest_regions", None)
    bump_nonce()


def model_view_image() -> np.ndarray | None:
    t = state()
    if not t.model_view:
        return None
    try:
        return _decode(t.model_view)
    except (ImageLoadError, MemoryError):
        return None


def regions() -> list[MaterialRegion]:
    """Materials found in the model view, at the size the checks run at (worked out once per image)."""
    t = state()
    img = model_view_image()
    if img is None:
        return []
    size = current_settings().work_size
    key = (hashlib.sha1(t.model_view).hexdigest(), size)
    memo = st.session_state.get("ptest_regions")
    if memo and memo[0] == key:
        return memo[1]
    found = segment_materials(fit_within(img, size))
    st.session_state.ptest_regions = (key, found)
    return found
