"""One USB owner per server, with bounded reconnect and observable capture status."""

from collections import deque
import logging
import threading
import time

from meshtastic.protobuf import mesh_pb2

from ..storage.repository import ArchiveError
from ..transport.replay import ServerSerialInterface
from .ingestion import Ingestor
from .replay import ReplayService
from ..transport.ports import available_ports, select_port


class ServerRuntime:
    def __init__(self, repository, device=None, radio_factory=ServerSerialInterface, port_provider=available_ports):
        self.repository, self.device, self.radio_factory = repository, device, radio_factory
        self.port_provider = port_provider
        if device and not repository.get_connection()['configured']:
            repository.set_connection('manual',device)
        self.reconnect_event = threading.Event()
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.thread = None
        self.events = deque(maxlen=30)
        self.replay = ReplayService(repository, event=self.event)
        from .channel_admin import ChannelAdmin
        self.channel_admin = ChannelAdmin(repository)
        self.state = {"connection": "offline", "device": device, "firmware": None,
                      "started_at": int(time.time()), "last_frame_at": None, "last_packet_at": None,
                      "frames": 0, "packets": 0, "stored": 0, "duplicates": 0,
                      "excluded": 0, "paused": 0, "invalid": 0, "channels": [], "error": None,
                      "connection_detail": None}

    def snapshot(self):
        replay = self.replay.snapshot()
        with self.lock:
            return {**self.state, "events": list(self.events), "replay": replay}

    def event(self, message):
        with self.lock:
            self.events.appendleft({"at": int(time.time()), "message": message})

    def start(self):
        for name, logger in logging.Logger.manager.loggerDict.items():
            if (name == "meshtastic" or name.startswith("meshtastic.")) and isinstance(logger, logging.Logger):
                logger.disabled = True
        self.thread = threading.Thread(target=self.run, name="archive-worker", daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=30)
            if self.thread.is_alive():
                raise RuntimeError("USB worker did not stop")

    def reconnect(self):
        self.replay.disconnect()
        self.reconnect_event.set()
        with self.lock:
            self.state['connection'] = 'connecting'

    def ports(self):
        return [{k:v for k,v in p.items() if k!='identity'} for p in self.port_provider()]

    def ingest(self, ingestor, raw, received_at):
        frame = mesh_pb2.FromRadio.FromString(raw)
        result = ingestor.accept(raw, received_at)
        if not self.stop_event.is_set():
            self.channel_admin.accept(ingestor.last_frame, ingestor)
            self.replay.accept(ingestor.last_frame, ingestor)
        with self.lock:
            self.state["frames"] += 1
            self.state["last_frame_at"] = received_at
            if frame.HasField("packet"):
                self.state["packets"] += 1
                self.state["last_packet_at"] = received_at
            if frame.HasField("metadata"):
                self.state["firmware"] = frame.metadata.firmware_version
            if ingestor.ready:
                self.state["connection"] = "connected"
                self.state["channels"] = list(ingestor.channel_info.values())
            if ingestor.last_disposition in self.state and ingestor.last_disposition != "control":
                self.state[ingestor.last_disposition] += 1
            if result and result.duplicate:
                self.state["duplicates"] += 1
        return result

    def run(self):
        delay, last_cleanup = 1, 0.0
        while not self.stop_event.is_set():
            radio = None
            try:
                if time.monotonic() - last_cleanup >= 60:
                    deleted = self.repository.apply_retention()
                    last_cleanup = time.monotonic()
                    if deleted:
                        self.event(f"Автоочистка: удалено {deleted} записей")
                self.reconnect_event.clear()
                selection = self.repository.get_connection()
                ports = self.port_provider()
                device, reason = select_port(selection, ports)
                self.device = device
                if not device:
                    with self.lock:
                        self.state.update(connection='offline' if selection['mode']=='off' else 'waiting',device=None,firmware=None,error=None,connection_detail=reason)
                    self.stop_event.wait(0.5)
                    continue
                if device:
                    with self.lock:
                        self.state.update(connection="connecting", device=device, firmware=None, error=None,connection_detail=None)
                    self.event("Подключение к USB")
                    radio = self.radio_factory(device)
                    ingestor = Ingestor(self.repository)
                remembered = False
                while not self.stop_event.is_set() and not self.reconnect_event.is_set():
                    if radio:
                        frame = radio.next_frame()
                        if frame:
                            self.ingest(ingestor, *frame)
                            if ingestor.ready:
                                delay = 1
                                if not remembered:
                                    found = next((p for p in ports if p['device']==device),None)
                                    if found:
                                        self.repository.remember_port(found['identity'])
                                    remembered = True
                        if radio.frames.empty() and not radio.failed.is_set():
                            ingestor.sync_catalog()
                            self.channel_admin.tick(radio)
                            self.replay.tick(radio, ingestor)
                    else:
                        self.stop_event.wait(0.5)
                    if time.monotonic() - last_cleanup >= 60:
                        deleted = self.repository.apply_retention()
                        last_cleanup = time.monotonic()
                        if deleted:
                            self.event(f"Автоочистка: удалено {deleted} записей")
                if radio and not radio.failed.is_set() and self.stop_event.is_set():
                    radio.close()
                    while not radio.frames.empty():
                        self.ingest(ingestor, *radio.frames.get_nowait())
            except Exception as exc:
                # Only curated archive errors are safe to display; SDK exceptions may contain configuration.
                messages = {'Archive belongs':'Подключена другая нода. Выберите прежнее устройство или отдельную базу.',
                            'Archive record limit':'Архив заполнен. Увеличьте лимит в настройках.',
                            'Node configuration changed':'Настройки ноды изменились. Восстанавливаем соединение.',
                            'Node restarted':'Нода перезапущена. Восстанавливаем соединение.'}
                message = next((value for key,value in messages.items() if isinstance(exc,ArchiveError) and str(exc).startswith(key)),
                               'Не удалось подключиться к ноде или сохранить данные. Проверьте USB и свободное место.')
                with self.lock:
                    self.state.update(connection="error", error=message)
                self.event(message)
            finally:
                self.replay.disconnect()
                self.channel_admin.replies.clear()
                if radio:
                    try:
                        radio.close()
                    except Exception:
                        pass
            if self.reconnect_event.is_set():
                continue
            if self.stop_event.wait(delay):
                break
            delay = min(delay * 2, 30)
        with self.lock:
            self.state["connection"] = "stopped"
