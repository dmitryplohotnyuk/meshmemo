import re
import sqlite3
import time
from importlib.resources import files

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from functools import partial
import sqlalchemy as sa

from meshtastic_sf.diagnostics.ios_probe import ProbeScenario
from meshtastic_sf.services.ingestion import Ingestor
from meshtastic_sf.services.runtime import ServerRuntime
from meshtastic_sf.storage.models import archive, messages
from meshtastic_sf.storage.repository import HistoryRepository
from meshtastic_sf.web.application import create_app
create_app = partial(create_app, admin_password="test-only-password")
TestClient = partial(TestClient, headers={"Authorization": "Basic YWRtaW46dGVzdC1vbmx5LXBhc3N3b3Jk"})


def configure(app):
    scenario = ProbeScenario(123)
    ingestor = Ingestor(app.state.repository)
    now = int(time.time())
    for frame in scenario.configuration(7):
        app.state.runtime.ingest(ingestor, frame.SerializeToString(), now)
    return ingestor, scenario, now


def token(client):
    page = client.get("/")
    assert page.status_code == 200
    return {"X-CSRF-Token": re.search(r'name="csrf-token" content="([^"]+)"', page.text)[1]}


def test_admin_archive_search_pagination_and_backup(tmp_path):
    app = create_app(str(tmp_path / "history.db"))
    with TestClient(app, base_url="http://127.0.0.1") as client:
        headers = token(client)
        assert client.get("/static/app.js").status_code == 200
        assert client.get("/static/app.css").status_code == 200
        ingestor, scenario, now = configure(app)
        for i in range(105):
            frame = scenario.packet("live")
            frame.packet.id = i + 1
            frame.packet.decoded.payload = ("Привіт Ґґ 100% <script>alert(1)</script>" if i == 0 else f"Message {i}").encode()
            app.state.runtime.ingest(ingestor, frame.SerializeToString(), now + i)
        app.state.runtime.ingest(ingestor, frame.SerializeToString(), now + 106)
        channels = client.get("/api/channels").json()
        assert channels[0]["count"] == 105
        scope = channels[0]["scope"]
        recent = client.get("/api/messages", params={"scope": scope}).json()
        assert len(recent) == 100 and recent[0]["text"] == "Message 5"
        older = client.get("/api/messages", params={"scope": scope, "before": recent[0]["row_id"]}).json()
        assert len(older) == 5 and "Привіт Ґґ" in older[0]["text"]
        search = client.get("/api/messages", params={"scope": scope, "q": "%"}).json()
        assert len(search) == 1  # literal search, not SQL wildcards
        assert "raw_envelope" not in str(recent) and "scope_secret" not in str(channels)
        status = client.get("/api/status").json()
        assert status["runtime"]["stored"] == 105
        assert status["runtime"]["duplicates"] == 1
        assert status["database"]["duplicates"] == 1
        assert client.post("/api/integrity", headers=headers).json() == {"result": "ok"}
        backup = client.post("/api/backup", headers=headers)
        assert backup.content.startswith(b"SQLite format 3\0")
        restored = tmp_path / "restored.db"
        restored.write_bytes(backup.content)
        with sqlite3.connect(restored) as db:
            assert db.execute("select count(*) from messages").fetchone()[0] == 105


def test_settings_protection_pause_retention_and_persistence(tmp_path):
    path = tmp_path / "history.db"
    app = create_app(str(path))
    with TestClient(app, base_url="http://127.0.0.1") as client:
        headers = token(client)
        assert client.get("/", headers={"Host": "attacker.example"}).status_code == 400
        policy = client.get("/api/status").json()["settings"]
        assert client.post("/api/settings", json=policy).status_code == 403
        assert client.post("/api/settings", json=policy, headers={**headers, "Origin": "https://attacker.example"}).status_code == 403
        assert client.post("/api/settings", json={**policy, "max_records": "100"}, headers=headers).status_code == 422
        ingestor, scenario, now = configure(app)
        raw = scenario.packet("live").SerializeToString()
        app.state.runtime.ingest(ingestor, raw, now - 3 * 86400)
        paused = {**policy, "capture_enabled": False}
        assert client.post("/api/settings", json=paused, headers=headers).status_code == 200
        assert app.state.runtime.ingest(ingestor, raw, now) is None
        assert app.state.runtime.snapshot()["paused"] == 1
        retention = {**paused, "retention_days": 1}
        assert client.post("/api/settings", json=retention, headers=headers).status_code == 409
        assert client.post("/api/settings", json={**retention, "confirm_retention": True}, headers=headers).status_code == 200
        assert app.state.repository.apply_retention() == 1
    reopened = HistoryRepository(path)
    try:
        assert reopened.get_settings() == retention
        assert reopened.summary()["messages"] == 0
    finally:
        reopened.close()


def test_migration_preserves_v1_archive(tmp_path):
    path = tmp_path / "old.db"
    engine = sa.create_engine("sqlite:///" + str(path))
    cfg = Config()
    cfg.set_main_option("script_location", str(files("meshtastic_sf.storage.migrations")))
    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "0001_history")
        connection.execute(archive.insert().values(id=1, device="old-node", scope_secret=b"s" * 32))
        connection.execute(messages.insert().values(scope="a" * 64, sender=123, packet_id=9, channel_index=0,
            payload="Старая запись".encode(), decoded_data=b"data", raw_envelope=b"raw", received_at=1234,
            last_seen_at=1234, rx_time=0, time_quality="missing", reply_id=0, emoji=0, seen_count=2, collision=False))
    engine.dispose()
    repo = HistoryRepository(path)
    try:
        assert repo.summary()["schema"] == "0005_catalog"
        assert repo.chat("a" * 64)[0]["text"] == "Старая запись"
        assert repo.get_settings()["retention_days"] == 0
        assert repo.get_settings()["replay_enabled"] is False
        assert repo.list_channels()[0]["count"] == 1
    finally:
        repo.close()


def test_runtime_reconnects_and_stops(tmp_path):
    import queue
    import threading

    calls = []
    scenario = ProbeScenario(456)
    class Radio:
        def __init__(self, device):
            calls.append(self)
            self.frames = queue.Queue()
            self.failed = threading.Event()
            self.closed = False
            for frame in [*scenario.configuration(7), scenario.packet("live")]:
                self.frames.put((frame.SerializeToString(), int(time.time())))

        def next_frame(self):
            if not self.frames.empty():
                return self.frames.get_nowait()
            if len(calls) == 1:
                self.failed.set()
                raise OSError("synthetic disconnect")
            time.sleep(0.01)

        def close(self):
            self.closed = True

    repo = HistoryRepository(tmp_path / "runtime.db")
    runtime = ServerRuntime(repo, "SYNTHETIC", radio_factory=Radio)
    runtime.start()
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and runtime.snapshot()["duplicates"] != 1:
            time.sleep(0.02)
        assert runtime.snapshot()["stored"] == 1
        assert runtime.snapshot()["duplicates"] == 1
        assert len(calls) == 2 and calls[0].closed
    finally:
        runtime.stop()
        repo.close()
    assert calls[-1].closed


def test_web_toggle_persists_and_cancels_pending_history(tmp_path):
    from test_replay import request
    app = create_app(str(tmp_path / 'replay.db'))
    with TestClient(app, base_url='http://127.0.0.1') as client:
        headers = token(client)
        policy = client.get('/api/status').json()['settings']
        assert policy['replay_enabled'] is False
        assert client.post('/api/settings', json={**policy, 'replay_enabled': 'true'}, headers=headers).status_code == 422
        enabled = {**policy, 'replay_enabled': True}
        assert client.post('/api/settings', json=enabled, headers=headers).json()['replay_enabled'] is True
        ingestor, scenario, now = configure(app)
        app.state.runtime.replay.accept(request(scenario), ingestor)
        assert app.state.runtime.replay.job is not None
        assert client.post('/api/settings', json=policy, headers=headers).json()['replay_enabled'] is False
        assert app.state.runtime.replay.job is None
        assert client.get('/api/status').json()['runtime']['replay']['state'] == 'disabled'
