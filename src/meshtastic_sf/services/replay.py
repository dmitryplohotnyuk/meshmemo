"""Bounded request-driven S&F v1 scheduler. No radio writes while disabled."""
from collections import OrderedDict, deque
from dataclasses import dataclass
import threading
import time

from google.protobuf.message import DecodeError
from meshtastic.protobuf import storeforward_pb2

from ..domain.commands import history_command
from ..transport.client import BridgeUnavailable, BridgeRejected
from ..transport.protocol import Status
from ..transport.replay import Control, FreshReplay, ReplayBridgeClient, context_digest

SF = storeforward_pb2.StoreAndForward
LIMIT, WINDOW_MINUTES, MAX_WINDOW_MINUTES, INTERVAL, JOB_TIMEOUT = 20, 1440, 10080, 5.0, 180.0
HEARTBEAT_SECONDS = 900


@dataclass
class Job:
    requester: int
    channel: int
    scope: str
    context: bytes
    packets: deque
    deadline: float


class ReplayService:
    def __init__(self, repository, event=lambda message: None, clock=time.monotonic, wall=time.time,
                 client_factory=ReplayBridgeClient):
        self.repository, self.event, self.clock, self.wall = repository, event, clock, wall
        self.client_factory = client_factory
        self.lock = threading.RLock()
        self.client = None
        self.job = None
        self.controls = deque(maxlen=4)
        self.seen = OrderedDict()
        self.cooldown = OrderedDict()
        self.next_send = 0.0
        self.blocked_until = 0.0
        self.next_heartbeat = 0.0
        self.started = clock()
        self.state = {"state": "disabled", "requests": 0, "submitted": 0, "replayed": 0,
                      "cancelled": 0, "error": None}

    def snapshot(self):
        with self.lock:
            policy = self.repository.get_settings()
            return {**self.state, "remaining": len(self.job.packets) if self.job else 0,
                    "limit": policy['replay_limit'], "interval_seconds": policy['replay_interval_seconds']}

    def cancel(self, state="idle"):
        with self.lock:
            if self.job:
                self.state["cancelled"] += 1
            self.job = None
            self.controls.clear()
            self.state["state"] = state

    def disconnect(self):
        with self.lock:
            self.cancel("disconnected")
            self.client = None
            self.next_heartbeat = 0.0

    def _enabled(self):
        return self.repository.get_settings()["replay_enabled"]

    def accept(self, frame, ingestor):
        if not ingestor.ready or not frame.HasField("packet"):
            return
        p = frame.packet
        if p.WhichOneof("payload_variant") != "decoded" or p.decoded.portnum not in (1, 65):
            return
        command = history_command(p.decoded.payload) if p.decoded.portnum == 1 else None
        if p.decoded.portnum == 1 and (command is None or command.hours is None):
            return
        with self.lock:
            ingestor.sync_catalog()
            policy = self.repository.get_settings()
            if not self._enabled():
                self.cancel("disabled")
                return
            server = int(ingestor.device.split(":")[0], 16)
            requester = getattr(p, "from")
            destination = 0xFFFFFFFF if command is not None else server
            if (p.to != destination or requester in (0, server, 0xFFFFFFFF) or not p.id
                    or p.pki_encrypted or p.via_mqtt or p.channel not in ingestor.channels or not ingestor.replay_allowed(p.channel)):
                return
            if command is not None:
                sf = SF(rr=65)
                sf.history.window = min(command.hours * 60, policy['replay_max_window_minutes'])
            else:
                try:
                    sf = SF.FromString(p.decoded.payload)
                except DecodeError:
                    return
            if sf.rr not in (64, 65, 66, 67, 68, 106):
                return
            if sf.rr == 65 and sf.WhichOneof("variant") not in (None, "history"):
                return
            scope = self.repository.channel_scope(ingestor.channels[p.channel], ingestor.lora)
            now = self.clock()
            key = (scope, requester, p.id)
            if key in self.seen and now - self.seen[key] < 120:
                return
            self.seen[key] = now
            self.seen.move_to_end(key)
            while len(self.seen) > 512:
                self.seen.popitem(last=False)
            if sf.rr in (64, 106):
                if self.job and (self.job.scope, self.job.requester) == (scope, requester):
                    self.cancel()
                    self.event("Выдача истории отменена клиентом")
                return
            if sf.rr == 68:
                return
            if now < self.blocked_until:
                return
            rate_key = (scope, requester)
            if rate_key in self.cooldown and now < self.cooldown[rate_key]:
                return
            self.cooldown[rate_key] = now + (policy['replay_cooldown_seconds'] if sf.rr == 65 else policy['replay_interval_seconds'])
            self.cooldown.move_to_end(rate_key)
            while len(self.cooldown) > 256:
                self.cooldown.popitem(last=False)
            self.state["requests"] += 1
            context = context_digest(ingestor.channels[p.channel], ingestor.lora)
            if self.job:
                if len(self.controls) < self.controls.maxlen:
                    self.controls.append((requester, p.channel, scope, context, SF(rr=5)))
                return
            if sf.rr == 65:
                window = min(sf.history.window or policy['replay_window_minutes'], policy['replay_max_window_minutes'])
                until = int(self.wall())
                rows = self.repository.replay_history(scope, requester, until - window * 60, until, policy['replay_limit'])
                if p.channel in ingestor.virtual_channels:
                    rows = [row for row in rows if len(row["payload"]) <= 160]
                packets = deque(rows)
                if command is None:
                    # Native Client History keeps its protocol metadata; chat commands
                    # return only archived text, without a visible statistics message.
                    response = SF(rr=6)
                    response.history.history_messages = len(rows)
                    response.history.window = window * 60000
                    response.history.last_request = 0
                    packets.appendleft(response)
                if not packets:
                    self.state.update(state="idle", error=None)
                    self.event("Запрос истории принят: 0 сообщений")
                    return
                deadline = max(JOB_TIMEOUT, (len(rows) + 4) * policy['replay_interval_seconds'] + 60)
                self.job = Job(requester, p.channel, scope, context, packets, now + deadline)
                self.state.update(state="queued", error=None)
                self.event(f"Запрос истории принят: {len(rows)} сообщений")
            else:
                response = SF(rr=4 if sf.rr == 67 else 7)
                if sf.rr == 66:
                    channel = next(c for c in self.repository.list_channels() if c["scope"] == scope)
                    count = min(channel["count"], 0xFFFFFFFF)
                    response.stats.messages_total = response.stats.messages_saved = count
                    response.stats.messages_max = self.repository.get_settings()["max_records"]
                    response.stats.up_time = min(int(now - self.started), 0xFFFFFFFF)
                    response.stats.return_max = policy['replay_limit']
                    response.stats.return_window = policy['replay_window_minutes']
                    response.stats.heartbeat = policy['replay_heartbeat_enabled']
                if len(self.controls) < self.controls.maxlen:
                    self.controls.append((requester, p.channel, scope, context, response))

    def tick(self, radio, ingestor):
        with self.lock:
            ingestor.sync_catalog()
            policy = self.repository.get_settings()
            if not self._enabled():
                self.cancel("disabled")
                self.client = None
                self.state["error"] = None
                self.next_heartbeat = 0.0
                return
            if not ingestor.ready:
                self.cancel("disconnected")
                return
            now = self.clock()
            if policy['replay_heartbeat_enabled'] and now >= self.next_heartbeat and now >= self.blocked_until and not self.job and not self.controls:
                for channel, config in ingestor.channels.items():
                    if channel in ingestor.virtual_channels or not ingestor.replay_allowed(channel):
                        continue
                    heartbeat = SF(rr=2)
                    heartbeat.heartbeat.period = policy['replay_heartbeat_seconds']
                    if len(self.controls) < self.controls.maxlen:
                        self.controls.append((0xFFFFFFFF, channel, self.repository.channel_scope(config, ingestor.lora),
                                              context_digest(config, ingestor.lora), heartbeat))
                self.next_heartbeat = now + policy['replay_heartbeat_seconds']
            if self.job and now >= self.job.deadline:
                self.cancel()
                self.event("Истекло время выдачи истории")
            if not self.job and not self.controls:
                if self.state["state"] != "blocked":
                    self.state["state"] = "idle"
                return
            if now < self.next_send or now < self.blocked_until:
                return
            job = self.job
            if job:
                requester, channel, scope, context = job.requester, job.channel, job.scope, job.context
                item = job.packets[0]
            else:
                requester, channel, scope, context, item = self.controls[0]
            if (channel not in ingestor.channels or not ingestor.replay_allowed(channel) or self.repository.channel_scope(ingestor.channels[channel], ingestor.lora) != scope):
                self.cancel()
                return
            try:
                if self.client is None:
                    self.client = self.client_factory(radio.exchange)
                    self.client.connect()
                server = int(ingestor.device.split(":")[0], 16)
                if isinstance(item, dict):
                    message = FreshReplay(item["sender"], item["packet_id"], requester, channel, item["payload"],
                        self.repository.reserve_replay_id(item["sender"], item["packet_id"]), context,
                        item["reply_id"], bool(item["emoji"]))
                else:
                    message = Control(requester, channel, self.repository.reserve_replay_id(server), context, item.SerializeToString())
                if channel in ingestor.virtual_channels:
                    from ..transport.replay import encrypted_history_reply
                    message = encrypted_history_reply(item, ingestor.virtual_channels[channel],
                        item['sender'] if isinstance(item,dict) else server, requester, message.outer_id, ingestor.lora)
                self.client.send(message)
            except BridgeRejected as exc:
                if exc.response.status == Status.BUSY:
                    self.next_send = now + policy['replay_interval_seconds']
                    return
                self._failed()
                return
            except Exception:
                # USB errors can carry private payload/configuration: never expose their text.
                self._failed()
                return
            self.next_send = self.clock() + policy['replay_interval_seconds']
            self.state["submitted"] += 1
            if isinstance(item, dict):
                self.state["replayed"] += 1
            if job:
                job.packets.popleft()
                if not job.packets:
                    self.job = None
                    self.state["state"] = "idle"
                    self.event("Выдача истории передана USB-ноде; доставка по радио не подтверждена")
                else:
                    self.state["state"] = "sending"
            else:
                self.controls.popleft()

    def _failed(self):
        self.cancel("blocked")
        self.client = None
        self.blocked_until = self.clock() + 30
        self.state["error"] = "Не удалось выдать историю. Проверьте подключение ноды и совместимость прошивки."
        self.event(self.state["error"])
