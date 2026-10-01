from dataclasses import replace
import os
from pathlib import Path
import struct
import subprocess

import pytest
from meshtastic.protobuf import mesh_pb2, storeforward_pb2

from meshtastic_sf.diagnostics.ios_probe import ProbeScenario
from meshtastic_sf.services.ingestion import Ingestor
from meshtastic_sf.services.replay import ReplayService, LIMIT, INTERVAL, MAX_WINDOW_MINUTES
from meshtastic_sf.storage.repository import HistoryRepository
from meshtastic_sf.transport.replay import FreshReplay, Control, MAX_REPLAY_TEXT, ReplayBridgeClient
from meshtastic_sf.transport.protocol import HEADER, CAPABILITIES, BASE_COMMIT, Status, Operation, header, Response
from meshtastic_sf.transport.client import BridgeUnavailable

SF = storeforward_pb2.StoreAndForward


def reply(payload, profile=1, status=0):
    magic, op, _, _, session, token = HEADER.unpack_from(payload)
    return HEADER.pack(magic, op | 128, status, 0, session, token) + CAPABILITIES.pack(
        MAX_REPLAY_TEXT if profile else 0, profile, 2 if profile else 1, 12, 0, BASE_COMMIT.encode())


class Radio:
    def __init__(self):
        self.sent = []
        self.profile = 1
        self.timeout = False
        self.busy = False

    def exchange(self, payload, timeout):
        self.sent.append(payload)
        if self.timeout:
            raise TimeoutError
        return reply(payload, self.profile, Status.BUSY if self.busy and payload[4] != 1 else Status.OK)


@pytest.fixture
def world(tmp_path):
    repo = HistoryRepository(tmp_path / "history.db")
    ingestor = Ingestor(repo)
    scenario = ProbeScenario(123)
    for f in scenario.configuration(7):
        ingestor.accept(f.SerializeToString(), 1_800_000_000)
    timer = [100.0]
    service = ReplayService(repo, clock=lambda: timer[0], wall=lambda: 1_800_000_100)
    radio = Radio()
    yield repo, ingestor, scenario, service, radio, timer
    repo.close()


def enable(repo, enabled=True):
    repo.update_settings({**repo.get_settings(), "replay_enabled": enabled})


def request(scenario, rr=65, sender=12345, channel=0, packet_id=800):
    sf = SF(rr=rr)
    if rr == 65:
        sf.history.window = 60
    frame = mesh_pb2.FromRadio(packet=mesh_pb2.MeshPacket(to=scenario.node, channel=channel, id=packet_id,
        decoded=mesh_pb2.Data(portnum=65, payload=sf.SerializeToString())))
    setattr(frame.packet, "from", sender)
    return frame


def seed(ingestor, scenario, count=3):
    for index in range(count):
        frame = scenario.packet("live")
        frame.packet.id = index + 1
        frame.packet.decoded.payload = f"Привіт Ґґ {index}".encode()
        ingestor.accept(frame.SerializeToString(), 1_800_000_000 + index)


def command_request(scenario, text=b'/history 6', packet_id=800):
    frame = request(scenario, packet_id=packet_id)
    frame.packet.to = 0xFFFFFFFF
    frame.packet.decoded.portnum = 1
    frame.packet.decoded.payload = text
    return frame


def test_chat_command_window_capture_and_wire_response(world):
    repo, ingestor, scenario, service, radio, timer = world
    seed(ingestor, scenario, 1)
    old = scenario.packet('live')
    old.packet.id = 200
    ingestor.accept(old.SerializeToString(), 1_800_000_100 - 7 * 3600)
    enable(repo)
    frame = command_request(scenario)
    assert ingestor.accept(frame.SerializeToString(), 1_800_000_100) is None
    assert ingestor.last_disposition == 'control'
    service.accept(frame, ingestor)
    assert len(service.job.packets) == 1
    service.tick(radio, ingestor)
    assert [p[4] for p in radio.sent] == [1, 2]  # HELLO, then text; no CONTROL header.
    assert radio.sent[-1][60:].decode() == 'Привіт Ґґ 0'
    assert service.job is None
    assert repo.list_channels()[0]['count'] == 2


@pytest.mark.parametrize('text', [b'/history', b'/history 0', b'/history -1', b'/history 1.5',
    b'/history abc', b'/history 1 extra', b'/history 1000000', b'/history \xff'])
def test_invalid_commands_are_never_archived_or_answered(world, text):
    repo, ingestor, scenario, service, radio, timer = world
    enable(repo)
    frame = command_request(scenario, text)
    assert ingestor.accept(frame.SerializeToString(), 1_800_000_100) is None
    service.accept(frame, ingestor)
    assert repo.list_channels()[0]['count'] == 0
    assert service.job is None and service.snapshot()['requests'] == 0


def test_command_disabled_capture_pause_cap_and_shared_cooldown(world):
    repo, ingestor, scenario, service, radio, timer = world
    frame = command_request(scenario, b' /HISTORY 999999 ')
    assert ingestor.accept(frame.SerializeToString(), 1_800_000_100) is None
    service.accept(frame, ingestor)
    service.tick(radio, ingestor)
    assert not radio.sent and service.job is None
    repo.update_settings({**repo.get_settings(), 'capture_enabled': False,
                          'replay_enabled': True, 'replay_max_window_minutes': 1440,
                          'replay_heartbeat_enabled': False})
    service.accept(frame, ingestor)
    assert service.job is None  # Empty chat history is silent, but consumes cooldown.
    service.tick(radio, ingestor)
    assert radio.sent == []
    service.accept(frame, ingestor)
    assert service.snapshot()['requests'] == 1
    service.cancel()
    service.accept(request(scenario, packet_id=801), ingestor)
    assert service.job is None  # Native requests cannot bypass the command cooldown.
    timer[0] += 61
    service.accept(command_request(scenario, packet_id=802), ingestor)
    assert service.job is None and service.snapshot()['requests'] == 2


def test_silent_command_still_caps_history_window(world):
    repo, ingestor, scenario, service, radio, timer = world
    seed(ingestor, scenario, 1)
    old = scenario.packet('live')
    old.packet.id = 200
    ingestor.accept(old.SerializeToString(), 1_800_000_100 - 25 * 3600)
    repo.update_settings({**repo.get_settings(), 'replay_enabled': True,
                          'replay_max_window_minutes': 1440})
    service.accept(command_request(scenario, b'/history 999999'), ingestor)
    assert len(service.job.packets) == 1
    assert service.job.packets[0]['packet_id'] == 1


def test_empty_native_request_keeps_history_header(world):
    repo, ingestor, scenario, service, radio, timer = world
    enable(repo)
    service.accept(request(scenario), ingestor)
    service.tick(radio, ingestor)
    response = SF.FromString(radio.sent[-1][44:])
    assert response.rr == 6 and response.history.history_messages == 0
    assert service.job is None


@pytest.mark.parametrize('change', ['unicast', 'other-channel', 'pki', 'mqtt', 'own', 'anonymous', 'no-id'])
def test_command_requires_private_broadcast_from_other_node(world, change):
    repo, ingestor, scenario, service, radio, timer = world
    enable(repo)
    frame = command_request(scenario)
    if change == 'unicast': frame.packet.to = scenario.node
    elif change == 'other-channel': frame.packet.channel = 7
    elif change == 'pki': frame.packet.pki_encrypted = True
    elif change == 'mqtt': frame.packet.via_mqtt = True
    elif change == 'own': setattr(frame.packet, 'from', scenario.node)
    elif change == 'anonymous': setattr(frame.packet, 'from', 0)
    elif change == 'no-id': frame.packet.id = 0
    service.accept(frame, ingestor)
    assert service.job is None and service.snapshot()['requests'] == 0


def test_regular_mentions_are_archived_and_legacy_commands_never_replayed(world):
    from meshtastic_sf.domain.messages import IncomingText
    repo, ingestor, scenario, service, radio, timer = world
    frame = command_request(scenario, b'Use /history 6 to request history')
    assert ingestor.accept(frame.SerializeToString(), 1_800_000_099) is not None
    scope = repo.list_channels()[0]['scope']
    repo.save(IncomingText(scope, 321, 110, 0, b'/history 6', b'data', b'envelope', 1_800_000_099, 0))
    enable(repo)
    service.accept(command_request(scenario, packet_id=801), ingestor)
    assert service.job is None


def test_disabled_is_silent_including_discovery(world):
    repo, ingestor, scenario, service, radio, timer = world
    assert repo.get_settings()["replay_enabled"] is False
    seed(ingestor, scenario)
    for rr in (65, 66, 67, 106):
        service.accept(request(scenario, rr), ingestor)
        service.tick(radio, ingestor)
    assert radio.sent == [] and service.job is None


def test_real_wire_header_original_identity_pacing_and_disable(world):
    repo, ingestor, scenario, service, radio, timer = world
    seed(ingestor, scenario)
    enable(repo)
    service.accept(request(scenario), ingestor)
    service.tick(radio, ingestor)
    assert [p[4] for p in radio.sent] == [1, 4]
    response = SF.FromString(radio.sent[-1][44:])
    assert response.rr == 6 and response.history.history_messages == 3
    assert response.history.window == 3_600_000
    service.tick(radio, ingestor)
    assert len(radio.sent) == 2
    timer[0] += INTERVAL
    service.tick(radio, ingestor)
    p = radio.sent[-1]
    sender, original, requester, channel, reply_id, emoji, outer_id = struct.unpack_from('<7I', p, 16)
    assert (original, requester, channel) == (1, 12345, 0)
    assert sender == getattr(scenario.packet('live').packet, 'from')
    assert outer_id != original and outer_id != 0
    assert p[60:].decode() == 'Привіт Ґґ 0'
    enable(repo, False)
    timer[0] += 20
    service.tick(radio, ingestor)
    assert len(radio.sent) == 3 and service.job is None
    assert service.snapshot()['state'] == 'disabled'


@pytest.mark.parametrize('change', ['other-channel', 'broadcast', 'mqtt', 'pki', 'own', 'malformed'])
def test_untrusted_requests_do_not_select_history(world, change):
    repo, ingestor, scenario, service, radio, timer = world
    enable(repo)
    frame = request(scenario)
    if change == 'other-channel': frame.packet.channel = 7
    elif change == 'broadcast': frame.packet.to = 0xFFFFFFFF
    elif change == 'mqtt': frame.packet.via_mqtt = True
    elif change == 'pki': frame.packet.pki_encrypted = True
    elif change == 'own': setattr(frame.packet, 'from', scenario.node)
    elif change == 'malformed': frame.packet.decoded.payload = b'\xff'
    service.accept(frame, ingestor)
    assert service.job is None and service.snapshot()['requests'] == 0


def test_duplicate_abort_owner_scope_and_timeout(world):
    repo, ingestor, scenario, service, radio, timer = world
    enable(repo)
    seed(ingestor, scenario)
    req = request(scenario)
    service.accept(req, ingestor)
    first = service.job
    service.accept(req, ingestor)
    assert service.job is first and service.snapshot()['requests'] == 1
    service.accept(request(scenario, 106, sender=999, packet_id=801), ingestor)
    assert service.job is first
    service.accept(request(scenario, 106, packet_id=802), ingestor)
    assert service.job is None
    timer[0] += 61
    service.accept(request(scenario, packet_id=803), ingestor)
    timer[0] += 181
    service.next_heartbeat = timer[0] + 1000
    service.tick(radio, ingestor)
    assert service.job is None and radio.sent == []


def test_history_excludes_other_scopes_own_conflicts_oversize_and_old(world):
    repo, ingestor, scenario, service, radio, timer = world
    seed(ingestor, scenario, 30)
    frame = scenario.packet('live')
    for packet_id, sender, text, received in [(101, 12345, b'own', 1_800_000_030),
            (102, 321, b'x' * (MAX_REPLAY_TEXT + 1), 1_800_000_031),
            (103, 321, b'old', 1_700_000_000), (104, 321, b'first', 1_800_000_033),
            (104, 321, b'conflict', 1_800_000_034)]:
        frame.packet.id = packet_id
        setattr(frame.packet, 'from', sender)
        frame.packet.decoded.payload = text
        ingestor.accept(frame.SerializeToString(), received)
    scope = repo.list_channels()[0]['scope']
    # Different channel epoch must not be returned even if sender/ID is the same.
    from meshtastic_sf.domain.messages import IncomingText
    repo.save(IncomingText('f' * 64, 321, 110, 0, b'other scope', b'data', b'envelope', 1_800_000_040, 0))
    selected = repo.replay_history(scope, 12345, 1_799_996_500, 1_800_000_100)
    assert len(selected) == LIMIT
    assert [r['packet_id'] for r in selected] == list(range(11, 31))


def test_stock_patch_and_timeout_fail_closed(world):
    repo, ingestor, scenario, service, radio, timer = world
    enable(repo)
    radio.profile = 0
    service.accept(request(scenario), ingestor)
    service.tick(radio, ingestor)
    assert service.snapshot()['state'] == 'blocked' and [p[4] for p in radio.sent] == [1]
    service.disconnect()
    timer[0] += 120
    radio.timeout = True
    service.accept(request(scenario, packet_id=999), ingestor)
    service.tick(radio, ingestor)
    assert radio.sent[-1] == radio.sent[-2]  # Same-token USB retry, never a fresh radio replay.
    assert service.job is None and service.snapshot()['state'] == 'blocked'


def test_completed_busy_and_discovery(world):
    repo, ingestor, scenario, service, radio, timer = world
    enable(repo)
    seed(ingestor, scenario, 1)
    service.accept(request(scenario), ingestor)
    radio.busy = True
    service.tick(radio, ingestor)
    assert len(service.job.packets) == 2
    timer[0] += INTERVAL
    radio.busy = False
    service.tick(radio, ingestor)
    timer[0] += INTERVAL
    service.tick(radio, ingestor)
    assert service.job is None and service.snapshot()['replayed'] == 1
    timer[0] += INTERVAL
    service.tick(radio, ingestor)
    heartbeat = SF.FromString(radio.sent[-1][44:])
    assert heartbeat.rr == 2 and heartbeat.heartbeat.period == 900
    assert struct.unpack_from('<I', radio.sent[-1], 16)[0] == 0xFFFFFFFF


def test_reserved_ids_survive_restart_and_retention(world, monkeypatch):
    repo, ingestor, scenario, service, radio, timer = world
    seed(ingestor, scenario, 1)
    sender = getattr(scenario.packet('live').packet, 'from')
    sequence = iter([0, 1, 1, 2])
    monkeypatch.setattr('meshtastic_sf.storage.repository.secrets.randbelow', lambda _: next(sequence))
    assert repo.reserve_replay_id(sender, 1) == 2
    repo.prune(before=1_800_000_100)
    reopened = HistoryRepository(repo.path)
    try:
        assert reopened.reserve_replay_id(sender, 1) == 3
    finally:
        reopened.close()


def test_native_profile_exact_retry_submits_once():
    binary = os.environ.get('USF_BRIDGE_HARNESS')
    if not binary:
        pytest.skip('Set USF_BRIDGE_HARNESS to the compiled profile-aware harness')
    packet = FreshReplay(1, 2, 3, 0, 'Привіт'.encode(), 4, b'c' * 16)
    hello = header(Operation.HELLO, 7, 1)
    replay = packet.encode(7, 2)
    malformed = replace(packet, outer_id=2)
    with pytest.raises(ValueError): malformed.encode(7, 3)
    commands = [hello.hex(), replay.hex(), replay.hex(), 'count']
    process = subprocess.run([binary, '--replay'], input='\n'.join(commands)+'\n', text=True, capture_output=True, check=True)
    lines = process.stdout.splitlines()
    capability = Response.decode(bytes.fromhex(lines[0]))
    ReplayBridgeClient(lambda *_: None).validate_capabilities(capability)
    assert lines[1] == lines[2] and lines[3] == '1'
    assert Response.decode(bytes.fromhex(lines[1])).status == Status.OK


def test_native_radio_payload_preserves_text_and_original_id():
    binary = os.environ.get('USF_BRIDGE_HARNESS')
    if not binary:
        pytest.skip('Native harness is required')
    from meshtastic_sf.diagnostics.replay_pb2 import ReplayText
    packets = [FreshReplay(1, 0xFFFFFFFF, 3, 0, text, 4, b'c' * 16).encode(7, 2)
               for text in ['Привіт Ґґ'.encode(), b'x' * MAX_REPLAY_TEXT]]
    process = subprocess.run([binary, '--replay'], input='\n'.join('payload '+p.hex() for p in packets)+'\n',
                             text=True, capture_output=True, check=True)
    for command, line in zip(packets, process.stdout.splitlines(), strict=True):
        payload = bytes.fromhex(line)
        decoded = ReplayText.FromString(payload)
        assert decoded.rr == 9 and decoded.original_id == 0xFFFFFFFF and decoded.text == command[60:]
        assert len(mesh_pb2.Data(portnum=65, payload=payload, reply_id=0xFFFFFFFF, emoji=1).SerializeToString()) <= 233
