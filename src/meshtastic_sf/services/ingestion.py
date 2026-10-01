"""Ingest ordered PhoneAPI frames; only private-channel broadcast text is archived."""

from google.protobuf.message import DecodeError
from meshtastic.protobuf import mesh_pb2
from meshtastic.util import DEFAULT_KEY

from ..domain.messages import IncomingText, SaveResult
from ..domain.commands import history_command, reserved_command
from ..domain.channel_crypto import channel_settings, decode_packet
from meshtastic.protobuf import channel_pb2
from ..storage.repository import ArchiveError, HistoryRepository


class Ingestor:
    def __init__(self, repository: HistoryRepository):
        self.repository = repository
        self.channels: dict[int, bytes] = {}
        self.lora: bytes | None = None
        self.device: str | None = None
        self.ready = False
        self.channel_info: dict[int, dict] = {}
        self.last_disposition = "control"
        self._catalog_revision = -1
        self.local_channels = {}
        self.virtual_channels = {}
        self.channel_policies = {}
        self.last_frame = None

    def sync_catalog(self):
        catalog = self.repository.catalog
        if not self.ready or self._catalog_revision == catalog.revision:
            return
        self.channels = dict(self.local_channels)
        self.virtual_channels = {}
        self.channel_policies = {}
        for entry in catalog.entries():
            local = next((i for i, raw in self.local_channels.items()
                          if (lambda c: c.name == entry['name'] and c.psk == entry['key'])(channel_pb2.ChannelSettings.FromString(raw))), None)
            index = local if local is not None else entry['id'] + 8
            self.channel_policies[index] = entry
            if local is None:
                self.channels[index] = channel_settings(entry['name'], entry['key'])
                self.virtual_channels[index] = entry
            scope = self.repository.channel_scope(self.channels[index], self.lora)
            self.repository.label_channel(scope, entry['name'], index)
        self._catalog_revision = catalog.revision

    def replay_allowed(self, index):
        return self.channel_policies.get(index, {}).get('replay', True)

    def accept(self, raw: bytes, received_at: int) -> SaveResult | None:
        self.last_disposition = "control"
        if len(raw) > 512:
            raise ValueError("PhoneAPI frame is too large")
        try:
            frame = mesh_pb2.FromRadio.FromString(raw)
        except DecodeError as exc:
            raise ValueError("Invalid PhoneAPI frame") from exc
        self.last_frame = frame
        if self.ready:
            self.sync_catalog()
            if frame.HasField('packet') and frame.packet.WhichOneof('payload_variant') == 'encrypted':
                p = frame.packet
                if not p.pki_encrypted and not p.via_mqtt and p.to == 0xffffffff:
                    match = decode_packet(p, self.virtual_channels.values())
                    if match:
                        entry, decoded = match
                        p.decoded.CopyFrom(decoded)
                        p.channel = entry['id'] + 8
        kind = frame.WhichOneof("payload_variant")
        if self.ready and (kind in {"my_info", "channel"} or
                           (kind == "config" and frame.config.HasField("lora"))):
            raise ArchiveError("Node configuration changed; reconnect before continuing capture")
        if kind == "my_info":
            if frame.my_info.my_node_num in (0, 0xFFFFFFFF):
                raise ArchiveError("Missing node identity")
            self.device = f"{frame.my_info.my_node_num:08x}:{frame.my_info.device_id.hex()}"
            self.repository.bind_device(self.device)
            self.ready = False
            self.channels.clear()
            self.local_channels.clear()
            self._catalog_revision = -1
            self.channel_info.clear()
            self.lora = None
        elif kind == "channel":
            self.ready = False
            ch = frame.channel
            # Empty/one-byte keys include disabled and public/default key aliases.
            public_key = len(ch.settings.psk) == 16 and ch.settings.psk[:-1] == DEFAULT_KEY[:-1]
            eligible = bool(ch.role and len(ch.settings.psk) in (16, 32) and not public_key)
            if ch.role:
                self.channel_info[ch.index] = {"index": ch.index, "name": ch.settings.name or f"Канал {ch.index}",
                                               "eligible": eligible}
            if ch.role and len(ch.settings.psk) in (16, 32) and not public_key:
                self.channels[ch.index] = ch.settings.SerializeToString(deterministic=True)
                self.local_channels[ch.index] = self.channels[ch.index]
            else:
                self.channels.pop(ch.index, None)
        elif kind == "config" and frame.config.HasField("lora"):
            self.ready = False
            self.lora = frame.config.lora.SerializeToString(deterministic=True)
        elif kind == "config_complete_id":
            self.ready = self.device is not None and self.lora is not None
            if self.ready:
                self._catalog_revision = -1
                self.sync_catalog()
                for index, value in self.local_channels.items():
                    self.repository.label_channel(self.repository.channel_scope(value, self.lora),
                                                  self.channel_info[index]["name"], index)
        elif kind == "rebooted":
            raise ArchiveError("Node restarted; reconnect to obtain a fresh configuration")
        elif kind == "node_info" and self.device is not None:
            self.repository.label_node(frame.node_info.num, frame.node_info.user.long_name or frame.node_info.user.short_name)
        elif kind == "packet" and self.ready:
            packet = frame.packet
            if packet.WhichOneof("payload_variant") == "decoded" and packet.decoded.portnum == 4:
                try:
                    user = mesh_pb2.User.FromString(packet.decoded.payload)
                    self.repository.label_node(getattr(packet, "from"), user.long_name or user.short_name)
                except DecodeError:
                    pass
            if (packet.WhichOneof("payload_variant") != "decoded" or packet.decoded.portnum != 1
                    or packet.to != 0xFFFFFFFF or packet.pki_encrypted or packet.via_mqtt
                    or packet.channel not in self.channels):
                self.last_disposition = "excluded"
                return None
            if reserved_command(packet.decoded.payload):
                self.last_disposition = "control"
                return None
            entry = self.channel_policies.get(packet.channel)
            if entry:
                self.repository.catalog.seen(entry['id'], received_at)
            if not self.repository.get_settings()["capture_enabled"] or (entry and not entry['capture']):
                self.last_disposition = "paused"
                return None
            payload = packet.decoded.payload
            if not payload or len(payload) > 237:
                self.last_disposition = "invalid"
                return None
            try:
                payload.decode("utf-8")
            except UnicodeDecodeError:
                self.last_disposition = "invalid"
                return None
            sender = getattr(packet, "from")
            if sender in (0, 0xFFFFFFFF) or not packet.id:
                self.last_disposition = "invalid"
                return None
            scope = self.repository.channel_scope(self.channels[packet.channel], self.lora)
            result = self.repository.save(IncomingText(
                scope, sender, packet.id, packet.channel, payload,
                packet.decoded.SerializeToString(deterministic=True), raw, received_at,
                packet.rx_time, packet.decoded.reply_id, packet.decoded.emoji))
            self.last_disposition = "duplicate" if result.duplicate else "stored"
            return result
        return None
