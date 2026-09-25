"""Prompt test screen, driven headlessly with Streamlit's AppTest."""

import numpy as np
from streamlit.testing.v1 import AppTest

from tests.synthetic import png_bytes
from tests.test_prompt_test import _chain_test

REPORTS = ("Download exec report (PowerPoint)", "Download results (CSV)")


def _page():
    from ui.prompt_test_page import render
    render()


def _app():
    at = AppTest.from_function(_page, default_timeout=180)
    at.session_state["ptest"] = _chain_test()
    return at.run()


def _downloads(at):
    return {d.proto.label: d.proto for d in at.get("download_button")}


def test_report_downloads_are_disabled_while_results_are_stale():
    at = _app()
    next(b for b in at.button if b.label.startswith("Run all checks")).click().run()
    assert not any(_downloads(at)[k].disabled for k in REPORTS)

    at.session_state["ptest"].models[0].slots["p1"].rating = 2  # ratings don't need a re-run
    at.run()
    assert not at.info and not any(_downloads(at)[k].disabled for k in REPORTS)

    t = at.session_state["ptest"]
    t.models[0].slots["p3"].image = png_bytes(np.full((200, 300, 3), 128, np.uint8))  # a different render, not re-run yet
    at.run()
    assert any("Something changed" in i.value for i in at.info)
    assert all(_downloads(at)[k].disabled for k in REPORTS)


def test_saved_test_is_only_built_when_downloaded():
    """Zipping every image on each rerun is slow with real renders, so it's deferred to the click."""
    d = _downloads(_app())["Download test"]
    assert d.url == "" and d.deferred_file_id
