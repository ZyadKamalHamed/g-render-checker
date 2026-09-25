"""Visual styling: calm, neutral, feels like a design tool rather than a dashboard."""

import streamlit as st

CSS = """
<style>
  /* Hide developer chrome */
  #MainMenu, footer, [data-testid="stStatusWidget"], [data-testid="stAppDeployButton"] { display: none !important; }
  [data-testid="stDecoration"] { display: none; }

  .block-container { max-width: 1200px; padding-top: 3.2rem; padding-bottom: 5rem; }
  h1 { font-weight: 700 !important; letter-spacing: -0.02em; }
  h2, h3 { letter-spacing: -0.01em; }
  .rq-lede { color: #6e6e73; font-size: 1.08rem; margin: -0.6rem 0 1.6rem; }
  .rq-step { font-weight: 600; font-size: 1.05rem; margin: 1.4rem 0 0.4rem; }
  .rq-step span { color: #a1a1aa; font-weight: 500; margin-right: .45rem; }

  /* Big friendly drop zones */
  [data-testid="stFileUploaderDropzone"] {
    min-height: 170px; border: 1.5px dashed #d4d4d8; border-radius: 14px; background: #fafafa;
    align-items: center; justify-content: center; transition: border-color .15s, background .15s;
  }
  [data-testid="stFileUploaderDropzone"] { flex-direction: column; gap: .6rem; }
  [data-testid="stFileUploaderDropzone"]::before {
    content: "Drag an image here"; font-size: 1.05rem; font-weight: 600; color: #3f3f46;
  }
  [class*="st-key-pt_open_"] [data-testid="stFileUploaderDropzone"]::before { content: "Drag a saved test here"; }
  [class*="st-key-pt_bulk_"] [data-testid="stFileUploaderDropzone"]::before { content: "Drag all the renders here"; }
  [class*="st-key-pt_up_"] [data-testid="stFileUploaderDropzone"] { min-height: 110px; }
  [data-testid="stFileUploaderDropzone"]:hover { border-color: #71717a; background: #f4f4f5; }
  [data-testid="stFileUploader"] label p { font-weight: 600; font-size: 1.02rem; }

  /* Primary button: large, solid ink */
  .stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"] {
    border-radius: 12px; font-weight: 600; font-size: 1.05rem; min-height: 3.1rem;
  }
  .stButton > button[kind="primary"] p, .stDownloadButton > button p { font-size: 1.02rem; font-weight: 600; }
  .st-key-rq-big-button button[kind="primary"] { min-height: 3.8rem; }
  .st-key-rq-big-button button[kind="primary"] p { font-size: 1.2rem; }
  .stButton > button, .stDownloadButton > button { border-radius: 10px; }
  .stDownloadButton > button { min-height: 3.1rem; }

  img { border-radius: 10px; }

  /* Score card */
  .rq-score { display: flex; align-items: center; gap: 1.6rem; padding: 1.6rem 1.8rem; border-radius: 16px;
              border: 1px solid #e4e4e7; background: #fff; margin: .4rem 0 1rem; }
  .rq-light { display: flex; flex-direction: column; gap: 6px; padding: 8px; background: #27272a; border-radius: 14px; }
  .rq-light i { width: 20px; height: 20px; border-radius: 50%; background: #52525b; display: block; }
  .rq-good .rq-light i.g { background: #22c55e; box-shadow: 0 0 12px #22c55e; }
  .rq-ok   .rq-light i.a { background: #f59e0b; box-shadow: 0 0 12px #f59e0b; }
  .rq-bad  .rq-light i.r { background: #ef4444; box-shadow: 0 0 12px #ef4444; }
  .rq-num { font-size: 4.2rem; font-weight: 700; line-height: 1; letter-spacing: -0.03em; color: #1c1c1c; }
  .rq-num span { font-size: 1.4rem; font-weight: 500; color: #a1a1aa; margin-left: .2rem; letter-spacing: 0; }
  .rq-label { font-size: 1.35rem; font-weight: 700; margin-top: .3rem; }
  .rq-good .rq-label { color: #15803d; } .rq-ok .rq-label { color: #b45309; } .rq-bad .rq-label { color: #b91c1c; }
  .rq-explain { color: #52525b; font-size: 1.02rem; max-width: 34rem; margin: 0; line-height: 1.5; }
  .rq-facts { display: flex; flex-wrap: wrap; gap: .5rem; margin: 0 0 1.2rem; }
  .rq-fact { background: #f4f4f5; border-radius: 999px; padding: .35rem .85rem; font-size: .95rem; color: #3f3f46; }

  /* Legend */
  .rq-legend { display: flex; flex-wrap: wrap; gap: 1.1rem; margin: .5rem 0 0; font-size: .95rem; color: #3f3f46; }
  .rq-legend b { display: inline-block; width: 14px; height: 14px; border-radius: 4px; margin-right: .45rem; vertical-align: -2px; }

  .rq-footer { color: #a1a1aa; font-size: .88rem; margin-top: 3rem; text-align: center; }
  .rq-footer b { color: #52525b; font-weight: 600; user-select: all; }
  .rq-muted { color: #71717a; font-size: .92rem; }
  [data-testid="stExpander"] details { border-radius: 12px; }
</style>
"""


def apply_theme() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
