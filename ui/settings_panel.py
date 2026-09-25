"""The "Advanced settings" expander. Normal users never need to open it."""

from __future__ import annotations

import numpy as np
import streamlit as st

from core import Settings, preview_edges, save_settings
from core.edges import edges_to_image
from core.imageio import to_rgb

from .common import get_settings

FIT_LABELS = {"crop": "Trim the edges", "pad": "Add borders", "stretch": "Stretch to fit"}

# widget key -> Settings field
_FIELDS = {
    "adv_orig": "original_sensitivity",
    "adv_rend": "render_sensitivity",
    "adv_tol": "match_tolerance_px",
    "adv_good": "good_threshold",
    "adv_ok": "ok_threshold",
    "adv_fit": "fit_mode",
    "adv_align": "auto_align",
    "adv_w_kept": "weight_kept",
    "adv_w_rating": "weight_rating",
    "adv_w_drift": "weight_drift",
    "adv_w_quality": "weight_quality",
}


def current_settings() -> Settings:
    """Settings as currently set in the panel (usable before the panel is drawn)."""
    if all(k in st.session_state for k in _FIELDS):
        return Settings(**{name: st.session_state[k] for k, name in _FIELDS.items()}).validated()
    return get_settings()


def _load_into_widgets(settings: Settings) -> None:
    for key, name in _FIELDS.items():
        st.session_state[key] = getattr(settings, name)


def _reset() -> None:
    st.session_state.settings = Settings()
    _load_into_widgets(Settings())
    st.session_state.pop("adv_preview", None)


def settings_panel(preview_pair: tuple[np.ndarray, np.ndarray] | None = None, where: str = "",
                   weights: bool = False) -> Settings:
    """Render the panel and return the current settings. ``weights`` adds the Prompt test weights."""
    current = get_settings()
    for key, name in _FIELDS.items():
        if key not in st.session_state:
            st.session_state[key] = getattr(current, name)

    with st.expander("Advanced settings"):
        st.caption("You shouldn't need these. They fine-tune how lines are picked out of each image.")
        c1, c2 = st.columns(2)
        with c1:
            st.slider("Line detail in the model view", 0, 100, key="adv_orig",
                      help="Higher picks up fainter lines in your SketchUp / Vectorworks view.")
            st.slider("Line detail in the render", 0, 100, key="adv_rend",
                      help="Keep this lower than the model view. Renders have lots of texture, "
                           "shadows and reflections that aren't geometry.")
            st.slider("How far a line can move and still match (pixels)", 1, 15, key="adv_tol",
                      help="Measured on the image scaled to 1600 pixels wide.")
        with c2:
            st.slider("Score needed for \"Accurate\"", 50, 100, key="adv_good")
            st.slider("Score needed for \"Check closely\"", 0, 100, key="adv_ok")
            st.radio("If the render is a different shape", list(FIT_LABELS), key="adv_fit",
                     format_func=FIT_LABELS.get, horizontal=True)
            st.toggle("Line the images up automatically", key="adv_align")

        if weights:
            st.markdown("**Prompt test weights**")
            st.caption("How much each part counts towards a model's overall score. "
                       "They're balanced automatically, so only their size relative to each other matters.")
            w1, w2 = st.columns(2)
            w1.slider("Kept (stayed the same where it should)", 0, 100, key="adv_w_kept")
            w1.slider("Your rating", 0, 100, key="adv_w_rating")
            w2.slider("Drift (stayed close to your model)", 0, 100, key="adv_w_drift")
            w2.slider("Quality (no degradation over edits)", 0, 100, key="adv_w_quality")

        settings = Settings(**{name: st.session_state[key] for key, name in _FIELDS.items()}).validated()
        st.session_state.settings = settings
        if settings.ok_threshold != st.session_state.adv_ok:
            st.caption(f"\"Check closely\" can't be higher than \"Accurate\", so it's using {settings.ok_threshold}.")

        b1, b2, b3 = st.columns(3)
        preview = b1.button("Preview detection", width="stretch", key=f"adv_preview_btn{where}")
        if b2.button("Save as default for everyone", width="stretch", key=f"adv_save{where}",
                     help="Saves these settings on this computer so they're used every time Render QA starts."):
            try:
                save_settings(settings)
                st.success("Saved. These settings will be used from now on.")
            except OSError:
                st.error("Couldn't save the settings file. Check that this folder isn't read-only.")
        b3.button("Reset to defaults", width="stretch", on_click=_reset, key=f"adv_reset{where}")

        if preview:
            st.session_state.adv_preview = True
        if st.session_state.get("adv_preview"):
            if preview_pair is None:
                st.info("Add a model view and a render first, then preview.")
            else:
                orig_e, rend_e = preview_edges(*preview_pair, settings)
                p1, p2 = st.columns(2)
                p1.image(to_rgb(edges_to_image(orig_e)), caption=f"Lines found in the model view ({int(orig_e.sum()):,} px)")
                p2.image(to_rgb(edges_to_image(rend_e)), caption=f"Lines found in the render ({int(rend_e.sum()):,} px)")
                st.caption(
                    "Aim for the render's lines to show walls, joinery and fixtures, but not wood grain, "
                    "tiles, shadows or reflections. The preview updates as you move the sliders."
                )
    return settings
