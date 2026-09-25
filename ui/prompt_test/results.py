"""Prompt test, steps 4 and 5: the recommendation, the run, the results and the downloads."""

from __future__ import annotations

from datetime import datetime

import altair as alt
import pandas as pd
import streamlit as st

from core import score_level
from core.deck import build_deck
from core.imageio import ImageLoadError, load_image
from core.prompt_test import (
    GUARDRAIL, OUTCOMES, ModelSummary, PromptTest, TestResults, analysis_signature, edit_prompts, prompt_number,
    quality_series, run_test, summarise,
)

from ..common import legend, safe_filename, step
from ..compare_page import LEVEL_COLORS
from ..components import fader
from ..settings_panel import settings_panel
from . import model_view_image, state

PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


def _num(value: float | None) -> str:
    return "—" if value is None else f"{value:.0f}"


def _set_reco() -> None:
    state().recommendation = st.session_state.pt_reco.strip()


def _render_count(t: PromptTest) -> int:
    return sum(1 for m in t.models for p in edit_prompts(t) if p.id in m.slots and m.slots[p.id].image)


# ---------------------------------------------------------------- run

def render_run_and_results() -> None:
    t = state()
    step(4, "Your recommendation")
    if "pt_reco" not in st.session_state:
        st.session_state.pt_reco = t.recommendation
    st.text_area("Your recommendation (used in the exec report)", key="pt_reco", on_change=_set_reco,
                 placeholder="e.g. Use GPT 2.5 Flare for concept renders; avoid Nano Banana 2 for material swaps.")

    step(5, "Run the checks")
    mv = model_view_image()
    settings = settings_panel(None, where="_ptest", weights=True)
    n = _render_count(t)
    if st.button(f"Run all checks ({n} render{'s' if n != 1 else ''})", type="primary", width="stretch",
                 disabled=mv is None or n == 0, icon=":material/play_arrow:"):
        bar = st.progress(0.0, text="Starting…")
        try:
            st.session_state.ptest_results = run_test(
                t, settings, progress=lambda done, total, text: bar.progress(done / max(total, 1), text=text))
        except Exception:  # noqa: BLE001 - one friendly message instead of a traceback
            st.error("Something went wrong while checking. Try re-exporting the images as PNG and run again.")
        bar.empty()
    if mv is None:
        st.caption("Add the model view in step 1 first.")
    elif n == 0:
        st.caption("Add at least one render in step 3 first.")

    results: TestResults | None = st.session_state.get("ptest_results")
    if results is None:
        return
    if results.signature != analysis_signature(t, settings):
        st.info("Something changed since the last run. Press **Run all checks** to update.")

    summaries = summarise(t, results, settings)
    scored = [s for s in summaries if s.overall is not None]
    if not scored:
        st.warning("None of the renders could be checked. Check the messages in the grid below.")
    else:
        _headline(scored)
        _leaderboard(t, scored, settings)
        _quality_chart(t, results)
    _grid(t, results)
    _downloads(t, results, summaries)


# ---------------------------------------------------------------- results

def _headline(scored: list[ModelSummary]) -> None:
    best = scored[0]
    st.subheader("Results", anchor=False)
    st.markdown(f"**{best.label}** came out on top with **{best.overall:.0f}/100**.")
    caveats = []
    for s in scored:
        if s.ran < s.total_edit:
            caveats.append(f"{s.label}: {s.ran} of {s.total_edit} prompts")
        if s.ratings_missing:
            caveats.append(f"{s.label}: {s.ratings_missing} rating{'s' if s.ratings_missing != 1 else ''} missing")
    if caveats:
        st.caption(" · ".join(caveats))


def _guardrail_text(s: ModelSummary, has_guardrails: bool) -> str:
    if not has_guardrails:
        return "—"
    g = s.guardrails
    parts = [f"Refused {g['refused']}", f"Partly {g['partly']}", f"Complied {g['complied']}"]
    if g["not_recorded"]:
        parts.append(f"Not recorded {g['not_recorded']}")
    return " · ".join(parts)


def _notes(s: ModelSummary) -> str:
    notes = []
    if s.nothing_changed:
        notes.append(f"Ignored {s.nothing_changed} prompt{'s' if s.nothing_changed != 1 else ''}")
    if s.ratings_missing:
        notes.append(f"{s.ratings_missing} unrated")
    return ", ".join(notes)


def _leaderboard(t: PromptTest, scored: list[ModelSummary], settings) -> None:
    has_guardrails = any(p.kind == GUARDRAIL for p in t.prompts)
    board = pd.DataFrame({
        "Rank": range(1, len(scored) + 1),
        "AI tool · model": [s.label for s in scored],
        "Overall": [round(s.overall, 1) for s in scored],
        "Kept": [s.kept for s in scored],
        "Your rating": [s.rating for s in scored],
        "Drift": [s.drift for s in scored],
        "Quality": [s.quality for s in scored],
        "Guardrails": [_guardrail_text(s, has_guardrails) for s in scored],
        "Prompts run": [f"{s.ran} of {s.total_edit}" for s in scored],
        "Notes": [_notes(s) for s in scored],
        "level": [score_level(s.overall, settings)[0] for s in scored],
    })
    chart = (
        alt.Chart(board)
        .mark_bar(cornerRadiusEnd=6, height=28)
        .encode(
            x=alt.X("Overall:Q", scale=alt.Scale(domain=[0, 100]), title=None),
            y=alt.Y("AI tool · model:N", sort=None, title=None, axis=alt.Axis(labelFontSize=14, labelLimit=260)),
            color=alt.Color("level:N", scale=alt.Scale(domain=list(LEVEL_COLORS), range=list(LEVEL_COLORS.values())),
                            legend=None),
            tooltip=["AI tool · model", "Overall", "Prompts run"],
        )
    )
    labels = chart.mark_text(align="left", dx=8, fontSize=14, fontWeight="bold", color="#1c1c1c").encode(
        text=alt.Text("Overall:Q", format=".0f"), color=alt.value("#1c1c1c"))
    st.altair_chart((chart + labels).properties(height=60 * len(scored) + 20), width="stretch")
    progress = st.column_config.ProgressColumn
    st.dataframe(
        board.drop(columns="level"), hide_index=True, width="stretch",
        column_config={
            "Overall": progress(min_value=0, max_value=100, format="%.0f"),
            "Kept": progress(min_value=0, max_value=100, format="%.0f", help="Stayed the same where it should"),
            "Your rating": progress(min_value=0, max_value=100, format="%.0f", help="Your stars, out of 100"),
            "Drift": progress(min_value=0, max_value=100, format="%.0f", help="How close it stayed to your model"),
            "Quality": progress(min_value=0, max_value=100, format="%.0f", help="100 means no degradation"),
        },
    )


def _quality_chart(t: PromptTest, results: TestResults) -> None:
    rows = quality_series(t, results)
    if not rows:
        return
    st.subheader("Quality over edits", anchor=False)
    chart = (
        alt.Chart(pd.DataFrame(rows))
        .mark_line(point=True)
        .encode(
            x=alt.X("step:O", title="Edit number", axis=alt.Axis(labelAngle=0)),
            y=alt.Y("quality:Q", scale=alt.Scale(domain=[0, 105]), title="Quality"),
            color=alt.Color("label:N", title=None, legend=alt.Legend(orient="bottom", labelLimit=320, columns=2)),
            tooltip=["label", "prompt", alt.Tooltip("quality:Q", format=".0f")],
        )
        .properties(height=280)
    )
    st.altair_chart(chart, width="stretch")
    st.caption("Measured on the parts no prompt has touched yet. A flat line means no degradation.")


# ---------------------------------------------------------------- grid

def _grid(t: PromptTest, results: TestResults) -> None:
    if not t.models:
        return
    st.subheader("Prompt by prompt", anchor=False)
    st.caption("Red lines went missing or moved; blue lines were added by the AI.")
    per_row = min(4, len(t.models))
    for p in edit_prompts(t):
        st.markdown(f"**{prompt_number(t, p.id)}. {p.title}**")
        for start in range(0, len(t.models), per_row):
            cols = st.columns(per_row)
            for col, m in zip(cols, t.models[start:start + per_row]):
                with col:
                    _cell(t, results, m, p)


def _cell(t: PromptTest, results: TestResults, m, p) -> None:
    r = results.renders.get((m.id, p.id))
    if r is None:
        st.markdown(f"**{m.label}**")
        st.caption("Not run")
        return
    if r.error:
        st.markdown(f"**{m.label}**")
        st.warning(r.error)
        return
    st.image(r.overlay_png, width="stretch")
    st.markdown(f"**{m.label}**: Kept {_num(r.kept)} · Drift {_num(r.drift)} · Quality {_num(r.quality)}")
    s = m.slots.get(p.id)
    if s is not None and s.rating:
        st.markdown("★" * s.rating + "☆" * (5 - s.rating))
    for w in r.warnings:
        st.caption(f"⚠ {w}")
    if st.button("Details", key=f"pt_det_{m.id}_{p.id}", type="tertiary", icon=":material/zoom_in:"):
        st.session_state.pt_detail = (m.id, p.id)
        _detail_dialog()


def _decode(jpg: bytes):
    try:
        return load_image(jpg) if jpg else None
    except ImageLoadError:
        return None


@st.dialog("Details", width="large")
def _detail_dialog() -> None:
    t = state()
    results: TestResults | None = st.session_state.get("ptest_results")
    mid, pid = st.session_state.get("pt_detail", (None, None))
    r = results.renders.get((mid, pid)) if results else None
    m = next((m for m in t.models if m.id == mid), None)
    if r is None or m is None:
        st.info("This render is no longer in the test.")
        return
    st.markdown(f"**{m.label}** · Prompt {r.prompt_number}, compared with {r.base_label}")

    st.image(r.overlay_png, width="stretch")
    legend()
    if r.material_overlay_png:
        st.image(r.material_overlay_png, width="stretch")
        st.caption(f"Amber outlines: materials that changed outside the change zone. {r.material_summary}".strip())

    base, render = _decode(r.base_jpg), _decode(r.aligned_render_jpg)
    if base is not None and render is not None:
        st.caption(f"Drag to fade between {r.base_label} and this render.")
        fader(base, render, key=f"pt_fader_{mid}_{pid}")

    rows = [("Kept", _num(r.kept)), ("Lines kept", _num(r.lines)),
            ("Materials", r.material_summary or "—"),
            ("Changed in the zone", "—" if r.changed_fraction is None else f"{100 * r.changed_fraction:.0f}%"),
            ("Drift", _num(r.drift)), ("Quality", _num(r.quality))]
    rows += [(f"Quality · {k}", _num(v)) for k, v in (r.quality_parts or {}).items()]
    st.dataframe(pd.DataFrame(rows, columns=["Score", "Value"]), hide_index=True, width="stretch")
    for w in r.warnings:
        st.warning(w)
    for n in r.notes:
        st.caption(n)


# ---------------------------------------------------------------- downloads

def _csv(t: PromptTest, results: TestResults) -> bytes:
    part_names = list(dict.fromkeys(k for r in results.renders.values() for k in (r.quality_parts or {})))
    rows = []
    for m in t.models:
        for p in t.prompts:
            s = m.slots.get(p.id)
            r = results.renders.get((m.id, p.id))
            row = {"Model": m.label, "Prompt": f"{prompt_number(t, p.id)}. {p.title}"}
            ok = r is not None and r.error is None
            row.update({
                "Kept": round(r.kept, 1) if ok and r.kept is not None else None,
                "Lines": round(r.lines, 1) if ok and r.lines is not None else None,
                "Materials kept": r.material_summary if ok else None,
                "Changed %": round(100 * r.changed_fraction, 1) if ok and r.changed_fraction is not None else None,
                "Drift": round(r.drift, 1) if ok and r.drift is not None else None,
                "Quality": round(r.quality, 1) if ok and r.quality is not None else None,
            })
            for k in part_names:
                v = (r.quality_parts or {}).get(k) if ok else None
                row[f"Quality · {k}"] = round(v, 1) if v is not None else None
            row["Rating"] = s.rating if s else None
            row["Outcome"] = (OUTCOMES.get(s.outcome, "Not recorded") if s else "Not recorded") \
                if p.kind == GUARDRAIL else None
            if r is not None and r.error:
                row["Warnings"] = r.error
            else:
                row["Warnings"] = "; ".join(r.warnings) if r else ("" if p.kind == GUARDRAIL else "Not run")
            rows.append(row)
    df = pd.DataFrame(rows)
    df["Rating"] = df["Rating"].astype("Int64")  # whole stars, not 4.0
    return df.to_csv(index=False).encode("utf-8-sig")  # BOM so Excel opens it cleanly


def _downloads(t: PromptTest, results: TestResults, summaries: list[ModelSummary]) -> None:
    when = datetime.now()
    stamp = f"{when:%Y-%m-%d}"
    name = safe_filename(t.name)
    st.write("")
    d1, d2, _ = st.columns([1.5, 1.2, 1.3])
    # Built when clicked, so changing a rating doesn't rebuild the deck on every rerun.
    d1.download_button("Download exec report (PowerPoint)", lambda: build_deck(t, results, summaries, when),
                       f"{name}-report-{stamp}.pptx", PPTX, type="primary", width="stretch", on_click="ignore",
                       icon=":material/slideshow:")
    d2.download_button("Download results (CSV)", _csv(t, results), f"{name}-results-{stamp}.csv", "text/csv",
                       width="stretch", on_click="ignore", icon=":material/table:")
    st.caption("Download the test too if you might want to come back to it.")
