from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class Selector:
    strategy: str
    value: str
    score: float = 0.0
    unique: bool | None = None

    def validate(self) -> None:
        if not self.strategy.strip() or not self.value.strip():
            raise ValueError("Selector strategy and value are required")
        if not 0 <= self.score <= 1:
            raise ValueError("Selector score must be between 0 and 1")


@dataclass(slots=True)
class Element:
    key: str
    kind: str
    selectors: list[Selector]
    label: str | None = None
    text: str | None = None
    region: str = "content"
    importance: str = "primary"
    attributes: dict[str, str] = field(default_factory=dict)

    def validate(self) -> None:
        if not self.key.strip() or not self.kind.strip():
            raise ValueError("Element key and kind are required")
        if not self.selectors:
            raise ValueError(f"Element '{self.key}' needs at least one selector")
        for selector in self.selectors:
            selector.validate()


@dataclass(slots=True)
class Page:
    key: str
    url_pattern: str
    title: str | None = None
    elements: list[Element] = field(default_factory=list)

    def validate(self) -> None:
        if not self.key.strip() or not self.url_pattern.strip():
            raise ValueError("Page key and url_pattern are required")
        keys = [element.key for element in self.elements]
        if len(keys) != len(set(keys)):
            raise ValueError(f"Page '{self.key}' contains duplicate element keys")
        for element in self.elements:
            element.validate()


@dataclass(slots=True)
class FlowStep:
    action: str
    target: str | None = None
    value: str | None = None
    expected_page: str | None = None

    def validate(self) -> None:
        if not self.action.strip():
            raise ValueError("Flow step action is required")


@dataclass(slots=True)
class Flow:
    name: str
    steps: list[FlowStep] = field(default_factory=list)

    def validate(self) -> None:
        if not self.name.strip():
            raise ValueError("Flow name is required")
        for step in self.steps:
            step.validate()


@dataclass(slots=True)
class Transition:
    from_page: str
    to_page: str
    action: str
    target: str

    def validate(self) -> None:
        if not all(value.strip() for value in (self.from_page, self.to_page, self.action, self.target)):
            raise ValueError("Transition fields are required")


@dataclass(slots=True)
class ApplicationManifest:
    name: str
    base_url: str
    version: str = "1"
    pages: list[Page] = field(default_factory=list)
    flows: list[Flow] = field(default_factory=list)
    transitions: list[Transition] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if not self.name.strip():
            raise ValueError("Application name is required")
        if not self.base_url.startswith(("http://", "https://")):
            raise ValueError("base_url must start with http:// or https://")
        page_keys = [page.key for page in self.pages]
        if len(page_keys) != len(set(page_keys)):
            raise ValueError("Manifest contains duplicate page keys")
        for page in self.pages:
            page.validate()
        for flow in self.flows:
            flow.validate()
        page_key_set = set(page_keys)
        pages_by_key = {page.key: page for page in self.pages}
        for transition in self.transitions:
            transition.validate()
            if transition.from_page not in page_key_set or transition.to_page not in page_key_set:
                raise ValueError("Transition references an unknown page")
            source_elements = {element.key for element in pages_by_key[transition.from_page].elements}
            if transition.target not in source_elements:
                raise ValueError("Transition target does not exist in its source page")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
