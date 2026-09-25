"""Tunable settings for the render check, with sensible defaults.

Defaults can be overridden by a ``settings.json`` file next to ``app.py``
(written by the "Save as default" button in Advanced settings).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path

SETTINGS_FILE = Path(__file__).resolve().parent.parent / "settings.json"

AI_TOOLS = ["Leonardo", "Gendo", "Veras", "Vectorworks AI Visualizer", "Other"]

FIT_MODES = ("crop", "pad", "stretch")


@dataclass(frozen=True)
class Settings:
    # Edge sensitivity, 0-100. Higher finds more (fainter) lines.
    original_sensitivity: int = 60
    render_sensitivity: int = 35
    # How far (in pixels) a line may drift and still count as "in the same place".
    match_tolerance_px: int = 4
    # Score thresholds for the traffic light.
    good_threshold: int = 85
    ok_threshold: int = 65
    # What to do when the render is a different shape from the original.
    fit_mode: str = "crop"
    # Try to line the render up with the original automatically.
    auto_align: bool = True
    # Longest side (px) images are analysed at. Keeps the tolerance meaningful
    # regardless of export size, and keeps things quick.
    work_size: int = 1600

    def validated(self) -> "Settings":
        good = int(min(max(self.good_threshold, 1), 100))
        ok = int(min(max(self.ok_threshold, 0), good))
        return replace(
            self,
            original_sensitivity=int(min(max(self.original_sensitivity, 0), 100)),
            render_sensitivity=int(min(max(self.render_sensitivity, 0), 100)),
            match_tolerance_px=int(min(max(self.match_tolerance_px, 1), 30)),
            good_threshold=good,
            ok_threshold=ok,
            fit_mode=self.fit_mode if self.fit_mode in FIT_MODES else "crop",
            work_size=int(min(max(self.work_size, 600), 2500)),
        )


def load_settings(path: Path = SETTINGS_FILE) -> Settings:
    """Load saved defaults, ignoring unknown keys or a broken file."""
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return Settings()
    known = {f.name for f in fields(Settings)}
    try:
        return Settings(**{k: v for k, v in data.items() if k in known}).validated()
    except TypeError:
        return Settings()


def save_settings(settings: Settings, path: Path = SETTINGS_FILE) -> None:
    path.write_text(json.dumps(asdict(settings.validated()), indent=2))


def score_level(score: float, settings: Settings) -> tuple[str, str]:
    """Return (level, plain-English label) for a 0-100 score."""
    if score >= settings.good_threshold:
        return "good", "Accurate"
    if score >= settings.ok_threshold:
        return "ok", "Check closely"
    return "bad", "Geometry changed a lot"
