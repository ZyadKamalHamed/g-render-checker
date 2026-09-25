"""Shared UI helpers: loading uploads, settings state, score display."""

from __future__ import annotations

import html
import re
import socket

import numpy as np
import streamlit as st

from core import AI_TOOLS, CheckResult, ImageLoadError, Settings, load_image, load_settings

EXPLANATIONS = {
    "good": "The render kept your model's geometry. Small differences are normal.",
    "ok": "Mostly faithful, but some things changed. Have a look at the highlighted areas.",
    "bad": "The AI changed the geometry noticeably. Check the highlighted areas before using this render.",
}

_TOOL_PATTERNS = [
    (r"leonardo", "Leonardo"),
    (r"gendo", "Gendo"),
    (r"veras", "Veras"),
    (r"vectorworks|visuali[sz]er|\bvw\b", "Vectorworks AI Visualizer"),
]


def guess_tool(filename: str) -> str | None:
    name = re.sub(r"[_\-.]+", " ", filename.lower())
    for pattern, tool in _TOOL_PATTERNS:
        if re.search(pattern, name):
            return tool
    return None


def tool_index(tool: str | None) -> int:
    return AI_TOOLS.index(tool) if tool in AI_TOOLS else AI_TOOLS.index("Other")


@st.cache_data(show_spinner=False, max_entries=64)
def _decode(data: bytes) -> np.ndarray:
    return load_image(data)


def read_upload(file) -> np.ndarray | None:
    """Decode an uploaded file, showing a friendly error if it isn't an image."""
    if file is None:
        return None
    try:
        return _decode(file.getvalue())
    except ImageLoadError as e:
        st.error(f"**{file.name}**: {e}")
    except MemoryError:
        st.error(f"**{file.name}**: That image is too big for this computer. Try exporting it smaller.")
    return None


def get_settings() -> Settings:
    if "settings" not in st.session_state:
        st.session_state.settings = load_settings()
    return st.session_state.settings


def step(number: int | str, text: str) -> None:
    st.markdown(f'<div class="rq-step"><span>{number}</span>{html.escape(text)}</div>', unsafe_allow_html=True)


def explanation(result: CheckResult) -> str:
    problems = result.missing_areas + result.added_areas
    if result.level == "good" and problems:
        return (f"Mostly accurate, but {problems} area{'s' if problems != 1 else ''} "
                f"look{'s' if problems == 1 else ''} different. Check the highlighted spots.")
    return EXPLANATIONS[result.level]


def score_card(result: CheckResult) -> None:
    st.markdown(
        f"""
        <div class="rq-score rq-{result.level}">
          <div class="rq-light"><i class="r"></i><i class="a"></i><i class="g"></i></div>
          <div>
            <div class="rq-num">{result.score:.0f}<span>/100</span></div>
            <div class="rq-label">{html.escape(result.label)}</div>
          </div>
          <p class="rq-explain">{explanation(result)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    facts = [
        f"{result.recall:.0%} of your model's lines are in the render",
        _areas(result.missing_areas, "missing or moved"),
        _areas(result.added_areas, "added by the AI"),
    ]
    st.markdown(
        '<div class="rq-facts">' + "".join(f'<span class="rq-fact">{html.escape(f)}</span>' for f in facts) + "</div>",
        unsafe_allow_html=True,
    )


def _areas(n: int, what: str) -> str:
    if n == 0:
        return f"No areas {what}"
    return f"{n} area{'s' if n != 1 else ''} {what}"


def legend() -> None:
    st.markdown(
        """
        <div class="rq-legend">
          <span><b style="background:#dc2626"></b>Missing or moved from your model</span>
          <span><b style="background:#2563eb"></b>Added by the AI</span>
          <span><b style="background:#cfcfcf"></b>Ignored</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def show_messages(result: CheckResult) -> None:
    for w in result.warnings:
        st.warning(w)
    for n in result.notes:
        st.caption(n)


def safe_filename(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower() or "render"


def _lan_address() -> str | None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))  # picks the office network interface; sends nothing
            ip = s.getsockname()[0]
        return None if ip.startswith("127.") else ip
    except OSError:
        return None


def footer() -> None:
    shared = st.get_option("server.address") in ("0.0.0.0", "::")
    ip = _lan_address() if shared else None
    if ip:
        link = f"http://{ip}:{st.get_option('server.port')}"
        text = (f"Shared on the office network. Others can open <b>{link}</b>. "
                "Images are checked on this computer and never go to the internet.")
    else:
        text = "Your images are checked on this computer and never go to the internet."
    st.markdown(f'<p class="rq-footer">{text}</p>', unsafe_allow_html=True)
