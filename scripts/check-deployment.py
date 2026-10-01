"""Read-only deployment checks; read credentials from the private config, never print them."""

import argparse
import base64
import json
import re
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler

from meshtastic_sf.config import load_config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    config = load_config(args.config)
    host = config.host if config.host not in {"0.0.0.0", "::"} else "127.0.0.1"
    if ":" in host:
        host = "[" + host + "]"
    base = f"http://{host}:{config.port}"
    auth = "Basic " + base64.b64encode(("admin:" + config.password).encode()).decode()
    opener = build_opener(ProxyHandler({}))

    def fetch(path, authenticated=False, data=None, extra=None):
        headers = {"Authorization": auth} if authenticated else {}
        headers.update(extra or {})
        request = Request(base + path, headers=headers, data=data)
        try:
            with opener.open(request, timeout=10) as response:
                return response.status, response.read()
        except HTTPError as error:
            return error.code, error.read()

    for path in ("/", "/api/status", "/api/channels", "/healthz", "/static/app.js"):
        assert fetch(path)[0] == 401, "Anonymous access was not denied: " + path
    assert fetch("/api/backup", data=b"")[0] == 401
    code, page = fetch("/", True)
    assert code == 200 and b"MeshMemo" in page
    csrf = re.search(rb'name="csrf-token" content="([^"]+)"', page)[1].decode()
    for asset in ("app.js", "app.css", "i18n.js", "logo.svg",
                  "locales/en.json", "locales/ru.json", "locales/uk.json"):
        assert fetch("/static/" + asset, True)[0] == 200, asset
    assert fetch("/healthz", True)[0] == 200
    assert fetch("/api/integrity", True, b"")[0] == 403
    code, integrity = fetch("/api/integrity", True, b"", {"X-CSRF-Token": csrf})
    assert code == 200 and json.loads(integrity)["result"] == "ok"
    code, payload = fetch("/api/status", True)
    assert code == 200
    status = json.loads(payload)
    print(json.dumps({"checks": "passed", "messages": status["database"]["messages"],
                      "schema": status["database"]["schema"],
                      "connection_mode": status["connection"]["mode"],
                      "connection": status["runtime"]["connection"],
                      "replay_enabled": status["settings"]["replay_enabled"]}))


if __name__ == "__main__":
    main()
