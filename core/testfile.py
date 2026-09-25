"""Save and open prompt tests as .rqtest files (a zip the user keeps).

The file holds the test's prompts, model names, ratings and the uploaded images
exactly as they were uploaded. Render QA itself never writes it to disk: the
user downloads it and opens it again by uploading it.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import PurePosixPath

import cv2
import numpy as np

from .prompt_test import (
    EDIT, FROM_MODEL, FROM_PREVIOUS, GUARDRAIL, OUTCOMES, ModelEntry, Prompt, PromptTest, Slot,
)

FORMAT = "render-qa-test"
VERSION = 1
MAX_BYTES = 1_500_000_000  # uncompressed total
MAX_ENTRIES = 500

NOT_A_TEST = "This isn't a Render QA test file."
TOO_NEW = "This test was saved by a newer Render QA. Update Render QA to open it."
DAMAGED = "This test file is damaged or incomplete."
TOO_LARGE = "This test file is too large to open."


class TestFileError(ValueError):
    __test__ = False


def _ext(filename: str, data: bytes) -> str:
    suffix = PurePosixPath(filename or "").suffix.lower().lstrip(".")
    if suffix.isalnum() and 0 < len(suffix) <= 5:
        return suffix
    if data.startswith(b"\x89PNG"):
        return "png"
    if data.startswith(b"\xff\xd8"):
        return "jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return "bin"


def _zone_png(zone: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", zone.astype(np.uint8) * 255)
    return buf.tobytes()


def save_test(test: PromptTest) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        doc = {"format": FORMAT, "version": VERSION, "name": test.name,
               "recommendation": test.recommendation, "model_view": None, "prompts": [], "models": []}
        if test.model_view is not None:
            path = f"images/model_view.{_ext(test.model_view_name, test.model_view)}"
            z.writestr(path, test.model_view, zipfile.ZIP_STORED)
            doc["model_view"] = {"file": path, "name": test.model_view_name}
        for p in test.prompts:
            entry = {"id": p.id, "title": p.title, "text": p.text, "kind": p.kind,
                     "starts_from": p.starts_from, "zone": None, "zone_materials": list(p.zone_materials)}
            if p.zone is not None and p.zone.any():
                entry["zone"] = f"zones/{p.id}.png"
                z.writestr(entry["zone"], _zone_png(p.zone), zipfile.ZIP_DEFLATED)
            doc["prompts"].append(entry)
        for m in test.models:
            slots = {}
            for pid, s in m.slots.items():
                item = {"file": None, "filename": s.filename, "outcome": s.outcome, "rating": s.rating}
                if s.image is not None:
                    item["file"] = f"images/{m.id}/{pid}.{_ext(s.filename, s.image)}"
                    z.writestr(item["file"], s.image, zipfile.ZIP_STORED)
                slots[pid] = item
            doc["models"].append({"id": m.id, "tool": m.tool, "model": m.model, "slots": slots})
        z.writestr("test.json", json.dumps(doc, indent=1), zipfile.ZIP_DEFLATED)
    return buf.getvalue()


def _text(value, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _rating(value) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 5 else None


def load_test(data: bytes) -> PromptTest:
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except (zipfile.BadZipFile, ValueError, OSError):
        raise TestFileError(NOT_A_TEST) from None
    with z:
        infos = z.infolist()
        if len(infos) > MAX_ENTRIES or sum(i.file_size for i in infos) > MAX_BYTES:
            raise TestFileError(TOO_LARGE)
        try:
            doc = json.loads(z.read("test.json"))
        except KeyError:
            raise TestFileError(NOT_A_TEST) from None
        except (ValueError, zipfile.BadZipFile, OSError):
            raise TestFileError(DAMAGED) from None
        if not isinstance(doc, dict) or doc.get("format") != FORMAT:
            raise TestFileError(NOT_A_TEST)
        version = doc.get("version")
        if not isinstance(version, int) or version < 1:
            raise TestFileError(DAMAGED)
        if version > VERSION:
            raise TestFileError(TOO_NEW)
        try:
            return _build(z, doc)
        except TestFileError:
            raise
        except Exception:  # anything malformed inside a real test file
            raise TestFileError(DAMAGED) from None


def _read(z: zipfile.ZipFile, path) -> bytes:
    if not isinstance(path, str):
        raise TestFileError(DAMAGED)
    try:
        return z.read(path)
    except KeyError:
        raise TestFileError(DAMAGED) from None


def _build(z: zipfile.ZipFile, doc: dict) -> PromptTest:
    test = PromptTest(name=_text(doc.get("name"), "Prompt test"), recommendation=_text(doc.get("recommendation")),
                      prompts=[], models=[])
    mv = doc.get("model_view")
    if isinstance(mv, dict):
        test.model_view = _read(z, mv.get("file"))
        test.model_view_name = _text(mv.get("name"))

    for entry in doc.get("prompts") or []:
        pid = entry["id"]
        if not isinstance(pid, str) or not pid or any(p.id == pid for p in test.prompts):
            raise TestFileError(DAMAGED)
        zone = None
        if entry.get("zone"):
            img = cv2.imdecode(np.frombuffer(_read(z, entry["zone"]), np.uint8), cv2.IMREAD_GRAYSCALE)
            if img is None:
                raise TestFileError(DAMAGED)
            zone = img > 127
        starts = _text(entry.get("starts_from"), FROM_PREVIOUS) or FROM_PREVIOUS
        test.prompts.append(Prompt(
            id=pid, title=_text(entry.get("title"), "Prompt"), text=_text(entry.get("text")),
            kind=entry.get("kind") if entry.get("kind") in (EDIT, GUARDRAIL) else EDIT,
            starts_from=starts, zone=zone,
            zone_materials=[int(i) for i in entry.get("zone_materials") or []
                            if isinstance(i, int) and not isinstance(i, bool)],
        ))

    known = {p.id for p in test.prompts}
    for p in test.prompts:  # a start point naming a prompt that isn't here falls back to "previous"
        if p.starts_from not in (FROM_MODEL, FROM_PREVIOUS) and p.starts_from not in known:
            p.starts_from = FROM_PREVIOUS

    for entry in doc.get("models") or []:
        m = ModelEntry(id=_text(entry.get("id")) or f"m{len(test.models) + 1}",
                       tool=_text(entry.get("tool")), model=_text(entry.get("model")))
        for pid, s in (entry.get("slots") or {}).items():
            if pid not in known:
                continue
            m.slots[pid] = Slot(
                image=_read(z, s["file"]) if s.get("file") else None,
                filename=_text(s.get("filename")),
                outcome=s.get("outcome") if s.get("outcome") in OUTCOMES else None,
                rating=_rating(s.get("rating")),
            )
        test.models.append(m)
    return test
