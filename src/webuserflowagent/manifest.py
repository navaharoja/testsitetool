from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import ApplicationManifest, Element, Flow, FlowStep, Page, Selector, Transition


def _selector(data: dict[str, Any]) -> Selector:
    return Selector(**data)


def _element(data: dict[str, Any]) -> Element:
    values = dict(data)
    values["selectors"] = [_selector(item) for item in values.get("selectors", [])]
    return Element(**values)


def _page(data: dict[str, Any]) -> Page:
    values = dict(data)
    values["elements"] = [_element(item) for item in values.get("elements", [])]
    return Page(**values)


def _flow(data: dict[str, Any]) -> Flow:
    values = dict(data)
    values["steps"] = [FlowStep(**item) for item in values.get("steps", [])]
    return Flow(**values)


def from_dict(data: dict[str, Any]) -> ApplicationManifest:
    values = dict(data)
    values["pages"] = [_page(item) for item in values.get("pages", [])]
    values["flows"] = [_flow(item) for item in values.get("flows", [])]
    values["transitions"] = [Transition(**item) for item in values.get("transitions", [])]
    manifest = ApplicationManifest(**values)
    manifest.validate()
    return manifest


def load(path: Path) -> ApplicationManifest:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("Manifest root must be a JSON object")
    return from_dict(data)


def save(manifest: ApplicationManifest, path: Path) -> None:
    manifest.validate()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(manifest.to_dict(), handle, ensure_ascii=False, indent=2)
        handle.write("\n")
