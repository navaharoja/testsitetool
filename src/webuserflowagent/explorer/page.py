from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from ..models import ApplicationManifest, Element, Flow, FlowStep, Page, Selector, Transition

INTERACTIVE_SELECTOR = (
    "a[href], button, input:not([type='hidden']), select, textarea, "
    "[role='button'], [role='link'], [role='checkbox'], [role='radio'], "
    "[role='switch'], [role='tab'], [contenteditable='true']"
)

EXTRACT_ELEMENTS_SCRIPT = r"""
(elements) => {
  const cleanText = value => (value || "").trim().replace(/\s+/g, " ").slice(0, 200);

  const accessibleName = element => {
    const labelledBy = element.getAttribute("aria-labelledby");
    if (labelledBy) {
      const value = labelledBy.split(/\s+/).map(id => document.getElementById(id))
        .filter(Boolean).map(node => cleanText(node.innerText || node.textContent)).join(" ");
      if (value) return value;
    }
    if (element.getAttribute("aria-label")) return cleanText(element.getAttribute("aria-label"));
    if (element.labels) {
      const value = [...element.labels].map(label => cleanText(label.innerText)).filter(Boolean).join(" ");
      if (value) return value;
    }
    if (element.getAttribute("alt")) return cleanText(element.getAttribute("alt"));
    if (element.getAttribute("title")) return cleanText(element.getAttribute("title"));
    return "";
  };

  const regionContext = element => {
    const semantic = element.closest("[role='dialog'], dialog, header, main, footer, nav, aside");
    if (semantic) {
      const role = semantic.getAttribute("role");
      if (role === "dialog" || semantic.tagName.toLowerCase() === "dialog") {
        const modal = semantic.getAttribute("aria-modal") === "true" ||
          (semantic.tagName.toLowerCase() === "dialog" && semantic.hasAttribute("open"));
        return {region: "dialog", blocking: modal};
      }
      return {region: semantic.tagName.toLowerCase(), blocking: false};
    }
    let current = element;
    while (current && current !== document.body) {
      const style = window.getComputedStyle(current);
      const rect = current.getBoundingClientRect();
      const viewportArea = Math.max(1, window.innerWidth * window.innerHeight);
      const coverage = (rect.width * rect.height) / viewportArea;
      if (style.position === "fixed" && Number.parseInt(style.zIndex || "0", 10) > 0 && coverage >= 0.05) {
        return {region: "overlay", blocking: true};
      }
      current = current.parentElement;
    }
    return {region: "content", blocking: false};
  };

  const cssPath = (element) => {
    if (element.id) return `#${CSS.escape(element.id)}`;
    const parts = [];
    let current = element;
    while (current && current.nodeType === Node.ELEMENT_NODE && current !== document.body) {
      let part = current.tagName.toLowerCase();
      if (!current.parentElement) {
        parts.unshift(part);
        break;
      }
      const siblings = [...current.parentElement.children].filter(
        sibling => sibling.tagName === current.tagName
      );
      if (siblings.length > 1) part += `:nth-of-type(${siblings.indexOf(current) + 1})`;
      parts.unshift(part);
      current = current.parentElement;
    }
    return `body > ${parts.join(" > ")}`;
  };

  const implicitRole = (element) => {
    const tag = element.tagName.toLowerCase();
    const type = (element.getAttribute("type") || "").toLowerCase();
    if (tag === "a" && element.hasAttribute("href")) return "link";
    if (tag === "button" || (tag === "input" && ["button", "submit", "reset"].includes(type))) return "button";
    if (tag === "select") return "combobox";
    if (tag === "textarea" || (tag === "input" && !["checkbox", "radio"].includes(type))) return "textbox";
    if (type === "checkbox") return "checkbox";
    if (type === "radio") return "radio";
    return "";
  };

  return elements.filter(element => {
    const style = window.getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    const hiddenAncestor = element.closest("[hidden], [aria-hidden='true'], [inert]");
    // Keep content below the fold (the agent can scroll), but reject common
    // accessibility/off-screen hiding techniques above or beside the viewport.
    const intersectsDocumentView = rect.bottom > 0 && rect.right > 0 && rect.left < window.innerWidth;
    return !hiddenAncestor && style.visibility !== "hidden" && style.display !== "none" &&
      Number.parseFloat(style.opacity || "1") > 0 && rect.width > 0 && rect.height > 0 &&
      intersectsDocumentView;
  }).map(element => {
    const context = regionContext(element);
    return {
      tag: element.tagName.toLowerCase(),
      type: element.getAttribute("type") || "",
      id: element.id || "",
      name: element.getAttribute("name") || "",
      role: element.getAttribute("role") || implicitRole(element),
      label: accessibleName(element),
      text: cleanText(element.innerText || element.value),
      placeholder: element.getAttribute("placeholder") || "",
      testid: element.getAttribute("data-testid") || element.getAttribute("data-test") || "",
      href: element.href || "",
      disabled: element.disabled || element.getAttribute("aria-disabled") === "true",
      region: context.region,
      blocking: context.blocking,
      css: cssPath(element)
    };
  });
}
"""


def _slug(value: str, fallback: str = "element") -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"[^a-z0-9]+", "_", ascii_value.lower()).strip("_")
    return normalized[:60] or fallback


def _repair_text(value: str) -> str:
    """Repair common UTF-8 text decoded as Windows-1252 without touching valid text."""
    markers = ("\u00c3", "\u00c2", "\u00e2\u20ac", "\u00f0\u0178")
    repaired = value
    for _ in range(2):
        if not any(marker in repaired for marker in markers):
            break
        try:
            candidate = repaired.encode("cp1252").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            break
        if candidate == repaired:
            break
        repaired = candidate
    return repaired


def _repair_raw(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        key: _repair_text(value) if isinstance(value, str) else value
        for key, value in raw.items()
    }


def _kind(raw: dict[str, Any]) -> str:
    return str(raw.get("role") or raw.get("type") or raw.get("tag") or "element")


def _importance(region: str, blocking: bool = False) -> str:
    if blocking:
        return "blocking"
    if region in {"footer", "aside"}:
        return "secondary"
    if region == "nav":
        return "navigation"
    return "primary"


def _selector_candidates(raw: dict[str, Any]) -> list[Selector]:
    candidates: list[Selector] = []
    testid = str(raw.get("testid", ""))
    role = str(raw.get("role", ""))
    label = str(raw.get("label", ""))
    text = str(raw.get("text", ""))
    placeholder = str(raw.get("placeholder", ""))

    if testid:
        candidates.append(Selector("testid", testid, 1.0))
    if role:
        accessible_name = label or text
        value = f"{role}|{accessible_name}" if accessible_name else role
        candidates.append(Selector("role", value, 0.95 if accessible_name else 0.8))
    if label:
        candidates.append(Selector("label", label, 0.9))
    if placeholder:
        candidates.append(Selector("placeholder", placeholder, 0.85))
    if raw.get("id"):
        candidates.append(Selector("css", str(raw["css"]), 0.8))
    elif raw.get("name"):
        candidates.append(Selector("name", str(raw["name"]), 0.75))
    if text and raw.get("tag") in {"a", "button"}:
        candidates.append(Selector("text", text, 0.7))
    if raw.get("css") and not any(item.strategy == "css" for item in candidates):
        candidates.append(Selector("css", str(raw["css"]), 0.4))
    return candidates


def elements_from_raw(items: Iterable[dict[str, Any]]) -> list[Element]:
    elements: list[Element] = []
    used_keys: set[str] = set()
    repaired_items = [_repair_raw(raw) for raw in items]
    for index, raw in enumerate(repaired_items, start=1):
        identity = str(raw.get("label") or raw.get("text") or raw.get("name") or raw.get("id") or "")
        base_key = _slug(f"{_kind(raw)}_{identity}", f"element_{index}")
        key = base_key
        suffix = 2
        while key in used_keys:
            key = f"{base_key}_{suffix}"
            suffix += 1
        used_keys.add(key)
        attributes = {
            key: str(raw[key])
            for key in ("tag", "type", "name", "href")
            if raw.get(key) not in (None, "")
        }
        if raw.get("disabled") is True:
            attributes["disabled"] = "true"
        region = str(raw.get("region") or "content")
        elements.append(
            Element(
                key=key,
                kind=_kind(raw),
                label=str(raw.get("label")) if raw.get("label") else None,
                text=str(raw.get("text")) if raw.get("text") else None,
                region=region,
                importance=_importance(region, raw.get("blocking") is True),
                selectors=_selector_candidates(raw),
                attributes=attributes,
            )
        )

    selector_counts = Counter(
        (selector.strategy, selector.value)
        for element in elements
        for selector in element.selectors
    )
    for element in elements:
        for selector in element.selectors:
            selector.unique = selector_counts[(selector.strategy, selector.value)] == 1
    return elements


def _capture(browser_page: Any) -> tuple[list[dict[str, Any]], str, str]:
    raw = browser_page.locator(INTERACTIVE_SELECTOR).evaluate_all(EXTRACT_ELEMENTS_SCRIPT)
    return raw, browser_page.url, _repair_text(browser_page.title())


def _dismiss_cookie_consent(browser_page: Any) -> str | None:
    candidates = [
        ("[data-testid='action:understood-button']", "button_aceptar_cookies"),
        ("button:has-text('Aceptar cookies')", "button_aceptar_cookies"),
        ("button:has-text('Accept cookies')", "button_accept_cookies"),
        ("button:has-text('Aceptar todas')", "button_aceptar_todas"),
        ("button:has-text('Entendido')", "button_entendido"),
    ]
    for selector, target in candidates:
        locator = browser_page.locator(selector)
        for index in range(locator.count()):
            candidate = locator.nth(index)
            if candidate.is_visible():
                candidate.click()
                browser_page.wait_for_timeout(500)
                return target
    return None


def _write_screenshot(browser_page: Any, screenshot_path: str) -> None:
    path = Path(screenshot_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    browser_page.screenshot(path=str(path), full_page=True)


def _search_target(elements: list[Element]) -> Element | None:
    textboxes = [
        element
        for element in elements
        if element.kind in {"textbox", "searchbox", "search", "combobox"}
    ]
    if not textboxes:
        return None
    for element in textboxes:
        searchable = " ".join(
            filter(None, [element.key, element.label, element.text, element.attributes.get("name")])
        ).lower()
        if any(hint in searchable for hint in ("search", "buscar", "busqueda", "as_word")):
            return element
    return textboxes[0] if len(textboxes) == 1 else None


def _locator_for_element(browser_page: Any, element: Element) -> Any:
    for selector in element.selectors:
        if selector.unique is not True:
            continue
        if selector.strategy == "testid":
            return browser_page.get_by_test_id(selector.value)
        if selector.strategy == "label":
            return browser_page.get_by_label(selector.value, exact=True)
        if selector.strategy == "placeholder":
            return browser_page.get_by_placeholder(selector.value, exact=True)
        if selector.strategy == "name":
            escaped = selector.value.replace('"', '\\"')
            return browser_page.locator(f'[name="{escaped}"]')
        if selector.strategy == "css":
            return browser_page.locator(selector.value)
    raise RuntimeError(f"No unique executable selector for element '{element.key}'")


def _perform_search(browser_page: Any, elements: list[Element], query: str, timeout_ms: int) -> str:
    target = _search_target(elements)
    if target is None:
        raise RuntimeError("No unambiguous search textbox was discovered")
    locator = _locator_for_element(browser_page, target)
    locator.fill(query)
    locator.press("Enter")
    try:
        browser_page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
    except Exception:
        # Client-side applications may update results without a document navigation.
        pass
    browser_page.wait_for_timeout(750)
    return target.key


def _result_state_type(url: str, title: str) -> str:
    haystack = f"{url} {title}".lower()
    challenge_markers = ("captcha", "challenge", "security-check", "seguridad")
    return "challenge" if any(marker in haystack for marker in challenge_markers) else "results"


def explore_page(
    url: str,
    application_name: str,
    *,
    headless: bool = True,
    timeout_ms: int = 30_000,
    screenshot_path: str | None = None,
    dismiss_cookies: bool = True,
    search_query: str | None = None,
) -> ApplicationManifest:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            'Playwright is required. Install it with: pip install -e ".[explorer]"'
        ) from exc

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        try:
            browser_page = browser.new_page()
            browser_page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            initial_raw, initial_url, initial_title = _capture(browser_page)
            if screenshot_path and dismiss_cookies:
                path = Path(screenshot_path)
                initial_path = path.with_name(f"{path.stem}-initial{path.suffix}")
                _write_screenshot(browser_page, str(initial_path))
            consent_target = _dismiss_cookie_consent(browser_page) if dismiss_cookies else None
            if consent_target:
                ready_raw, final_url, title = _capture(browser_page)
            else:
                ready_raw, final_url, title = initial_raw, initial_url, initial_title
            ready_elements = elements_from_raw(ready_raw)
            search_target: str | None = None
            if search_query:
                if screenshot_path:
                    path = Path(screenshot_path)
                    ready_path = path.with_name(f"{path.stem}-ready{path.suffix}")
                    _write_screenshot(browser_page, str(ready_path))
                search_target = _perform_search(browser_page, ready_elements, search_query, timeout_ms)
                results_raw, results_url, results_title = _capture(browser_page)
            if screenshot_path:
                _write_screenshot(browser_page, screenshot_path)
        finally:
            browser.close()

    parsed = urlsplit(final_url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    page_key = _slug(title or parsed.path or parsed.netloc, "page")
    ready_key = page_key
    pages: list[Page]
    transitions: list[Transition] = []
    if consent_target:
        initial_key = f"{page_key}_cookie_consent"
        ready_key = f"{page_key}_ready"
        pages = [
            Page(
                key=initial_key,
                title=initial_title or None,
                state_type="blocked",
                url_pattern=urlsplit(initial_url).path or "/",
                elements=elements_from_raw(initial_raw),
            ),
            Page(
                key=ready_key,
                title=title or None,
                state_type="ready",
                url_pattern=parsed.path or "/",
                elements=ready_elements,
            ),
        ]
        transitions.append(Transition(initial_key, ready_key, "click", consent_target))
    else:
        pages = [
            Page(
                key=ready_key,
                title=title or None,
                state_type="ready",
                url_pattern=parsed.path or "/",
                elements=ready_elements,
            )
        ]

    flows: list[Flow] = []
    if search_query and search_target:
        results_parsed = urlsplit(results_url)
        result_type = _result_state_type(results_url, results_title)
        suffix = "challenge" if result_type == "challenge" else "search_results"
        results_key = f"{_slug(results_title or results_parsed.path, 'results')}_{suffix}"
        if results_key in {page.key for page in pages}:
            results_key = f"{results_key}_2"
        pages.append(
            Page(
                key=results_key,
                title=results_title or None,
                state_type=result_type,
                url_pattern=results_parsed.path or "/",
                elements=elements_from_raw(results_raw),
            )
        )
        transitions.append(
            Transition(ready_key, results_key, "search", search_target, value=search_query)
        )
        flows.append(
            Flow(
                name="search",
                steps=[
                    FlowStep(action="fill", target=search_target, value=search_query),
                    FlowStep(action="press", target=search_target, value="Enter", expected_page=results_key),
                ],
            )
        )

    manifest = ApplicationManifest(
        name=application_name,
        base_url=base_url,
        pages=pages,
        flows=flows,
        transitions=transitions,
        metadata={
            "explorer": "playwright",
            "source_url": url,
            "cookie_consent_dismissed": consent_target is not None,
            "challenge_detected": any(page.state_type == "challenge" for page in pages),
        },
    )
    manifest.validate()
    return manifest
