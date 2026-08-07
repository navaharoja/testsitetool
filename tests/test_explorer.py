from webuserflowagent.explorer.page import _result_state_type, _search_target, elements_from_raw


def test_elements_prioritize_semantic_selectors_and_deduplicate_keys():
    raw = {
        "tag": "button",
        "type": "submit",
        "role": "button",
        "label": "Ingresar",
        "text": "Ingresar",
        "testid": "login-submit",
        "css": "#submit",
        "disabled": False,
    }

    elements = elements_from_raw([raw, raw])

    assert [element.key for element in elements] == ["button_ingresar", "button_ingresar_2"]
    assert elements[0].selectors[0].strategy == "testid"
    assert elements[0].selectors[1].strategy == "role"
    assert elements[0].selectors[0].unique is False
    assert elements[0].selectors[-1].unique is False
    assert "disabled" not in elements[0].attributes


def test_elements_always_have_a_css_fallback():
    elements = elements_from_raw(
        [{"tag": "input", "type": "email", "css": "body > form > input"}]
    )

    assert elements[0].kind == "email"
    assert elements[0].selectors[-1].strategy == "css"
    assert elements[0].selectors[-1].unique is True


def test_elements_repair_mojibake_and_preserve_region():
    elements = elements_from_raw(
        [{
            "tag": "button",
            "role": "button",
            "text": "Configuraci\u00c3\u00b3n",
            "region": "dialog",
            "blocking": True,
            "css": "#settings",
        }]
    )

    assert elements[0].text == "Configuraci\u00f3n"
    assert elements[0].key == "button_configuracion"
    assert elements[0].region == "dialog"
    assert elements[0].importance == "blocking"


def test_non_modal_dialog_is_not_considered_blocking():
    elements = elements_from_raw(
        [{
            "tag": "a",
            "role": "link",
            "text": "Atajo de accesibilidad",
            "region": "dialog",
            "blocking": False,
            "css": "#shortcut",
        }]
    )

    assert elements[0].importance == "primary"


def test_repair_handles_double_mojibake():
    elements = elements_from_raw(
        [{
            "tag": "button",
            "role": "button",
            "text": "Men\u00c3\u0192\u00c2\u00ba",
            "css": "#menu",
        }]
    )

    assert elements[0].text == "Men\u00fa"


def test_search_target_prefers_semantic_search_field():
    elements = elements_from_raw(
        [
            {"tag": "input", "role": "textbox", "label": "Nombre", "css": "#name"},
            {
                "tag": "input",
                "role": "textbox",
                "label": "Buscar productos",
                "name": "as_word",
                "css": "#search",
            },
        ]
    )

    assert _search_target(elements).key == "textbox_buscar_productos"


def test_search_target_accepts_combobox():
    elements = elements_from_raw(
        [{
            "tag": "input",
            "role": "combobox",
            "label": "Buscar productos",
            "name": "as_word",
            "css": "#search",
        }]
    )

    assert _search_target(elements).key == "combobox_buscar_productos"


def test_result_state_recognizes_captcha_wall():
    assert _result_state_type("https://example.com/captcha/wall", "Seguridad") == "challenge"
    assert _result_state_type("https://example.com/search?q=test", "Resultados") == "results"
