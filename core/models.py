"""Tool and model names: display labels, remembered model names, filename guessing.

Only model *names* are saved (in models.json next to settings.json), never images.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .settings import SETTINGS_FILE

MODELS_FILE = SETTINGS_FILE.with_name("models.json")
DEFAULT_MODELS = ["GPT 2.5 Flare", "GPT 2.5 Sunburst", "Nano Banana Pro", "Nano Banana 2"]


def label(tool: str, model: str | None) -> str:
    """How a tool + model pair is shown everywhere, e.g. "Leonardo · Nano Banana Pro"."""
    tool, model = (tool or "").strip(), (model or "").strip()
    return f"{tool} · {model}" if model else tool


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def known_models(path: Path = MODELS_FILE) -> list[str]:
    """The default suggestions plus any names typed in before (ignoring a broken file)."""
    names = list(DEFAULT_MODELS)
    try:
        saved = json.loads(path.read_text())
    except (OSError, ValueError):
        saved = []
    seen = {_norm(n) for n in names}
    for n in saved if isinstance(saved, list) else []:
        if isinstance(n, str) and n.strip() and _norm(n) not in seen:
            names.append(n.strip())
            seen.add(_norm(n))
    return names


def remember_model(name: str, path: Path = MODELS_FILE) -> None:
    """Add a new model name to the suggestions. Never raises."""
    name = (name or "").strip()
    known = known_models(path)
    if not name or _norm(name) in {_norm(n) for n in known}:
        return
    extra = [n for n in known if n not in DEFAULT_MODELS] + [name]
    try:
        path.write_text(json.dumps(extra, indent=2))
    except OSError:
        pass


def guess_model(filename: str, known: list[str]) -> str | None:
    """The longest known model name found in a file name, ignoring case and punctuation."""
    target = _norm(filename)
    hits = [n for n in known if _norm(n) and _norm(n) in target]
    return max(hits, key=lambda n: len(_norm(n))) if hits else None
