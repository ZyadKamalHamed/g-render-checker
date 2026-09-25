"""Prompt test, steps 1 and 2: the saved test, the model view and the prompts."""

from __future__ import annotations

import cv2
import numpy as np
import streamlit as st

from core.imageio import fit_within, to_rgb
from core.materials import swatch
from core.prompt_test import (
    EDIT, FROM_MODEL, FROM_PREVIOUS, GUARDRAIL, Prompt, chain_problems, move_prompt, new_id, prompt_number,
    remove_prompt, resolve_base,
)
from core.testfile import TestFileError, load_test, save_test

from ..common import read_upload, safe_filename, step
from ..components import image_key, mask_painter
from . import bump_nonce, model_view_image, nonce, regions, replace_test, state

IMAGE_TYPES = ["png", "jpg", "jpeg", "webp"]
KINDS = {"Edit": EDIT, "Guardrail": GUARDRAIL}


def _init(key: str, value) -> None:
    if key not in st.session_state:
        st.session_state[key] = value


# ---------------------------------------------------------------- header

def _set_name() -> None:
    state().name = st.session_state.pt_name.strip() or "Prompt test"


def render_header() -> None:
    t = state()
    if st.session_state.pop("ptest_toast", None):
        st.toast("Test opened", icon=":material/folder_open:")

    c1, c2 = st.columns([2, 1], vertical_alignment="bottom")
    with c1:
        f = st.file_uploader("Open a saved test", type=["rqtest"], key=f"pt_open_{nonce()}",
                             help="A .rqtest file you downloaded earlier.")
        if f is not None:
            try:
                opened = load_test(f.getvalue())
            except TestFileError as e:
                st.error(str(e))
            else:
                replace_test(opened)
                st.session_state.ptest_toast = True
                st.rerun()
    with c2:
        st.download_button("Download test", save_test(t), f"{safe_filename(t.name)}.rqtest", "application/zip",
                           on_click="ignore", icon=":material/download:", width="stretch")
    st.caption("Nothing is saved automatically. Download the test to keep it.")

    _init("pt_name", t.name)
    st.text_input("Test name", key="pt_name", on_change=_set_name)


# ---------------------------------------------------------------- model view

def render_model_view() -> None:
    t = state()
    step(1, "Add your model view")
    c1, c2 = st.columns([1, 1], gap="large")
    with c1:
        label = "Replace the model view" if t.model_view else "Model view"
        f = st.file_uploader(label, type=IMAGE_TYPES, key=f"pt_mv_{nonce()}",
                             help="The SketchUp / Vectorworks view the AI renders were made from.")
        if f is not None and read_upload(f) is not None:
            t.model_view, t.model_view_name = f.getvalue(), f.name
            st.session_state.pop("ptest_regions", None)
            bump_nonce()
            st.rerun()
    with c2:
        img = model_view_image()
        if img is not None:
            st.image(to_rgb(fit_within(img, 700)), width="stretch")
            st.caption(f"{t.model_view_name}. Add another file on the left to replace it; change zones are kept.")
        elif t.model_view:
            st.error("The saved model view couldn't be read. Add it again.")
        else:
            st.info("Add the model view first. Every render is compared with it.")


# ---------------------------------------------------------------- prompts

def _suffix(t, p: Prompt) -> str:
    if p.kind == GUARDRAIL:
        return "  ·  Guardrail"
    earlier = [q for q in t.prompts[: t.prompts.index(p)] if q.kind == EDIT]
    base = resolve_base(t, p)
    if not earlier:
        return ""
    if base == FROM_MODEL:
        return "  ·  from the model view"
    if base != earlier[-1].id:
        return f"  ·  from prompt {prompt_number(t, base)}"
    return ""


def _set(p: Prompt, attr: str, key: str, convert=lambda v: v) -> None:
    setattr(p, attr, convert(st.session_state[key]))


def _add_prompt() -> None:
    t = state()
    t.prompts.append(Prompt(id=new_id(), title=f"Prompt {len(t.prompts) + 1}"))


def render_prompts() -> None:
    t = state()
    step(2, "Your prompts")
    st.caption("Open a prompt to paste the exact wording, change where it starts from, or mark the area "
               "it was meant to change.")
    for problem in chain_problems(t):
        st.warning(problem)

    img = model_view_image()
    found = regions() if img is not None else []
    for n, p in enumerate(list(t.prompts), 1):
        with st.expander(f"{n}. {p.title}{_suffix(t, p)}", key=f"pt_exp_{p.id}"):
            _prompt_editor(t, p, n, img, found)

    st.button("Add prompt", icon=":material/add:", on_click=_add_prompt)


def _prompt_editor(t, p: Prompt, n: int, img, found) -> None:
    pid = p.id
    _init(f"pt_title_{pid}", p.title)
    _init(f"pt_text_{pid}", p.text)
    _init(f"pt_kind_{pid}", "Guardrail" if p.kind == GUARDRAIL else "Edit")

    st.text_input("Headline", key=f"pt_title_{pid}", on_change=_set,
                  args=(p, "title", f"pt_title_{pid}", lambda v: v.strip() or f"Prompt {n}"))
    st.text_area("Full prompt", key=f"pt_text_{pid}", placeholder="Paste the exact prompt you used",
                 on_change=_set, args=(p, "text", f"pt_text_{pid}"))
    c1, c2 = st.columns(2)
    c1.radio("Type", list(KINDS), key=f"pt_kind_{pid}", horizontal=True, on_change=_set,
             args=(p, "kind", f"pt_kind_{pid}", KINDS.get),
             help="Guardrail prompts should be refused; you record what each model did.")

    if p.kind == EDIT:
        earlier = [q for q in t.prompts[: t.prompts.index(p)] if q.kind == EDIT]
        options = [FROM_PREVIOUS, FROM_MODEL] + [q.id for q in earlier]
        names = {FROM_PREVIOUS: "Previous prompt", FROM_MODEL: "The model view"}
        names.update({q.id: f"Prompt {prompt_number(t, q.id)}: {q.title}" for q in earlier})
        key = f"pt_from_{pid}"
        if st.session_state.get(key) not in options:
            st.session_state[key] = p.starts_from if p.starts_from in options else FROM_PREVIOUS
        c2.selectbox("Starts from", options, key=key, format_func=names.get, on_change=_set,
                     args=(p, "starts_from", key),
                     help="Which image this prompt's render was made from.")

    b1, b2, b3, _ = st.columns([1, 1, 1, 3])
    b1.button("Move up", key=f"pt_up_{pid}", on_click=move_prompt, args=(t, pid, -1), disabled=n == 1,
              icon=":material/arrow_upward:")
    b2.button("Move down", key=f"pt_down_{pid}", on_click=move_prompt, args=(t, pid, 1),
              disabled=n == len(t.prompts), icon=":material/arrow_downward:")
    b3.button("Remove", key=f"pt_rm_{pid}", on_click=remove_prompt, args=(t, pid), type="tertiary",
              icon=":material/close:")

    if p.kind == EDIT and img is not None:
        _zone_editor(p, n, img, found)


def _zone_editor(p: Prompt, n: int, img: np.ndarray, found) -> None:
    pid = p.id
    on = st.toggle("Change zone", key=f"pt_zone_on_{pid}", value=p.zone is not None or bool(p.zone_materials),
                   help="The area this prompt asked the AI to change.")
    if not on:
        p.zone, p.zone_materials = None, []
        if n > 1:
            st.caption("No change zone, so everything counts as should-stay-the-same.")
        return

    st.caption("Paint where you asked the AI to change things. Everything else is judged on staying the same.")
    key = f"pt_zone_{pid}"
    mask = mask_painter(img, key=key, empty_text="Nothing painted yet",
                        painted_text="Painted area is the change zone")
    saved = st.session_state.get(f"{key}__saved") or {}
    if saved.get("key") == image_key(img):
        p.zone = mask  # the painter is in charge once it has been used on this image
    elif p.zone is not None:
        st.image(to_rgb(_zone_preview(img, p.zone)), width=360)
        st.caption("Saved zone. Paint to replace it.")

    if found:
        st.image([swatch(r) for r in found], caption=[f"M{r.id + 1}" for r in found], width=48)
        ids = [r.id for r in found]
        mkey = f"pt_mat_{pid}"
        _init(mkey, [i for i in p.zone_materials if i in ids])
        chosen = st.multiselect("Also include these materials", ids, format_func=lambda i: f"M{i + 1}", key=mkey,
                                help="Everything in these materials counts as inside the zone.")
        p.zone_materials = list(chosen)
    else:
        st.caption("No separate materials were found in this model view, so only the painted area counts.")


def _zone_preview(img: np.ndarray, zone: np.ndarray) -> np.ndarray:
    small = fit_within(img, 700)
    mask = cv2.resize(zone.astype(np.uint8), (small.shape[1], small.shape[0]), interpolation=cv2.INTER_NEAREST) > 0
    out = small.copy()
    out[mask] = (0.5 * out[mask] + 0.5 * np.array([11, 158, 245])).astype(np.uint8)
    return out
