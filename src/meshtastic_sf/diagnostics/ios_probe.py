"""Synthetic TCP node for observing iOS deduplication; never opens a radio."""

import ipaddress
import secrets
import socket
import threading
import time

from google.protobuf.message import DecodeError

from meshtastic.protobuf import channel_pb2, config_pb2, mesh_pb2, module_config_pb2, portnums_pb2

from .replay_pb2 import ReplayText

MAGIC = b"\x94\xc3"
MAX_FRAME = 512
STAGES = ("baseline", "live", "replay", "replay-again", "offline", "offline-again")


def frame(message: mesh_pb2.FromRadio | mesh_pb2.ToRadio) -> bytes:
    data = message.SerializeToString()
    if not 0 < len(data) <= MAX_FRAME:
        raise ValueError("Invalid Meshtastic frame size")
    return MAGIC + len(data).to_bytes(2, "big") + data


class FrameDecoder:
    def __init__(self):
        self.buffer = bytearray()

    def feed(self, data: bytes) -> list[bytes]:
        self.buffer.extend(data)
        result = []
        while len(self.buffer) >= 4:
            if self.buffer[:2] != MAGIC:
                del self.buffer[0]
                continue
            size = int.from_bytes(self.buffer[2:4], "big")
            if not 0 < size <= MAX_FRAME:
                del self.buffer[0]
                continue
            if len(self.buffer) < size + 4:
                break
            result.append(bytes(self.buffer[4:size + 4]))
            del self.buffer[:size + 4]
        return result


class ProbeScenario:
    def __init__(self, seed: int | None = None):
        self.seed = seed if seed is not None else secrets.randbelow(0x0FFFFFF0) + 1
        if not 1 <= self.seed <= 0x0FFFFFF0:
            raise ValueError("Invalid scenario seed")
        self.node = 0xE0000000 | self.seed
        self.author = 0xD0000000 | self.seed
        self.label = f"SFTEST-{self.seed:08x}"

    def configuration(self, nonce: int) -> list[mesh_pb2.FromRadio]:
        info = mesh_pb2.MyNodeInfo(my_node_num=self.node, nodedb_count=2,
                                  device_id=self.node.to_bytes(4, "little") * 4, pio_env="sf-test-only")
        messages = [mesh_pb2.FromRadio(my_info=info)]
        metadata = mesh_pb2.DeviceMetadata(firmware_version="2.7.26.sf-test", hw_model=12, hasWifi=True)
        messages.append(mesh_pb2.FromRadio(metadata=metadata))
        for num, name, short in [(self.node, "LOCAL TEST - NO RADIO", "TEST"),
                                 (self.author, "Synthetic SF author", "SRC")]:
            user = mesh_pb2.User(id=f"!{num:08x}", long_name=name, short_name=short, hw_model=12)
            messages.append(mesh_pb2.FromRadio(node_info=mesh_pb2.NodeInfo(num=num, user=user, channel=0)))
        for index in range(8):
            ch = channel_pb2.Channel(index=index, role=channel_pb2.Channel.PRIMARY if index == 0 else 0)
            if index == 0:
                ch.settings.name = "SFTEST"
                ch.settings.psk = b"SYNTHETIC-KEY-16"
            messages.append(mesh_pb2.FromRadio(channel=ch))
        for kind in ("device", "position", "power", "network", "display", "lora", "bluetooth", "security"):
            config = config_pb2.Config()
            getattr(config, kind).SetInParent()
            if kind == "lora":
                config.lora.region = config_pb2.Config.LoRaConfig.UA_433
                config.lora.use_preset = True
                config.lora.tx_enabled = False
            messages.append(mesh_pb2.FromRadio(config=config))
        module = module_config_pb2.ModuleConfig()
        module.store_forward.enabled = True
        module.store_forward.is_server = False
        messages.append(mesh_pb2.FromRadio(moduleConfig=module))
        messages.append(mesh_pb2.FromRadio(config_complete_id=nonce))
        return messages

    def packet(self, stage: str) -> mesh_pb2.FromRadio:
        index = STAGES.index(stage)
        packet_id = self.seed + index
        category = "BASELINE" if index == 0 else "LIVE" if index < 4 else "OFFLINE"
        text = f"{self.label} {category} Привіт Ґґ".encode("utf-8")
        data = mesh_pb2.Data(portnum=portnums_pb2.TEXT_MESSAGE_APP, payload=text)
        destination = 0xFFFFFFFF
        if index >= 2:
            original = self.seed + 1 if index < 4 else self.seed + 6
            data.portnum = portnums_pb2.STORE_FORWARD_APP
            data.payload = ReplayText(rr=9, text=text, original_id=original).SerializeToString()
            destination = self.node
        packet = mesh_pb2.MeshPacket(id=packet_id, to=destination, channel=0,
                                    decoded=data, rx_time=int(time.time()))
        setattr(packet, "from", self.author)
        return mesh_pb2.FromRadio(packet=packet)


class ProbeSession:
    def __init__(self, connection: socket.socket, scenario: ProbeScenario):
        self.connection = connection
        self.scenario = scenario
        self.ready = threading.Event()
        self.stopped = threading.Event()
        self.lock = threading.Lock()
        self.error: str | None = None

    def send(self, message: mesh_pb2.FromRadio) -> None:
        with self.lock:
            self.connection.sendall(frame(message))

    def receive(self) -> None:
        decoder = FrameDecoder()
        try:
            while not self.stopped.is_set():
                incoming = self.connection.recv(1024)
                if not incoming:
                    break
                for payload in decoder.feed(incoming):
                    request = mesh_pb2.ToRadio.FromString(payload)
                    variant = request.WhichOneof("payload_variant")
                    if variant == "want_config_id":
                        self.ready.clear()
                        for message in self.scenario.configuration(request.want_config_id):
                            self.send(message)
                        self.ready.set()
                    elif variant == "heartbeat":
                        self.send(mesh_pb2.FromRadio(queueStatus=mesh_pb2.QueueStatus(free=16, maxlen=16)))
                    elif variant == "disconnect":
                        return
                    # Client writes, positions and private settings are discarded, never persisted.
        except (OSError, ValueError, DecodeError) as exc:
            self.error = type(exc).__name__
        finally:
            self.stopped.set()

    def send_stage(self, stage: str) -> None:
        if not self.ready.is_set() or self.stopped.is_set():
            raise RuntimeError("Client configuration handshake is not active")
        self.send(self.scenario.packet(stage))


def validate_bind(value: str) -> str:
    address = ipaddress.IPv4Address(value)
    private = (ipaddress.IPv4Network("10.0.0.0/8"), ipaddress.IPv4Network("172.16.0.0/12"),
               ipaddress.IPv4Network("192.168.0.0/16"))
    if not address.is_loopback and not any(address in network for network in private):
        raise ValueError("Use a specific private LAN IPv4 address or loopback")
    return str(address)


def serve(bind: str, port: int) -> None:
    bind = validate_bind(bind)
    scenario = ProbeScenario()
    print("Synthetic node; NO RADIO. Connecting iOS switches its active node/database.")
    print("Back up the app's current node data first; see docs/ios-client-probe.md.")
    print(f"Listening on {bind}:{port}; test label {scenario.label}", flush=True)
    with socket.create_server((bind, port), backlog=1) as listener:
        listener.settimeout(600)
        connection, _ = listener.accept()
        with connection:
            session = ProbeSession(connection, scenario)
            reader = threading.Thread(target=session.receive, daemon=True)
            reader.start()
            try:
                print("Connected. Wait for SFTEST channel, then type stages in order:")
                print(", ".join(STAGES) + "; quit to exit.")
                for expected in STAGES:
                    command = input(f"{expected}> ").strip()
                    if command == "quit":
                        return
                    if command != expected:
                        raise ValueError(f"Expected {expected}; no packet sent")
                    session.send_stage(command)
                    print(f"Sent {command}. Inspect iOS before continuing.")
                print("Expected totals: BASELINE=1, LIVE=1, OFFLINE=1. Record observed counts.")
                input("Press Enter to disconnect.")
            finally:
                session.stopped.set()
                try:
                    connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                reader.join(timeout=2)
