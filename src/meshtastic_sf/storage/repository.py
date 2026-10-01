"""Single-node archive with transactional ingestion and no radio dependencies."""

import hashlib
import hmac
from importlib.resources import files
from pathlib import Path
import secrets
import sqlite3
import time

from alembic import command
from alembic.config import Config
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite import insert

from ..domain.messages import IncomingText, SaveResult
from .models import archive, messages, settings, channels, nodes, replay_ids, connection_settings


class ArchiveError(RuntimeError):
    pass


class HistoryRepository:
    def __init__(self, path: str | Path, *, max_records: int | None = None, dedupe_seconds: int | None = None):
        if (max_records is not None and max_records < 1) or (dedupe_seconds is not None and dedupe_seconds < 1):
            raise ValueError("Archive bounds must be positive")
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = sa.create_engine(sa.URL.create("sqlite", database=str(self.path)), hide_parameters=True)

        @sa.event.listens_for(self.engine, "connect")
        def configure(connection, _):
            connection.isolation_level = None
            connection.execute("PRAGMA busy_timeout=5000")
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")

        @sa.event.listens_for(self.engine, "begin")
        def begin(connection):
            connection.exec_driver_sql("BEGIN IMMEDIATE")

        try:
            with self.engine.begin() as connection:
                tables = sa.inspect(connection).get_table_names()
                if tables and "alembic_version" not in tables:
                    raise ArchiveError("Existing database is not a versioned S&F archive")
                cfg = Config()
                cfg.set_main_option("script_location", str(files("meshtastic_sf.storage.migrations")).replace("%", "%%"))
                cfg.attributes["connection"] = connection
                command.upgrade(cfg, "head")
                if connection.execute(sa.select(archive.c.id)).first() is None:
                    connection.execute(archive.insert().values(id=1, scope_secret=secrets.token_bytes(32)))
        except BaseException:
            self.close()
            raise
        from .catalog import ChannelCatalog
        try:
            self.catalog = ChannelCatalog(self)
        except BaseException:
            self.close()
            raise
        overrides = {k: v for k, v in {"max_records": max_records, "dedupe_seconds": dedupe_seconds}.items() if v is not None}
        if overrides:
            with self.engine.begin() as conn:
                conn.execute(settings.update().where(settings.c.id == 1).values(**overrides))

    def close(self):
        self.engine.dispose()

    def bind_device(self, device: str) -> None:
        if not device:
            raise ValueError("Missing device identity")
        with self.engine.begin() as conn:
            current = conn.execute(sa.select(archive.c.device).where(archive.c.id == 1)).scalar_one()
            if current is not None and current != device:
                raise ArchiveError("Archive belongs to a different node; use a separate database")
            conn.execute(archive.update().where(archive.c.id == 1).values(device=device))

    def channel_scope(self, settings: bytes, lora: bytes) -> str:
        with self.engine.connect() as conn:
            secret, device = conn.execute(sa.select(archive.c.scope_secret, archive.c.device)).one()
        if device is None:
            raise ArchiveError("Bind the archive to a node before ingesting")
        material = b"scope-v1\0" + len(settings).to_bytes(4, "big") + settings + lora
        return hmac.new(secret, material, hashlib.sha256).hexdigest()

    def save(self, item: IncomingText) -> SaveResult:
        if not (1 <= item.sender < 0xFFFFFFFF and 1 <= item.packet_id <= 0xFFFFFFFF):
            raise ValueError("Invalid message identity")
        if item.received_at <= 0 or not 0 <= item.channel_index <= 0x7fffffff or len(item.scope) != 64:
            raise ValueError("Invalid archive context")
        if not 0 < len(item.payload) <= 237 or len(item.raw_envelope) > 512 or len(item.decoded_data) > 512:
            raise ValueError("Invalid message size")
        with self.engine.begin() as conn:
            policy = conn.execute(sa.select(settings)).mappings().one()
            identity = sa.and_(messages.c.scope == item.scope, messages.c.sender == item.sender,
                               messages.c.packet_id == item.packet_id,
                               messages.c.received_at >= item.received_at - policy["dedupe_seconds"])
            candidates = conn.execute(sa.select(messages).where(identity)).mappings().all()
            for row in candidates:
                if row["decoded_data"] == item.decoded_data:
                    conn.execute(messages.update().where(messages.c.row_id == row["row_id"]).values(
                        last_seen_at=max(row["last_seen_at"], item.received_at), seen_count=row["seen_count"] + 1))
                    return SaveResult(row["row_id"], True, row["collision"])
            if conn.execute(sa.select(sa.func.count()).select_from(messages)).scalar_one() >= policy["max_records"]:
                raise ArchiveError("Archive record limit reached; apply retention or raise the limit")
            if candidates:
                conn.execute(messages.update().where(identity).values(collision=True))
            result = conn.execute(messages.insert().values(
                scope=item.scope, sender=item.sender, packet_id=item.packet_id, channel_index=item.channel_index,
                payload=item.payload, decoded_data=item.decoded_data, raw_envelope=item.raw_envelope,
                received_at=item.received_at, last_seen_at=item.received_at, rx_time=item.rx_time,
                time_quality=item.time_quality, reply_id=item.reply_id, emoji=item.emoji,
                seen_count=1, collision=bool(candidates)))
            return SaveResult(result.inserted_primary_key[0], False, bool(candidates))

    def get_settings(self) -> dict:
        with self.engine.connect() as conn:
            row = dict(conn.execute(sa.select(settings)).mappings().one())
        row.pop("id")
        return row

    def update_settings(self, values: dict) -> dict:
        if set(values) != set(self.get_settings()):
            raise ValueError("Unknown or missing settings")
        for field, lower, upper in [("max_records", 1, 10_000_000), ("dedupe_seconds", 1, 604800),
                                    ("retention_days", 0, 3650), ('replay_limit',1,100),
                                    ('replay_window_minutes',1,10080), ('replay_max_window_minutes',1,10080),
                                    ('replay_interval_seconds',5,60), ('replay_cooldown_seconds',30,3600),
                                    ('replay_heartbeat_seconds',900,86400)]:
            if type(values[field]) is not int or not lower <= values[field] <= upper:
                raise ValueError("Setting outside allowed range")
        if values['replay_window_minutes'] > values['replay_max_window_minutes']:
            raise ValueError('Default history window exceeds maximum')
        if any(type(values[k]) is not bool for k in ("capture_enabled", "replay_enabled", 'replay_heartbeat_enabled')):
            raise ValueError("Capture flag must be boolean")
        with self.engine.begin() as conn:
            conn.execute(settings.update().where(settings.c.id == 1).values(**values))
        return self.get_settings()

    def get_connection(self):
        with self.engine.connect() as conn:
            row = dict(conn.execute(sa.select(connection_settings)).mappings().one())
        row.pop('id')
        return row

    def set_connection(self, mode, port=''):
        if mode not in {'off','auto','manual'} or not isinstance(port,str) or len(port)>256 or (mode=='manual' and not port):
            raise ValueError('Invalid serial selection')
        with self.engine.begin() as conn:
            conn.execute(connection_settings.update().where(connection_settings.c.id==1).values(mode=mode,port=port,configured=True))
        return self.get_connection()

    def remember_port(self, identity):
        with self.engine.begin() as conn:
            conn.execute(connection_settings.update().where(connection_settings.c.id==1).values(identity=identity))

    def label_channel(self, scope: str, name: str, index: int):
        with self.engine.begin() as conn:
            conn.execute(insert(channels).values(scope=scope, name=name[:64], channel_index=index)
                         .on_conflict_do_update(index_elements=["scope"], set_={"name": name[:64], "channel_index": index}))

    def label_node(self, number: int, name: str):
        if not 0 < number < 0xFFFFFFFF or not name:
            return
        with self.engine.begin() as conn:
            conn.execute(insert(nodes).values(node_num=number, name=name[:80])
                         .on_conflict_do_update(index_elements=["node_num"], set_={"name": name[:80]}))

    def list_channels(self) -> list[dict]:
        with self.engine.connect() as conn:
            grouped = sa.select(messages.c.scope, sa.func.count().label("count"),
                                sa.func.max(messages.c.received_at).label("last_at")).group_by(messages.c.scope).subquery()
            known = conn.execute(sa.select(channels, sa.func.coalesce(grouped.c.count, 0).label("count"), grouped.c.last_at)
                                 .outerjoin(grouped, channels.c.scope == grouped.c.scope)
                                 .order_by(channels.c.channel_index, channels.c.name)).mappings().all()
            unknown = conn.execute(sa.select(grouped).where(~grouped.c.scope.in_(sa.select(channels.c.scope)))).mappings()
            return [dict(row) for row in known] + [{**dict(row), "name": "Архивный канал", "channel_index": None} for row in unknown]

    def chat(self, scope: str, *, before: int | None = None, query: str = "", limit: int = 100) -> list[dict]:
        if not 1 <= limit <= 200 or len(query) > 200:
            raise ValueError("Invalid message query")
        statement = sa.select(messages.c.row_id, messages.c.sender, messages.c.packet_id, messages.c.payload,
                              messages.c.received_at, messages.c.rx_time, messages.c.time_quality,
                              messages.c.seen_count, messages.c.collision, messages.c.reply_id,
                              nodes.c.name.label("sender_name")).outerjoin(nodes, messages.c.sender == nodes.c.node_num)
        statement = statement.where(messages.c.scope == scope)
        if before is not None:
            statement = statement.where(messages.c.row_id < before)
        if query:
            statement = statement.where(sa.func.instr(sa.cast(messages.c.payload, sa.Text), query) > 0)
        with self.engine.connect() as conn:
            rows = conn.execute(statement.order_by(messages.c.row_id.desc()).limit(limit)).mappings().all()
        output = []
        for row in reversed(rows):
            item = dict(row)
            item["text"] = item.pop("payload").decode("utf-8", errors="replace")
            item["sender_id"] = f'!{item["sender"]:08x}'
            item["sender_name"] = item["sender_name"] or item["sender_id"]
            output.append(item)
        return output

    def summary(self) -> dict:
        with self.engine.connect() as conn:
            row = conn.execute(sa.select(sa.func.count().label("messages"),
                                         sa.func.coalesce(sa.func.sum(messages.c.seen_count - 1), 0).label("duplicates"),
                                         sa.func.coalesce(sa.func.sum(sa.cast(messages.c.collision, sa.Integer)), 0).label("collisions"),
                                         sa.func.min(messages.c.received_at).label("oldest_at"),
                                         sa.func.max(messages.c.received_at).label("latest_at"))).mappings().one()
            version = conn.exec_driver_sql("select version_num from alembic_version").scalar_one()
        def size(suffix):
            path = Path(str(self.path) + suffix)
            try:
                return path.stat().st_size
            except FileNotFoundError:
                return 0
        return {**dict(row), "database_bytes": size(""), "wal_bytes": size("-wal"), "schema": version}

    def integrity(self) -> str:
        with self.engine.connect() as conn:
            return "ok" if conn.exec_driver_sql("PRAGMA quick_check").all() == [("ok",)] else "failed"

    def apply_retention(self) -> int:
        days = self.get_settings()["retention_days"]
        return self.prune(before=int(time.time()) - days * 86400) if days else 0

    def replay_history(self, scope: str, requester: int, since: int, until: int, limit: int = 20) -> list[dict]:
        from ..domain.commands import reserved_command
        # Ambiguous original identities cannot be made distinct in stock clients.
        # Oversize texts are omitted, never truncated or fragmented.
        from ..domain.replay import MAX_REPLAY_TEXT
        other = messages.alias("other_identity")
        ambiguous = sa.exists(sa.select(other.c.row_id).where(
            other.c.scope == messages.c.scope, other.c.sender == messages.c.sender,
            other.c.packet_id == messages.c.packet_id, other.c.row_id != messages.c.row_id))
        with self.engine.connect() as conn:
            rows = conn.execute(sa.select(messages).where(
                messages.c.scope == scope, messages.c.sender != requester,
                messages.c.received_at > since, messages.c.received_at <= until,
                messages.c.collision.is_(False), ~ambiguous, sa.func.length(messages.c.payload) <= MAX_REPLAY_TEXT,
            ).order_by(messages.c.received_at.desc(), messages.c.row_id.desc()).limit(limit)).mappings().all()
        # Most recent bounded window, sent oldest first. No delivery cursor is claimed.
        # Older databases may contain commands captured before command support.
        return [dict(row) for row in reversed(rows) if not reserved_command(row['payload'])]

    def reserve_replay_id(self, sender: int, original_id: int = 0) -> int:
        with self.engine.begin() as conn:
            # Ledger survives retention, restart and unknown USB outcomes. Bound its growth.
            if conn.execute(sa.select(sa.func.count()).select_from(replay_ids)).scalar_one() >= 1_000_000:
                raise ArchiveError("Replay identity ledger is full; replay stopped")
            for _ in range(100):
                value = secrets.randbelow(0xFFFFFFFF) + 1
                if value == original_id:
                    continue
                known = conn.execute(sa.select(messages.c.row_id).where(
                    messages.c.sender == sender, messages.c.packet_id == value).limit(1)).first()
                used = conn.execute(sa.select(replay_ids.c.packet_id).where(
                    replay_ids.c.sender == sender, replay_ids.c.packet_id == value)).first()
                if not known and not used:
                    conn.execute(replay_ids.insert().values(sender=sender, packet_id=value))
                    return value
            raise ArchiveError("Could not reserve a fresh replay identity")

    def history(self, scope: str, *, since: int = 0, limit: int = 100) -> list[dict]:
        if not 1 <= limit <= 1000:
            raise ValueError("History limit must be 1..1000")
        with self.engine.connect() as conn:
            rows = conn.execute(sa.select(messages).where(messages.c.scope == scope, messages.c.received_at >= since)
                                .order_by(messages.c.received_at, messages.c.row_id).limit(limit)).mappings()
            return [dict(row) for row in rows]

    def prune(self, *, before: int) -> int:
        if before <= 0:
            raise ValueError("Retention cutoff must be positive")
        with self.engine.begin() as conn:
            return conn.execute(messages.delete().where(messages.c.received_at < before)).rowcount

    def backup(self, destination: str | Path) -> None:
        destination = Path(destination).resolve()
        # Exclusive creation refuses accidental replacement, including symlinks.
        with destination.open("xb"):
            pass
        try:
            with sqlite3.connect(self.path) as source, sqlite3.connect(destination) as target:
                source.backup(target)
                if target.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                    raise ArchiveError("Backup integrity check failed")
        finally:
            # sqlite connection context managers commit but do not close handles.
            if "source" in locals():
                source.close()
            if "target" in locals():
                target.close()
