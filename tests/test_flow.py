from webuserflowagent.explorer.page import elements_from_raw
from webuserflowagent.flow.graph import (
    candidate_elements,
    state_signature,
    unique_page_key,
)


def test_candidate_elements_excludes_destructive_wording():
    elements = elements_from_raw([
        {"tag": "a", "role": "link", "text": "Ver productos", "href": "/productos", "css": "#a1"},
        {"tag": "button", "role": "button", "text": "Eliminar cuenta", "css": "#a2"},
        {"tag": "a", "role": "link", "text": "Cerrar sesión", "href": "/logout", "css": "#a3"},
    ])

    candidates = candidate_elements(elements, base_netloc="example.com", max_actions=10)

    assert [element.text for element in candidates] == ["Ver productos"]


def test_candidate_elements_excludes_off_origin_and_file_links():
    elements = elements_from_raw([
        {"tag": "a", "role": "link", "text": "Interno", "href": "/interno", "css": "#a1"},
        {"tag": "a", "role": "link", "text": "Externo", "href": "https://otro-sitio.com/x", "css": "#a2"},
        {"tag": "a", "role": "link", "text": "Descargar PDF", "href": "/manual.pdf", "css": "#a3"},
        {"tag": "a", "role": "link", "text": "Escribinos", "href": "mailto:hola@example.com", "css": "#a4"},
    ])

    candidates = candidate_elements(elements, base_netloc="example.com", max_actions=10)

    assert [element.text for element in candidates] == ["Interno"]


def test_candidate_elements_requires_a_unique_selector():
    # dos elementos identicos -> ningun selector queda unico -> ninguno es candidato
    raw = {"tag": "a", "role": "link", "text": "Ver más", "href": "/mas", "css": "#dup"}
    elements = elements_from_raw([raw, raw])

    candidates = candidate_elements(elements, base_netloc="example.com", max_actions=10)

    assert candidates == []


def test_candidate_elements_respects_max_actions_and_prefers_links_and_buttons():
    elements = elements_from_raw([
        {"tag": "div", "role": "", "text": "Contenedor clickeable", "css": "#c1"},
        {"tag": "a", "role": "link", "text": "Link", "href": "/x", "css": "#c2"},
        {"tag": "button", "role": "button", "text": "Boton", "css": "#c3"},
    ])

    candidates = candidate_elements(elements, base_netloc="example.com", max_actions=2)

    assert len(candidates) == 2
    assert {element.kind for element in candidates} == {"link", "button"}


def test_state_signature_differs_by_path_and_by_element_set():
    elements_a = elements_from_raw([{"tag": "a", "role": "link", "text": "A", "href": "/a", "css": "#a"}])
    elements_b = elements_from_raw([{"tag": "a", "role": "link", "text": "B", "href": "/b", "css": "#b"}])

    same_path_same_elements = state_signature("https://example.com/home", elements_a)
    same_path_diff_elements = state_signature("https://example.com/home", elements_b)
    diff_path_same_elements = state_signature("https://example.com/other", elements_a)

    assert same_path_same_elements != same_path_diff_elements
    assert same_path_same_elements != diff_path_same_elements


def test_state_signature_is_stable_for_the_same_state():
    elements = elements_from_raw([{"tag": "a", "role": "link", "text": "A", "href": "/a", "css": "#a"}])

    first = state_signature("https://example.com/home", elements)
    second = state_signature("https://example.com/home", elements)

    assert first == second


def test_unique_page_key_appends_suffix_on_collision():
    used: set[str] = set()

    first = unique_page_key("home", used)
    second = unique_page_key("home", used)
    third = unique_page_key("home", used)

    assert (first, second, third) == ("home", "home_2", "home_3")
    assert used == {"home", "home_2", "home_3"}
