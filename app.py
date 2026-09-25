"""Render QA: check how faithfully an AI render keeps your model's geometry.

Start it with the "Render QA" launcher, or: streamlit run app.py
"""

import streamlit as st

from ui import check_page, compare_page, prompt_test_page
from ui.common import footer
from ui.theme import apply_theme

st.set_page_config(page_title="Render QA", page_icon=":material/architecture:", layout="wide")
apply_theme()

page = st.navigation(
    [
        st.Page(check_page.render, title="Check a render", icon=":material/image_search:", url_path="check", default=True),
        st.Page(compare_page.render, title="Compare AI tools", icon=":material/leaderboard:", url_path="compare"),
        st.Page(prompt_test_page.render, title="Prompt test", icon=":material/science:", url_path="prompt-test"),
    ],
    position="top",
)
page.run()
footer()
