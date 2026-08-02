import pytest

from webuserflowagent.models import ApplicationManifest, Element, Page, Selector, Transition


def cookie_button():
    return Element("accept_cookies", "button", [Selector("role", "button|Accept")])


def test_manifest_accepts_transition_between_known_states():
    manifest = ApplicationManifest(
        name="demo",
        base_url="https://example.com",
        pages=[Page("initial", "/", elements=[cookie_button()]), Page("ready", "/")],
        transitions=[Transition("initial", "ready", "click", "accept_cookies")],
    )

    manifest.validate()


def test_manifest_rejects_transition_to_unknown_state():
    manifest = ApplicationManifest(
        name="demo",
        base_url="https://example.com",
        pages=[Page("initial", "/", elements=[cookie_button()])],
        transitions=[Transition("initial", "missing", "click", "accept_cookies")],
    )

    with pytest.raises(ValueError, match="unknown page"):
        manifest.validate()
