"""Prompt test, step 3: the models, their renders, ratings and guardrail outcomes."""

from __future__ import annotations

import numpy as np
import streamlit as st

from core.imageio import ImageLoadError, fit_within, to_rgb
from core.prompt_test import GUARDRAIL, OUTCOMES, ModelEntry, Prompt, assign_files, new_id, slot

from ..common import _decode, read_upload, step, tool_model_picker
from . import bump_nonce, nonce, state

IMAGE_TYPES = ["png", "jpg", "jpeg", "webp"]
NOT_RECORDED = "none"


@st.cache_data(show_spinner=False, max_entries=256)
def _thumb(data: bytes) -> np.ndarray | None:
    try:
        return to_rgb(fit_within(_decode(data), 300))
    except (ImageLoadError, MemoryError):
        return None


def _readable(data: bytes) -> bool:
    try:
        _decode(data)
        return True
    except (ImageLoadError, MemoryError):
        return False


# ---------------------------------------------------------------- callbacks

def _remove_model(model_id: str) -> None:
    t = state()
    t.models = [m for m in t.models if m.id != model_id]


def _clear_image(m: ModelEntry, pid: str) -> None:
    s = slot(m, pid)
    s.image, s.filename = None, ""


def _set_rating(m: ModelEntry, pid: str, key: str) -> None:
    v = st.session_state.get(key)
    slot(m, pid).rating = None if v is None else int(v) + 1


def _set_outcome(m: ModelEntry, pid: str, key: str) -> None:
    v = st.session_state.get(key)
    slot(m, pid).outcome = None if v == NOT_RECORDED else v


# ---------------------------------------------------------------- section

def render_models() -> None:
    t = state()
    step(3, "Models and renders")
    st.caption("Add each AI model you tried, then drop in its render for every prompt.")

    with st.form("pt_add_model", clear_on_submit=True, border=True):
        tool, model, label = tool_model_picker("pt_new")
        if st.form_submit_button("Add model", icon=":material/add:"):
            if any(m.label == label for m in t.models):
                st.info(f"{label} is already in this test.")
            else:
                t.models.append(ModelEntry(id=new_id(), tool=tool, model=model))

    if not t.models:
        st.info("No models yet. Add the first one above.")
        return

    for tab, m in zip(st.tabs([m.label for m in t.models]), t.models):
        with tab:
            _model_tab(t, m)


def _model_tab(t, m: ModelEntry) -> None:
    st.button("Remove this model", key=f"pt_rmm_{m.id}", on_click=_remove_model, args=(m.id,),
              type="tertiary", icon=":material/delete:")

    files = st.file_uploader("Drop all this model's renders at once", type=IMAGE_TYPES, accept_multiple_files=True,
                             key=f"pt_bulk_{m.id}_{nonce()}",
                             help="Files named like “p3” or “render_03” go to that prompt. "
                                  "The rest fill empty prompts in order.")
    if files:
        good = [(f.name, f.getvalue()) for f in files if _readable(f.getvalue())]
        lines = assign_files(t, m, good)
        lines += [f"{f.name} → not used (couldn't read this image)" for f in files if not _readable(f.getvalue())]
        st.session_state[f"pt_bulkmsg_{m.id}"] = lines
        bump_nonce()
        st.rerun()
    for line in st.session_state.get(f"pt_bulkmsg_{m.id}", []):
        st.caption(line)

    for n, p in enumerate(t.prompts, 1):
        with st.container(border=True):
            _slot_row(m, p, n)


def _slot_row(m: ModelEntry, p: Prompt, n: int) -> None:
    c1, c2, c3 = st.columns([0.6, 2.2, 1.6])
    c1.markdown(f"**{n}**")
    c1.caption(p.title + ("  ·  Guardrail" if p.kind == GUARDRAIL else ""))

    s = m.slots.get(p.id)
    with c2:
        if s is not None and s.image:
            thumb = _thumb(s.image)
            if thumb is None:
                st.warning("Couldn't read this image. Try exporting it again as PNG.")
            else:
                st.image(thumb, width=300)
            st.caption(s.filename or "Render")
            st.button("Remove", key=f"pt_clr_{m.id}_{p.id}", on_click=_clear_image, args=(m, p.id),
                      type="tertiary", icon=":material/close:")
        else:
            label = "Screenshot of the reply (optional)" if p.kind == GUARDRAIL else "Render"
            f = st.file_uploader(label, type=IMAGE_TYPES, key=f"pt_up_{m.id}_{p.id}_{nonce()}")
            if f is not None and read_upload(f) is not None:
                target = slot(m, p.id)
                target.image, target.filename = f.getvalue(), f.name
                bump_nonce()
                st.rerun()

    with c3:
        if p.kind == GUARDRAIL:
            key = f"pt_out_{m.id}_{p.id}"
            if key not in st.session_state:
                st.session_state[key] = (s.outcome if s and s.outcome in OUTCOMES else NOT_RECORDED)
            st.radio("What did it do?", [*OUTCOMES, NOT_RECORDED], key=key,
                     format_func=lambda o: OUTCOMES.get(o, "Not recorded"),
                     on_change=_set_outcome, args=(m, p.id, key),
                     help="A guardrail prompt should be refused.")
        else:
            key = f"pt_rate_{m.id}_{p.id}"
            if key not in st.session_state and s is not None and s.rating:
                st.session_state[key] = s.rating - 1
            st.caption("Your rating")
            st.feedback("stars", key=key, on_change=_set_rating, args=(m, p.id, key))
