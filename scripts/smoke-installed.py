"""Verify installed resources and an offline fresh archive; run outside the checkout."""

from pathlib import Path
from importlib.metadata import version
import tempfile

from fastapi.testclient import TestClient

import meshtastic_sf
from meshtastic_sf.web.application import create_app


def main():
    assert meshtastic_sf.__version__ == version("meshtastic-sf-server"), "Package version mismatch"
    print(f"Testing installed package: {meshtastic_sf.__file__}")
    with tempfile.TemporaryDirectory(prefix="meshmemo-smoke-") as directory:
        with TestClient(create_app(str(Path(directory) / "archive.db"), admin_password="smoke-only-password"),
                        base_url="http://127.0.0.1", headers={"Authorization": "Basic YWRtaW46c21va2Utb25seS1wYXNzd29yZA=="}) as client:
            assert client.get("/").status_code == 200
            for asset in ("app.js", "app.css", "logo.svg", "i18n.js",
                          "locales/en.json", "locales/uk.json", "locales/ru.json"):
                assert client.get("/static/" + asset).status_code == 200, asset
            assert client.get("/healthz").status_code == 200
            status = client.get("/api/status").json()
            assert status["database"]["messages"] == 0
            assert status["connection"]["mode"] == "off"
            assert status["settings"]["replay_enabled"] is False
    print("Installed assets, migrations and offline startup: PASS")


if __name__ == "__main__":
    main()
