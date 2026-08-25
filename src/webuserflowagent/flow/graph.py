"""Flow Agent: multi-step graph exploration.

Builds on the Explorer Agent (`explorer.page`) instead of reimplementing it —
the first state captured here is exactly what `explore_page` would capture,
using the same primitives (`_capture`, `_wait_for_interactive_content`,
`_dismiss_cookie_consent`, `_locator_for_element`, `elements_from_raw`).
What's new is walking BEYOND that first state: clicking through discovered
elements, capturing the resulting states, and recording the graph of
`Page`/`Transition`/`Flow` objects that results — generalizing the single
hardcoded "search flow" `explore_page` already builds (see `page.py`) into
N flows discovered by an actual bounded, safety-filtered crawl.

Heuristic, not LLM-driven: candidate elements are filtered and prioritized
by simple rules (same-origin, non-destructive wording, unique selector
required), not by a model deciding what to click. See the project README's
own roadmap — the Explorer Agent has no LLM dependency either, and a
deterministic crawler is a more trustworthy foundation to build the
Generator Agent on top of later.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from ..explorer.page import (
    _capture,
    _dismiss_cookie_consent,
    _locator_for_element,
    _slug,
    _wait_for_interactive_content,
    elements_from_raw,
)
from ..models import ApplicationManifest, Element, Flow, FlowStep, Page, Transition

DEFAULT_MAX_PAGES = 8
DEFAULT_MAX_ACTIONS_PER_PAGE = 6
DEFAULT_MAX_DEPTH = 3

# Palabras que, si aparecen en el texto/label/href visible de un elemento,
# lo excluyen de los candidatos a click — el crawler nunca debe intentar
# completar una compra, borrar algo o cerrar la sesion por su cuenta.
_DESTRUCTIVE_WORDS = (
    "eliminar", "borrar", "cancelar", "cerrar sesion", "cerrar sesión",
    "logout", "log out", "sign out", "delete", "remove", "desactivar",
    "deactivate", "pagar", "comprar", "checkout", "purchase", "buy now",
    "enviar pedido", "submit order", "confirmar compra", "unsubscribe",
    "desuscrib", "eliminar cuenta", "delete account",
)

# Se prefieren enlaces/botones reales sobre contenedores clickeables genericos
# (menor probabilidad de disparar algo inesperado).
_PREFERRED_KINDS = {"link", "button"}

_SKIP_HREF_PREFIXES = ("mailto:", "tel:", "javascript:")
_SKIP_HREF_SUFFIXES = (
    ".pdf", ".zip", ".doc", ".docx", ".xls", ".xlsx",
    ".jpg", ".jpeg", ".png", ".gif", ".svg",
)


def _is_destructive(element: Element) -> bool:
    haystack = " ".join(
        filter(None, [element.label, element.text, element.attributes.get("href", "")])
    ).lower()
    return any(word in haystack for word in _DESTRUCTIVE_WORDS)


def _is_off_scope_href(href: str) -> bool:
    if not href:
        return False
    lowered = href.lower()
    if lowered.startswith(_SKIP_HREF_PREFIXES):
        return True
    return lowered.endswith(_SKIP_HREF_SUFFIXES)


def _is_same_origin(href: str, base_netloc: str) -> bool:
    if not href:
        return True  # sin href (ej. un boton) -> se asume que actua sobre la pagina actual
    parsed = urlsplit(href)
    if not parsed.netloc:
        return True  # link relativo
    return parsed.netloc == base_netloc


def candidate_elements(
    elements: list[Element], base_netloc: str, max_actions: int,
) -> list[Element]:
    """Filtra y prioriza que elementos son seguros/utiles para clickear.

    Reglas: requiere al menos un selector unico (mismo requisito que
    _locator_for_element ya impone al ejecutar el click, chequeado antes
    para no gastar un intento en un elemento que fallaria igual); descarta
    texto/label/href con palabras destructivas; descarta href fuera de
    origen, mailto/tel/javascript, o que apunte a un archivo descargable;
    prioriza link/button sobre contenedores clickeables genericos.
    """
    scored: list[tuple[int, Element]] = []
    for element in elements:
        if not any(selector.unique for selector in element.selectors):
            continue
        if _is_destructive(element):
            continue
        href = element.attributes.get("href", "")
        if _is_off_scope_href(href) or not _is_same_origin(href, base_netloc):
            continue
        priority = 0 if element.kind in _PREFERRED_KINDS else 1
        scored.append((priority, element))
    scored.sort(key=lambda pair: pair[0])
    return [element for _, element in scored[:max_actions]]


def state_signature(url: str, elements: list[Element]) -> tuple[str, tuple[str, ...]]:
    """Identidad de un estado: path de la URL + el conjunto de elementos
    presentes. Los cambios de estado de una SPA no siempre cambian la URL
    (ver docstring de _perform_search en explorer/page.py), asi que la URL
    sola no alcanza para distinguir dos estados."""
    parsed = urlsplit(url)
    return (parsed.path or "/", tuple(sorted(element.key for element in elements)))


def unique_page_key(base_key: str, used: set[str]) -> str:
    key = base_key
    suffix = 2
    while key in used:
        key = f"{base_key}_{suffix}"
        suffix += 1
    used.add(key)
    return key


@dataclass
class _CrawlState:
    pages: list[Page] = field(default_factory=list)
    pages_by_key: dict[str, Page] = field(default_factory=dict)
    transitions: list[Transition] = field(default_factory=list)
    used_page_keys: set[str] = field(default_factory=set)
    visited_signatures: dict[tuple, str] = field(default_factory=dict)
    first_transition_into: dict[str, Transition] = field(default_factory=dict)
    expanded: set[str] = field(default_factory=set)
    max_pages: int = DEFAULT_MAX_PAGES


def _walk(
    browser_page: Any,
    from_page: Page,
    depth: int,
    max_depth: int,
    max_actions_per_page: int,
    base_netloc: str,
    timeout_ms: int,
    state: _CrawlState,
) -> None:
    if depth >= max_depth or len(state.pages) >= state.max_pages:
        return

    candidates = candidate_elements(from_page.elements, base_netloc, max_actions_per_page)
    parent_url = browser_page.url

    for element in candidates:
        if len(state.pages) >= state.max_pages:
            break
        try:
            locator = _locator_for_element(browser_page, element)
            locator.click(timeout=timeout_ms)
        except Exception:
            continue  # el elemento ya no es clickeable (se movio, quedo oculto, etc.) — se salta

        browser_page.wait_for_timeout(500)
        _wait_for_interactive_content(browser_page, timeout_ms)
        raw, new_url, new_title = _capture(browser_page)
        new_elements = elements_from_raw(raw)
        signature = state_signature(new_url, new_elements)

        if signature in state.visited_signatures:
            to_key = state.visited_signatures[signature]
        else:
            parsed = urlsplit(new_url)
            base_key = _slug(new_title or parsed.path or parsed.netloc, "page")
            to_key = unique_page_key(base_key, state.used_page_keys)
            new_page = Page(
                key=to_key, title=new_title or None, state_type="ready",
                url_pattern=parsed.path or "/", elements=new_elements,
            )
            state.pages.append(new_page)
            state.pages_by_key[to_key] = new_page
            state.visited_signatures[signature] = to_key

        transition = Transition(from_page.key, to_key, "click", element.key)
        state.transitions.append(transition)
        if to_key not in state.first_transition_into:
            state.first_transition_into[to_key] = transition

        if to_key not in state.expanded:
            state.expanded.add(to_key)
            _walk(
                browser_page, state.pages_by_key[to_key], depth + 1, max_depth,
                max_actions_per_page, base_netloc, timeout_ms, state,
            )

        # Volver al estado del padre antes del siguiente candidato hermano.
        # go_back() funciona para la mayoria de navegaciones reales (cambian
        # la URL); si un elemento cambio solo estado de cliente (sin URL
        # nueva), go_back no lo revierte — se hace un goto de respaldo a la
        # URL del padre. Limitacion conocida del v0: ramas de estado
        # puramente client-side no se resetean perfectamente entre hermanos.
        if browser_page.url != parent_url:
            try:
                browser_page.go_back(timeout=timeout_ms, wait_until="domcontentloaded")
            except Exception:
                pass
            if browser_page.url != parent_url:
                try:
                    browser_page.goto(parent_url, wait_until="domcontentloaded", timeout=timeout_ms)
                except Exception:
                    pass
            _wait_for_interactive_content(browser_page, timeout_ms)


def _flow_for_page(page_key: str, state: _CrawlState) -> Flow:
    """Reconstruye el camino desde la raiz hasta page_key siguiendo
    first_transition_into hacia atras — un Flow por pagina descubierta,
    mismo formato de FlowStep que ya usa el flow 'search' de explore_page."""
    chain: list[Transition] = []
    current = page_key
    while current in state.first_transition_into:
        transition = state.first_transition_into[current]
        chain.append(transition)
        current = transition.from_page
    chain.reverse()
    steps = [
        FlowStep(action=transition.action, target=transition.target, expected_page=transition.to_page)
        for transition in chain
    ]
    target_page = state.pages_by_key[page_key]
    name = _slug(f"flow_to_{target_page.title or page_key}", f"flow_{page_key}")
    return Flow(name=name, steps=steps)


def explore_flows(
    url: str,
    application_name: str,
    *,
    headless: bool = True,
    timeout_ms: int = 30_000,
    max_pages: int = DEFAULT_MAX_PAGES,
    max_actions_per_page: int = DEFAULT_MAX_ACTIONS_PER_PAGE,
    max_depth: int = DEFAULT_MAX_DEPTH,
    dismiss_cookies: bool = True,
) -> ApplicationManifest:
    """Explora un sitio siguiendo clicks reales (BFS/DFS acotado por
    max_pages/max_actions_per_page/max_depth), a diferencia de explore_page
    que solo captura una pagina. Devuelve un ApplicationManifest con todas
    las paginas y transiciones descubiertas, mas un Flow por pagina
    reconstruyendo el camino real que la alcanzo desde la raiz."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            'Playwright is required. Install it with: pip install -e ".[explorer]"'
        ) from exc

    state = _CrawlState(max_pages=max_pages)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        try:
            browser_page = browser.new_page()
            browser_page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            _wait_for_interactive_content(browser_page, timeout_ms)
            raw, current_url, title = _capture(browser_page)

            if dismiss_cookies:
                consent_target = _dismiss_cookie_consent(browser_page)
                if consent_target:
                    raw, current_url, title = _capture(browser_page)

            parsed = urlsplit(current_url)
            base_netloc = parsed.netloc
            base_url = f"{parsed.scheme}://{parsed.netloc}"

            elements = elements_from_raw(raw)
            root_key = unique_page_key(
                _slug(title or parsed.path or parsed.netloc, "page"), state.used_page_keys,
            )
            root_page = Page(
                key=root_key, title=title or None, state_type="ready",
                url_pattern=parsed.path or "/", elements=elements,
            )
            state.pages.append(root_page)
            state.pages_by_key[root_key] = root_page
            state.visited_signatures[state_signature(current_url, elements)] = root_key
            state.expanded.add(root_key)

            _walk(
                browser_page, root_page, 0, max_depth, max_actions_per_page,
                base_netloc, timeout_ms, state,
            )
        finally:
            browser.close()

    flows = [
        _flow_for_page(page.key, state)
        for page in state.pages
        if page.key != root_key and page.key in state.first_transition_into
    ]

    manifest = ApplicationManifest(
        name=application_name,
        base_url=base_url,
        pages=state.pages,
        flows=flows,
        transitions=state.transitions,
        metadata={
            "explorer": "playwright-flow",
            "source_url": url,
            "max_pages": max_pages,
            "max_actions_per_page": max_actions_per_page,
            "max_depth": max_depth,
            "pages_discovered": len(state.pages),
        },
    )
    manifest.validate()
    return manifest
