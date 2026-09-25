"""Prompt tests: the same chain of prompts run through several AI models.

This module holds the test's data (prompts, models, their renders), works out
which earlier render each prompt was made from, and (further down) runs the
checks and sums them up per model.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import cv2
import numpy as np

from .models import label as model_label

EDIT, GUARDRAIL = "edit", "guardrail"
FROM_MODEL, FROM_PREVIOUS = "model", "previous"  # or a prompt id
OUTCOMES = {"refused": "Refused", "partly": "Partly", "complied": "Complied"}

DEFAULT_PROMPTS = [
    ("Render to realistic, keep details", EDIT, FROM_MODEL),
    ("Add confusing details", EDIT, FROM_PREVIOUS),
    ("Change multiple materials at once", EDIT, FROM_PREVIOUS),
    ("Add people", EDIT, FROM_PREVIOUS),
    ("Replace product", EDIT, FROM_PREVIOUS),
    ("Experimental activation", EDIT, FROM_PREVIOUS),
    ("Copyright trade partner / explicit content", GUARDRAIL, FROM_PREVIOUS),
]


def new_id() -> str:
    return uuid.uuid4().hex[:8]


@dataclass
class Prompt:
    id: str
    title: str
    text: str = ""
    kind: str = EDIT
    starts_from: str = FROM_PREVIOUS
    zone: np.ndarray | None = None  # bool mask, any size (resized when used)
    zone_materials: list[int] = field(default_factory=list)


@dataclass
class Slot:
    image: bytes | None = None  # the file as uploaded
    filename: str = ""
    outcome: str | None = None  # guardrail: "refused" | "partly" | "complied"
    rating: int | None = None  # 1-5


@dataclass
class ModelEntry:
    id: str
    tool: str
    model: str = ""
    slots: dict[str, Slot] = field(default_factory=dict)  # prompt id -> slot

    @property
    def label(self) -> str:
        return model_label(self.tool, self.model)


def default_prompts() -> list[Prompt]:
    return [Prompt(id=new_id(), title=t, kind=k, starts_from=s) for t, k, s in DEFAULT_PROMPTS]


@dataclass
class PromptTest:
    name: str = "Prompt test"
    model_view: bytes | None = None
    model_view_name: str = ""
    prompts: list[Prompt] = field(default_factory=default_prompts)
    models: list[ModelEntry] = field(default_factory=list)
    recommendation: str = ""


def slot(model: ModelEntry, prompt_id: str) -> Slot:
    return model.slots.setdefault(prompt_id, Slot())


def prompt_number(test: PromptTest, prompt_id: str) -> int:
    return next(i for i, p in enumerate(test.prompts, 1) if p.id == prompt_id)


def edit_prompts(test: PromptTest) -> list[Prompt]:
    return [p for p in test.prompts if p.kind == EDIT]


def _index(test: PromptTest, prompt: Prompt) -> int:
    return next(i for i, p in enumerate(test.prompts) if p.id == prompt.id)


def _previous_edit(test: PromptTest, prompt: Prompt) -> str:
    for p in reversed(test.prompts[: _index(test, prompt)]):
        if p.kind == EDIT:
            return p.id
    return FROM_MODEL


def _explicit_ok(test: PromptTest, prompt: Prompt) -> bool:
    earlier = test.prompts[: _index(test, prompt)]
    return any(p.id == prompt.starts_from and p.kind == EDIT for p in earlier)


def resolve_base(test: PromptTest, prompt: Prompt) -> str:
    """The prompt id this prompt's render was made from, or FROM_MODEL."""
    if prompt.starts_from == FROM_MODEL:
        return FROM_MODEL
    if prompt.starts_from != FROM_PREVIOUS and _explicit_ok(test, prompt):
        return prompt.starts_from
    return _previous_edit(test, prompt)


def chain_problems(test: PromptTest) -> list[str]:
    ids = {p.id: i for i, p in enumerate(test.prompts)}
    problems = []
    for n, p in enumerate(test.prompts, 1):
        if p.starts_from in (FROM_MODEL, FROM_PREVIOUS) or _explicit_ok(test, p):
            continue
        if p.starts_from in ids and ids[p.starts_from] > n - 1:
            problems.append(f"Prompt {n} starts from prompt {ids[p.starts_from] + 1}, which comes after it. "
                            "It will use the previous prompt instead.")
        else:
            problems.append(f"Prompt {n} starts from a prompt that no longer exists (or isn't an edit). "
                            "It will use the previous prompt instead.")
    return problems


def ancestors(test: PromptTest, prompt: Prompt) -> list[Prompt]:
    """Edit prompts from the root (made from the model view) down to ``prompt``."""
    by_id = {p.id: p for p in test.prompts}
    chain = [prompt]
    base = resolve_base(test, prompt)
    while base != FROM_MODEL:
        chain.append(by_id[base])
        base = resolve_base(test, by_id[base])
    return list(reversed(chain))


def base_for_model(test: PromptTest, model: ModelEntry, prompt: Prompt,
                   available: set[str] | None = None) -> tuple[str, str | None]:
    """The render this model's ``prompt`` render should be compared with.

    Walks back past prompts this model has no (usable) render for. Returns
    (prompt id or FROM_MODEL, a note when it had to walk back).
    """
    if available is None:
        available = {pid for pid, s in model.slots.items() if s.image}
    wanted = resolve_base(test, prompt)
    chain = ancestors(test, prompt)[:-1]
    for p in reversed(chain):
        if p.id in available:
            base = p.id
            break
    else:
        base = FROM_MODEL
    if base == wanted:
        return base, None
    missing = prompt_number(test, wanted)
    target = "the model view" if base == FROM_MODEL else f"prompt {prompt_number(test, base)}"
    return base, f"Prompt {missing} had no render, so this was compared with {target}."


def _resize_mask(mask: np.ndarray, shape_hw: tuple[int, int]) -> np.ndarray:
    h, w = shape_hw
    m = mask.astype(np.uint8)
    if m.shape != (h, w):
        m = cv2.resize(m, (w, h), interpolation=cv2.INTER_NEAREST)
    return m > 0


def zone_mask(prompt: Prompt, shape_hw: tuple[int, int], regions) -> np.ndarray:
    """Painted zone plus the chosen materials, at ``shape_hw``. All False when there's none."""
    out = np.zeros(shape_hw, bool)
    if prompt.zone is not None and prompt.zone.size:
        out |= _resize_mask(prompt.zone, shape_hw)
    chosen = set(prompt.zone_materials)
    for r in regions:
        if r.id in chosen:
            out |= _resize_mask(r.mask, shape_hw)
    return out


def move_prompt(test: PromptTest, prompt_id: str, delta: int) -> None:
    i = next(i for i, p in enumerate(test.prompts) if p.id == prompt_id)
    j = i + delta
    if 0 <= j < len(test.prompts):
        test.prompts[i], test.prompts[j] = test.prompts[j], test.prompts[i]


def remove_prompt(test: PromptTest, prompt_id: str) -> None:
    test.prompts = [p for p in test.prompts if p.id != prompt_id]
    for p in test.prompts:
        if p.starts_from == prompt_id:
            p.starts_from = FROM_PREVIOUS
    for m in test.models:
        m.slots.pop(prompt_id, None)
