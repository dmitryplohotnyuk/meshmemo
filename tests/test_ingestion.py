import queue
import threading

import pytest
from meshtastic.protobuf import config_pb2, mesh_pb2
from meshtastic.serial_interface import SerialInterface
from meshtastic.util import DEFAULT_KEY

from meshtastic_sf.diagnostics.ios_probe import ProbeScenario
from meshtastic_sf.services.ingestion import Ingestor
from meshtastic_sf.storage.repository import ArchiveError, HistoryRepository
from meshtastic_sf.transport.capture import CaptureSerialInterface


@pytest.fixture
def configured(tmp_path):
    repo = HistoryRepository(tmp_path / "history.db")
    scenario = ProbeScenario(123)
    ingestor = Ingestor(repo)
    for frame in scenario.configuration(7):
        ingestor.accept(frame.SerializeToString(), 1_800_000_000)
    assert ingestor.ready
    yield repo, ingestor, scenario
    repo.close()


def test_ingests_only_original_broadcast_text(configured):
    repo, ingestor, scenario = configured
    raw = scenario.packet("live").SerializeToString()
    first = ingestor.accept(raw, 1_800_000_000)
    assert first and not first.duplicate
    assert ingestor.accept(raw, 1_800_000_001).duplicate
    assert ingestor.accept(scenario.packet("replay").SerializeToString(), 1_800_000_002) is None
    frame = scenario.packet("live")
    frame.packet.to = scenario.node
    assert ingestor.accept(frame.SerializeToString(), 1_800_000_002) is None
    frame.packet.to = 0xFFFFFFFF
    frame.packet.pki_encrypted = True
    assert ingestor.accept(frame.SerializeToString(), 1_800_000_002) is None
    frame.packet.pki_encrypted = False
    frame.packet.via_mqtt = True
    assert ingestor.accept(frame.SerializeToString(), 1_800_000_002) is None
    frame.packet.via_mqtt = False
    frame.packet.decoded.payload = b"\xff"
    assert ingestor.accept(frame.SerializeToString(), 1_800_000_002) is None


@pytest.mark.parametrize("key", [b"", b"\x01", DEFAULT_KEY, DEFAULT_KEY[:-1] + b"\x02"])
def test_public_or_disabled_channels_are_excluded(tmp_path, key):
    repo = HistoryRepository(tmp_path / "history.db")
    try:
        ingestor = Ingestor(repo)
        scenario = ProbeScenario(123)
        for frame in scenario.configuration(7):
            if frame.HasField("channel") and frame.channel.index == 0:
                frame.channel.settings.psk = key
            ingestor.accept(frame.SerializeToString(), 1_800_000_000)
        assert ingestor.accept(scenario.packet("live").SerializeToString(), 1_800_000_000) is None
    finally:
        repo.close()


def test_reconfiguration_fails_closed_and_new_key_changes_scope(configured):
    repo, ingestor, scenario = configured
    before = repo.channel_scope(ingestor.channels[0], ingestor.lora)
    config = mesh_pb2.FromRadio(config=config_pb2.Config(lora=config_pb2.Config.LoRaConfig()))
    with pytest.raises(ArchiveError, match="configuration changed"):
        ingestor.accept(config.SerializeToString(), 1_800_000_000)
    ingestor = Ingestor(repo)
    assert ingestor.accept(scenario.packet("live").SerializeToString(), 1_800_000_000) is None
    for frame in scenario.configuration(8):
        if frame.HasField("channel") and frame.channel.index == 0:
            frame.channel.settings.psk = b"different-key-16"
        ingestor.accept(frame.SerializeToString(), 1_800_000_000)
    after = repo.channel_scope(ingestor.channels[0], ingestor.lora)
    assert before != after
    assert not ingestor.accept(scenario.packet("live").SerializeToString(), 1_800_000_000).duplicate


def test_capture_adapter_preserves_bytes_and_fails_on_overflow(monkeypatch):
    radio = CaptureSerialInterface.__new__(CaptureSerialInterface)
    radio.frames = queue.Queue(maxsize=1)
    radio.failed = threading.Event()
    monkeypatch.setattr(SerialInterface, "_handleFromRadio", lambda *args: pytest.fail("SDK must not handle captured text"))
    raw = ProbeScenario(123).packet("live").SerializeToString()
    radio._handleFromRadio(raw)
    assert radio.next_frame()[0] == raw
    radio._handleFromRadio(raw)
    radio._handleFromRadio(raw)
    with pytest.raises(RuntimeError, match="queue overflow"):
        radio.next_frame()
    with pytest.raises(RuntimeError, match="transmission is disabled"):
        radio._sendToRadioImpl(mesh_pb2.ToRadio(packet=mesh_pb2.MeshPacket(id=1)))


def test_capture_requests_node_database_and_buffers_initial_sync(monkeypatch):
    def initialize(self, **kwargs):
        assert kwargs['noNodes'] is False
        assert kwargs['connectNow'] is False

    monkeypatch.setattr(SerialInterface, '__init__', initialize)
    monkeypatch.setattr(SerialInterface, '_handleFromRadio', lambda *args: None)
    def connect(self):
        for number in range(1, 1001):
            raw = mesh_pb2.FromRadio(node_info=mesh_pb2.NodeInfo(
                num=number, user=mesh_pb2.User(long_name=f'Node {number}'))).SerializeToString()
            self._handleFromRadio(raw)
    monkeypatch.setattr(CaptureSerialInterface, 'connect', connect)
    radio = CaptureSerialInterface('test-port')
    assert not radio.failed.is_set()
    for number in range(1, 1001):
        frame = mesh_pb2.FromRadio.FromString(radio.next_frame()[0])
        assert frame.node_info.num == number


def test_node_names_resolve_existing_messages_and_survive_restart(configured):
    repo, ingestor, scenario = configured
    frame = scenario.packet('live')
    sender = 0x12345678
    setattr(frame.packet, 'from', sender)
    ingestor.accept(frame.SerializeToString(), 1_800_000_000)
    scope = repo.list_channels()[0]['scope']
    assert repo.chat(scope)[0]['sender_name'] == '!12345678'
    info = mesh_pb2.FromRadio(node_info=mesh_pb2.NodeInfo(
        num=sender, user=mesh_pb2.User(long_name='Домашня нода', short_name='HOME')))
    ingestor.accept(info.SerializeToString(), 1_800_000_001)
    assert repo.chat(scope)[0]['sender_name'] == 'Домашня нода'
    info.node_info.user.Clear()
    ingestor.accept(info.SerializeToString(), 1_800_000_002)
    reopened = HistoryRepository(repo.path)
    try:
        assert reopened.chat(scope)[0]['sender_name'] == 'Домашня нода'
        assert reopened.summary()['messages'] == 1
    finally:
        reopened.close()
