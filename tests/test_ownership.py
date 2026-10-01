import os
from pathlib import Path
import subprocess
import sys

from fastapi.testclient import TestClient
from functools import partial
import pytest

from meshtastic_sf.services.ownership import ArchiveInUse, ArchiveOwner
from meshtastic_sf.web.application import create_app
create_app = partial(create_app, admin_password="test-only-password")
TestClient = partial(TestClient, headers={"Authorization": "Basic YWRtaW46dGVzdC1vbmx5LXBhc3N3b3Jk"})


def child(code, path):
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}
    return subprocess.run([sys.executable, "-c", code, str(path)], env=env,
                          capture_output=True, text=True, timeout=15)


def test_other_process_cannot_take_owned_archive(tmp_path):
    path = tmp_path / "archive.db"
    code = "from meshtastic_sf.services.ownership import ArchiveOwner; import sys; ArchiveOwner(sys.argv[1]).__enter__()"
    with ArchiveOwner(path):
        result = child(code, path)
        assert result.returncode != 0
        assert "ArchiveInUse" in result.stderr
        # Another database remains independent.
        assert child(code, tmp_path / "other.db").returncode == 0
    assert child(code, path).returncode == 0


def test_process_exit_releases_lock_without_cleanup(tmp_path):
    path = tmp_path / "archive.db"
    code = "from meshtastic_sf.services.ownership import ArchiveOwner; import sys, os; owner=ArchiveOwner(sys.argv[1]); owner.__enter__(); os._exit(23)"
    assert child(code, path).returncode == 23
    with ArchiveOwner(path):
        assert Path(str(path) + ".lock").exists()


def test_server_ownership_and_health_are_independent_of_usb(tmp_path):
    path = str(tmp_path / "archive.db")
    app = create_app(path)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        assert client.get("/healthz").json() == {"status": "ok"}
        assert client.get("/api/status").json()["connection"]["mode"] == "off"
        with pytest.raises(ArchiveInUse):
            with TestClient(create_app(path)):
                pytest.fail("Second server acquired an owned archive")
        assert client.get("/healthz").status_code == 200
        app.state.runtime.stop()
        assert client.get("/healthz").status_code == 503
    with TestClient(create_app(path), base_url="http://127.0.0.1") as client:
        assert client.get("/healthz").status_code == 200


def test_failed_start_releases_archive(tmp_path):
    path = str(tmp_path / "archive.db")

    def fail(*args):
        raise RuntimeError("startup failed")

    with pytest.raises(RuntimeError, match="startup failed"):
        with TestClient(create_app(path, runtime_factory=fail)):
            pass
    with TestClient(create_app(path), base_url="http://127.0.0.1") as client:
        assert client.get("/healthz").status_code == 200
