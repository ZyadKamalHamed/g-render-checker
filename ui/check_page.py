"""Screen 1: check a single render against its model view."""

from __future__ import annotations

import hashlib
from datetime import datetime

import streamlit as st

from core import check_render
from core.imageio import fit_within, to_rgb
from core.report import build_report, to_pdf_bytes, to_png_bytes

from .common import (
    legend, read_upload, safe_filename, score_card, show_messages, step, tool_model_picker,
)
from .components import fader, mask_painter
from .settings_panel import current_settings, settings_panel

UPLOAD_HELP = "PNG, JPG or WEBP"


def _signature(*parts) -> str:
    h = hashlib.sha1()
    for p in parts:
        h.update(p if isinstance(p, bytes) else repr(p).encode())
    return h.hexdigest()


def render() -> None:
    st.title("Check a render", anchor=False)
    st.markdown(
        '<p class="rq-lede">See how faithfully an AI render kept the geometry of your model view.</p>',
        unsafe_allow_html=True,
    )

    step(1, "Add your two images")
    c1, c2 = st.columns(2, gap="large")
    with c1:
        orig_file = st.file_uploader("Original model view", key="c_orig", help=UPLOAD_HELP)
        original = read_upload(orig_file)
        if original is not None:
            st.image(to_rgb(fit_within(original, 900)), width="stretch")
    with c2:
        rend_file = st.file_uploader("AI render", key="c_rend", help=UPLOAD_HELP)
        render_img = read_upload(rend_file)
        if render_img is not None:
            st.image(to_rgb(fit_within(render_img, 900)), width="stretch")

    step(2, "Which AI tool and model made this?")
    tool_key = f"c_tool_{rend_file.file_id}" if rend_file else "c_tool"
    _, _, tool = tool_model_picker(tool_key, rend_file.name if rend_file else None)

    step(3, "Ignore areas (optional)")
    mask = None
    if st.toggle("Skip some areas", key="c_ignore_on"):
        st.caption("Paint over areas you don't care about, like floors and walls.")
        if original is None:
            st.info("Add your model view first, then paint on it here.")
        else:
            mask = mask_painter(original, key="c_mask")

    st.write("")
    ready = original is not None and render_img is not None
    settings = current_settings()
    with st.container(key="rq-big-button"):
        clicked = st.button("Check render", type="primary", width="stretch", disabled=not ready)
    if not ready:
        st.caption("Add both images to start.")

    sig = None
    if ready:
        sig = _signature(
            orig_file.getvalue(), rend_file.getvalue(),
            mask.tobytes() if mask is not None else b"", mask.shape if mask is not None else None,
            settings,
        )
    if clicked and ready:
        with st.spinner("Checking your render…"):
            try:
                result = check_render(original, render_img, settings, mask)
            except Exception:  # never show a traceback to designers
                st.error("Something went wrong while checking these images. Try exporting them again as PNG.")
                result = None
        if result is not None:
            st.session_state.c_result = {"sig": sig, "result": result}
            st.session_state.pop("c_report", None)

    saved = st.session_state.get("c_result")
    if saved and ready:
        _results(saved, tool, rend_file.name, stale=saved["sig"] != sig)

    st.write("")
    settings_panel((original, render_img) if ready else None, where="_check")


def _results(saved: dict, tool: str, render_name: str, stale: bool) -> None:
    result = saved["result"]
    st.divider()
    st.subheader("Result", anchor=False)
    if stale:
        st.info("Something changed since this check. Press **Check render** to update the result.")
    score_card(result)
    show_messages(result)

    left, right = st.columns(2, gap="large")
    with left:
        st.markdown("**What changed**")
        st.image(to_rgb(result.overlay), width="stretch")
        legend()
    with right:
        st.markdown("**Fade between your model and the render**")
        fader(result.original, result.render, key="c_fader")

    st.write("")
    report_key = (saved["sig"], tool)
    cached = st.session_state.get("c_report")
    if not cached or cached["key"] != report_key:
        page = build_report(result, tool, job_name=render_name, when=datetime.now())
        cached = {"key": report_key, "pdf": to_pdf_bytes(page), "png": to_png_bytes(page)}
        st.session_state.c_report = cached

    base = f"render-check-{safe_filename(tool)}-{datetime.now():%Y-%m-%d}"
    d1, d2, _ = st.columns([1.2, 1.2, 1.6])
    d1.download_button("Download report (PDF)", cached["pdf"], f"{base}.pdf", "application/pdf",
                       type="primary", width="stretch", on_click="ignore")
    d2.download_button("Download as image (PNG)", cached["png"], f"{base}.png", "image/png",
                       width="stretch", on_click="ignore")
