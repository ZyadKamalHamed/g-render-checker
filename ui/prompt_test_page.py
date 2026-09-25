"""Screen 3: run the same prompts through several AI models and compare them."""

from __future__ import annotations

import streamlit as st

from .prompt_test import renders, setup, state


def render() -> None:
    st.title("Prompt test", anchor=False)
    st.markdown(
        '<p class="rq-lede">Run the same prompts through several AI models and see which keeps your design, '
        "changes what you asked, and holds its quality.</p>",
        unsafe_allow_html=True,
    )
    state()
    setup.render_header()
    setup.render_model_view()
    setup.render_prompts()
    renders.render_models()
