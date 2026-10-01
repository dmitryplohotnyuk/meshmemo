from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import sqlite3
import os
from pathlib import Path
import subprocess
import sys

import pytest
import sqlalchemy as sa

from meshtastic_sf.domain.messages import IncomingText
from meshtastic_sf.storage.repository import ArchiveError, HistoryRepository


@pytest.fixture
def repo(tmp_path):
    result = HistoryRepository(tmp_path / "history.db")
    result.bind_device("synthetic-node")
    yield result
    result.close()


def message(repo, **changes):
    item = IncomingText(repo.channel_scope(b"private-settings", b"lora"), 0xFFFFFFFF - 1,
                        0xFFFFFFFF, 0, "Привіт Ґґ".encode(), b"decoded", b"envelope",
                        1_800_000_000, 1_800_000_000)
    return replace(item, **changes)


def test_durable_deduplication_with_concurrent_writers(repo):
    item = message(repo)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: repo.save(item), range(12)))
    assert sum(not result.duplicate for result in results) == 1
    repo.close()
    reopened = HistoryRepository(repo.path)
    try:
        rows = reopened.history(item.scope)
        assert len(rows) == 1
        assert rows[0]["seen_count"] == 12
        assert rows[0]["payload"].decode() == "Привіт Ґґ"
        assert rows[0]["raw_envelope"] == b"envelope"
        assert reopened.save(replace(item, raw_envelope=b"different-rssi")).duplicate
    finally:
        reopened.close()


def test_scope_device_binding_and_id_collisions(repo):
    item = message(repo)
    first = repo.save(item)
    conflict = repo.save(replace(item, payload=b"other", decoded_data=b"different"))
    assert conflict.collision and not conflict.duplicate
    assert {r["row_id"] for r in repo.history(item.scope)} == {first.row_id, conflict.row_id}
    assert all(r["collision"] for r in repo.history(item.scope))
    assert not repo.save(replace(item, sender=123)).collision
    other_scope = repo.channel_scope(b"new-key-or-name", b"lora")
    assert not repo.save(replace(item, scope=other_scope)).collision
    assert other_scope != item.scope
    with pytest.raises(ArchiveError, match="different node"):
        repo.bind_device("another-node")


def test_identity_horizon_and_retention_use_host_time(repo):
    item = message(repo, rx_time=1_900_000_000)
    repo.save(item)
    later = replace(item, received_at=item.received_at + 86401)
    assert not repo.save(later).duplicate
    assert all(row["time_quality"] == "suspect" for row in repo.history(item.scope))
    assert repo.prune(before=item.received_at + 1) == 1
    assert len(repo.history(item.scope)) == 1
    assert message(repo, rx_time=0).time_quality == "missing"


def test_record_limit_does_not_overwrite_or_block_duplicates(tmp_path):
    repo = HistoryRepository(tmp_path / "small.db", max_records=1)
    try:
        repo.bind_device("synthetic")
        item = message(repo)
        repo.save(item)
        assert repo.save(item).duplicate
        with pytest.raises(ArchiveError, match="record limit"):
            repo.save(replace(item, packet_id=10))
        assert len(repo.history(item.scope)) == 1
    finally:
        repo.close()


def test_wal_backup_restore_and_no_overwrite(repo, tmp_path):
    item = message(repo)
    repo.save(item)
    destination = tmp_path / "backup.db"
    repo.backup(destination)
    with pytest.raises(FileExistsError):
        repo.backup(destination)
    restored = HistoryRepository(destination)
    try:
        assert restored.history(item.scope)[0]["payload"] == item.payload
        assert restored.channel_scope(b"private-settings", b"lora") == item.scope
    finally:
        restored.close()
    with sqlite3.connect(destination) as conn:
        assert conn.execute("pragma integrity_check").fetchone()[0] == "ok"
        assert conn.execute("select version_num from alembic_version").fetchone()[0] == "0005_catalog"


def test_transaction_rollback_and_foreign_database_rejection(repo, tmp_path):
    with pytest.raises(RuntimeError):
        with repo.engine.begin() as conn:
            conn.execute(sa.text("UPDATE archive SET device='wrong'"))
            raise RuntimeError("simulated failure before commit")
    repo.bind_device("synthetic-node")
    foreign = tmp_path / "foreign.db"
    with sqlite3.connect(foreign) as conn:
        conn.execute("create table unrelated(value text)")
    with pytest.raises(ArchiveError, match="not a versioned"):
        HistoryRepository(foreign)


def test_committed_message_survives_abrupt_process_exit(repo):
    item = message(repo)
    repo.save(item)
    child = """
import os, sys
from meshtastic_sf.storage.repository import HistoryRepository
r = HistoryRepository(sys.argv[1])
c = r.engine.connect()
t = c.begin()
c.exec_driver_sql('DELETE FROM messages')
os._exit(17)
"""
    environment = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}
    result = subprocess.run([sys.executable, "-c", child, str(repo.path)], env=environment,
                            capture_output=True, timeout=20)
    assert result.returncode == 17, result.stderr.decode(errors="replace")
    assert repo.history(item.scope)[0]["payload"] == item.payload
