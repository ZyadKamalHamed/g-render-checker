"""Screen 2: compare AI tools across several jobs (a bake-off)."""

from __future__ import annotations

import uuid
from datetime import datetime

import altair as alt
import pandas as pd
import streamlit as st

from core import check_render, score_level
from core.imageio import encode_png, fit_within, to_rgb
from core.report import ToolSummary, build_comparison_summary, to_png_bytes

from .common import legend, read_upload, tool_model_picker
from .settings_panel import current_settings, settings_panel

LEVEL_COLORS = {"good": "#1f9d55", "ok": "#d97706", "bad": "#dc2626"}


def _jobs() -> list[dict]:
    if "jobs" not in st.session_state:
        st.session_state.jobs = [{"id": uuid.uuid4().hex[:8], "n": 1}]
        st.session_state.job_count = 1
    return st.session_state.jobs


def _add_job() -> None:
    st.session_state.job_count += 1
    st.session_state.jobs.append({"id": uuid.uuid4().hex[:8], "n": st.session_state.job_count})


def _remove_job(job_id: str) -> None:
    st.session_state.jobs = [j for j in st.session_state.jobs if j["id"] != job_id]


def render() -> None:
    st.title("Compare AI tools", anchor=False)
    st.markdown(
        '<p class="rq-lede">Find out which AI tool keeps your geometry best. Add a few jobs: '
        "each job is one model view plus the renders different AI tools made from it.</p>",
        unsafe_allow_html=True,
    )

    tasks = []  # (job id, job name, original image, render file, tool)
    for i, job in enumerate(_jobs(), 1):
        tasks += _job_card(job, i)

    st.button("Add another job", icon=":material/add:", on_click=_add_job)

    st.write("")
    with st.container(key="rq-big-button"):
        run = st.button(
            f"Run all checks ({len(tasks)} render{'s' if len(tasks) != 1 else ''})" if tasks else "Run all checks",
            type="primary", width="stretch", disabled=not tasks,
        )
    if not tasks:
        st.caption("Add a model view and at least one render to a job to start.")

    if run:
        _run(tasks)

    rows = st.session_state.get("bake_rows")
    if rows:
        _results(rows)

    st.write("")
    preview = (tasks[0][2], read_upload(tasks[0][3])) if tasks else None
    settings_panel(preview, where="_compare")


def _job_card(job: dict, index: int) -> list:
    jid = job["id"]
    tasks = []
    with st.container(border=True):
        top_l, top_r = st.columns([5, 1], vertical_alignment="bottom")
        name = top_l.text_input("Job name", value=f"Job {job['n']}", key=f"j_{jid}_name").strip() or f"Job {index}"
        if len(st.session_state.jobs) > 1:
            top_r.button("Remove", key=f"j_{jid}_remove", on_click=_remove_job, args=(jid,),
                         type="tertiary", icon=":material/close:")

        left, right = st.columns([1, 2], gap="large")
        with left:
            orig_file = st.file_uploader("Original model view", key=f"j_{jid}_orig", help="PNG, JPG or WEBP")
            original = read_upload(orig_file)
            if original is not None:
                st.image(to_rgb(fit_within(original, 700)), width="stretch")
        with right:
            files = st.file_uploader("AI renders (one or more)", key=f"j_{jid}_rends", accept_multiple_files=True,
                                     help="Add the render each AI tool made from this model view.")
            for f in files or []:
                img = read_upload(f)
                if img is None:
                    continue
                c1, c2 = st.columns([1, 2], vertical_alignment="center")
                c1.image(to_rgb(fit_within(img, 400)), width="stretch")
                c2.caption(f"**{f.name}**")
                _, _, tool = tool_model_picker(f"j_{jid}_tool_{f.file_id}", f.name, c2)
                if original is not None:
                    tasks.append((jid, name, original, f, tool))
        if files and original is None:
            st.caption("Add the original model view for this job so its renders can be checked.")
    return tasks


def _run(tasks: list) -> None:
    settings = current_settings()
    bar = st.progress(0.0, text="Getting ready…")
    rows = []
    for k, (jid, job, original, f, tool) in enumerate(tasks):
        bar.progress(k / len(tasks), text=f"Checking {k + 1} of {len(tasks)}: {job}, {tool}")
        row = {"jid": jid, "job": job, "tool": tool, "file": f.name}
        try:
            r = check_render(original, read_upload(f), settings)
        except Exception:  # keep going; never show a traceback
            row.update(error="Couldn't check this one. Try exporting it again as PNG.")
        else:
            row.update(
                score=r.score, level=r.level, label=r.label, recall=r.recall, precision=r.precision,
                missing_areas=r.missing_areas, added_areas=r.added_areas, aligned=r.aligned,
                overlay=encode_png(fit_within(r.overlay, 1200)), warnings=r.warnings,
            )
        rows.append(row)
    bar.progress(1.0, text="All done")
    bar.empty()
    st.session_state.bake_rows = rows
    st.session_state.bake_time = datetime.now()


def _summaries(rows: list[dict]) -> list[ToolSummary]:
    settings = current_settings()
    ok = pd.DataFrame([r for r in rows if "score" in r])
    agg = ok.groupby("tool")["score"].agg(["mean", "count"]).sort_values("mean", ascending=False)
    return [ToolSummary(tool, float(m), int(c), score_level(m, settings)[0]) for tool, (m, c) in agg.iterrows()]


def _results(rows: list[dict]) -> None:
    st.divider()
    st.subheader("Leaderboard", anchor=False)
    for r in rows:
        if "error" in r:
            st.warning(f"**{r['job']}, {r['file']}**: {r['error']}")
    if not any("score" in r for r in rows):
        return

    tools = _summaries(rows)
    best = tools[0]
    if len(tools) > 1:
        st.markdown(f"**{best.tool}** kept your geometry best, averaging **{best.average:.0f}/100**.")
    else:
        st.markdown(f"Only **{best.tool}** was checked, averaging **{best.average:.0f}/100**. "
                    "Add renders from other tools to compare.")

    settings = current_settings()
    board = pd.DataFrame({
        "Rank": range(1, len(tools) + 1),
        "AI tool · model": [t.tool for t in tools],
        "Average score": [round(t.average, 1) for t in tools],
        "Renders checked": [t.count for t in tools],
        "Verdict": [score_level(t.average, settings)[1] for t in tools],
        "level": [t.level for t in tools],
    })
    chart = (
        alt.Chart(board)
        .mark_bar(cornerRadiusEnd=6, height=28)
        .encode(
            x=alt.X("Average score:Q", scale=alt.Scale(domain=[0, 100]), title=None),
            y=alt.Y("AI tool · model:N", sort=None, title=None, axis=alt.Axis(labelFontSize=14, labelLimit=260)),
            color=alt.Color("level:N", scale=alt.Scale(domain=list(LEVEL_COLORS), range=list(LEVEL_COLORS.values())),
                            legend=None),
            tooltip=["AI tool · model", "Average score", "Renders checked", "Verdict"],
        )
    )
    labels = chart.mark_text(align="left", dx=8, fontSize=14, fontWeight="bold", color="#1c1c1c").encode(
        text=alt.Text("Average score:Q", format=".0f"), color=alt.value("#1c1c1c"))
    st.altair_chart((chart + labels).properties(height=60 * len(tools) + 20), width="stretch")
    st.dataframe(
        board.drop(columns="level"), hide_index=True, width="stretch",
        column_config={"Average score": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f")},
    )

    st.subheader("Each job", anchor=False)
    st.caption("Open a job to see what each AI tool changed.")
    for jid in dict.fromkeys(r["jid"] for r in rows):
        items = [r for r in rows if r["jid"] == jid and "score" in r]
        if not items:
            continue
        top = max(items, key=lambda r: r["score"])
        with st.expander(f"{items[0]['job']}  ·  best: {top['tool']} ({top['score']:.0f})"):
            legend()
            for start in range(0, len(items), 3):
                cols = st.columns(3)
                for col, r in zip(cols, items[start : start + 3]):
                    col.image(r["overlay"], width="stretch")
                    col.markdown(f"**{r['tool']}**: {r['score']:.0f}/100, {r['label']}")
                    col.caption(r["file"])
                    for w in r["warnings"]:
                        col.caption(f"⚠ {w}")

    _exports(rows, tools)


def _exports(rows: list[dict], tools: list[ToolSummary]) -> None:
    when = st.session_state.get("bake_time", datetime.now())
    csv = pd.DataFrame([
        {
            "Job": r["job"], "AI tool · model": r["tool"], "Render file": r["file"],
            "Score (0-100)": r.get("score"), "Verdict": r.get("label", r.get("error")),
            "Model lines kept (%)": round(100 * r["recall"], 1) if "recall" in r else None,
            "New lines in render (%)": round(100 * (1 - r["precision"]), 1) if "precision" in r else None,
            "Areas missing or moved": r.get("missing_areas"), "Areas added": r.get("added_areas"),
            "Lined up automatically": ("Yes" if r["aligned"] else "No") if "aligned" in r else None,
        }
        for r in rows
    ]).to_csv(index=False).encode("utf-8-sig")  # BOM so Excel opens it cleanly

    table = []
    for jid in dict.fromkeys(r["jid"] for r in rows):
        scores: dict[str, list[float]] = {}
        for r in rows:
            if r["jid"] == jid and "score" in r:
                scores.setdefault(r["tool"], []).append(r["score"])
        name = next(r["job"] for r in rows if r["jid"] == jid)
        table.append((name, {t: sum(v) / len(v) for t, v in scores.items()}))
    png = to_png_bytes(build_comparison_summary(tools, table, when))

    st.write("")
    stamp = f"{when:%Y-%m-%d}"
    d1, d2, _ = st.columns([1.2, 1.2, 1.6])
    d1.download_button("Download summary (PNG)", png, f"ai-tool-comparison-{stamp}.png", "image/png",
                       type="primary", width="stretch", on_click="ignore")
    d2.download_button("Download results (CSV)", csv, f"ai-tool-comparison-{stamp}.csv", "text/csv",
                       width="stretch", on_click="ignore")
