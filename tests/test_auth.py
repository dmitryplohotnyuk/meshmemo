import base64
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from meshtastic_sf.config import load_config, DEFAULT_PORT
from meshtastic_sf.web.application import create_app

PASSWORD = "synthetic-admin-password-Ґґ"


def authorization(password=PASSWORD):
    return {"Authorization": "Basic " + base64.b64encode(("admin:" + password).encode()).decode()}


def test_admin_requires_password_for_html_assets_reads_and_writes(tmp_path):
    app = create_app(str(tmp_path / "archive.db"), admin_password=PASSWORD)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        for method, path in [("GET", "/"), ("GET", "/static/app.js"), ("GET", "/healthz"),
                             ("GET", "/api/status"), ("GET", "/api/channels"),
                             ("GET", "/api/messages"), ("GET", "/api/ports"),
                             ("POST", "/api/backup"), ("POST", "/api/settings"),
                             ("POST", "/api/connection"), ("POST", "/api/integrity")]:
            response = client.request(method, path)
            assert response.status_code == 401
            assert response.headers["www-authenticate"].startswith("Basic ")
            assert response.headers["cache-control"] == "no-store"
        for header in ("Basic !!", "Bearer abc", "Basic " + "x" * 5000):
            assert client.get("/", headers={"Authorization": header}).status_code == 401
        assert client.get("/", headers=authorization("wrong-password")).status_code == 401
        assert client.get("/", headers=authorization()).status_code == 200
        assert client.post("/api/backup", headers=authorization()).status_code == 403
        assert not (tmp_path / "backups").exists()


def test_failed_logins_are_throttled_and_expire(tmp_path, monkeypatch):
    app = create_app(str(tmp_path / "archive.db"), admin_password=PASSWORD)
    clock = [100.0]
    monkeypatch.setattr("meshtastic_sf.web.auth.time", SimpleNamespace(monotonic=lambda: clock[0]))
    with TestClient(app, base_url="http://127.0.0.1") as client:
        for _ in range(10):
            assert client.get("/", headers=authorization("incorrect")).status_code == 401
        blocked = client.get("/", headers=authorization())
        assert blocked.status_code == 429 and int(blocked.headers["retry-after"]) > 0
        clock[0] += 61
        assert client.get("/", headers=authorization()).status_code == 200


def test_remote_access_still_requires_password_and_trusted_host(tmp_path):
    app = create_app(str(tmp_path / "remote.db"), admin_password=PASSWORD,
                     allow_remote=True, allowed_hosts=("192.0.2.5",))
    with TestClient(app, base_url="http://192.0.2.5", client=("192.0.2.10", 1234)) as client:
        assert client.get("/").status_code == 401
        assert client.get("/api/status", headers=authorization()).status_code == 200
        assert client.get("/", headers={**authorization(), "Host": "attacker.example"}).status_code == 400
    app = create_app(str(tmp_path / "local.db"), admin_password=PASSWORD)
    with TestClient(app, base_url="http://127.0.0.1", client=("192.0.2.10", 1234)) as client:
        assert client.get("/", headers=authorization()).status_code == 403


def config_file(tmp_path, text):
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")
    path.chmod(0o600)
    return str(path)


def test_private_config_defaults_paths_and_secret_redaction(tmp_path):
    config = load_config(config_file(tmp_path, '[admin]\npassword = "' + PASSWORD + '"'))
    assert config.port == DEFAULT_PORT == 18765
    assert Path(config.database) == tmp_path / "data" / "history.db"
    assert PASSWORD not in repr(config)
    assert config.password == PASSWORD
    with pytest.raises(ValueError, match="Cannot read config"):
        load_config(str(tmp_path / "missing.toml"))


@pytest.mark.parametrize("text", [
    '', '[admin]\npassword="short"', '[admin]\npassword="                "',
    '[admin]\npassword="secret-value-leaked-if-parser-error',
    '[admin]\npassword="valid-test-password"\n[server]\nport=true',
    '[admin]\npassword="valid-test-password"\n[server]\nport=0',
    '[admin]\npassword="valid-test-password"\n[server]\nhost="localhost"',
    '[admin]\npassword="valid-test-password"\n[server]\nallowed_hosts=["*"]',
    '[admin]\npassword="valid-test-password"\n[server]\nunknown=true',
])
def test_invalid_configuration_fails_closed(tmp_path, text):
    with pytest.raises(ValueError) as error:
        load_config(config_file(tmp_path, text))
    assert "secret-value" not in str(error.value)


def test_password_cannot_be_disabled(tmp_path):
    with pytest.raises(TypeError):
        create_app(str(tmp_path / "noauth.db"))
    with pytest.raises(ValueError):
        create_app(str(tmp_path / "blank.db"), admin_password="")
