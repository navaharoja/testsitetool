import json

from webuserflowagent.manifest import load, save
from webuserflowagent.models import ApplicationManifest


def test_manifest_round_trip(tmp_path):
    path = tmp_path / "app.json"
    expected = ApplicationManifest(name="demo", base_url="https://example.com")

    save(expected, path)
    actual = load(path)

    assert actual == expected
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == "1"
