import pytest

from webuserflowagent.models import ApplicationManifest, Element, Page, Selector


def test_manifest_accepts_a_valid_page_and_element():
    manifest = ApplicationManifest(
        name="demo",
        base_url="https://example.com",
        pages=[
            Page(
                key="login",
                url_pattern="/login",
                elements=[
                    Element(
                        key="submit",
                        kind="button",
                        selectors=[Selector(strategy="role", value="button:Ingresar", score=1.0)],
                    )
                ],
            )
        ],
    )

    manifest.validate()


def test_manifest_rejects_invalid_base_url():
    with pytest.raises(ValueError, match="base_url"):
        ApplicationManifest(name="demo", base_url="example.com").validate()


def test_page_rejects_duplicate_element_keys():
    element = Element(
        key="submit",
        kind="button",
        selectors=[Selector(strategy="role", value="button")],
    )
    with pytest.raises(ValueError, match="duplicate"):
        Page(key="login", url_pattern="/login", elements=[element, element]).validate()
