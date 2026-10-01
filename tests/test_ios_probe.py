import socket
import threading

import pytest
from meshtastic.protobuf import mesh_pb2, portnums_pb2, storeforward_pb2
from meshtastic.tcp_interface import TCPInterface

from meshtastic_sf.diagnostics.ios_probe import FrameDecoder, ProbeScenario, ProbeSession, STAGES, frame, validate_bind
from meshtastic_sf.diagnostics.replay_pb2 import ReplayText


def test_fixtures_separate_live_identity_from_unique_radio_ids():
    scenario = ProbeScenario(seed=0x12345)
    packets = [scenario.packet(stage).packet for stage in STAGES]
    assert len({p.id for p in packets}) == 6
    assert all(getattr(p, "from") == scenario.author for p in packets)
    assert packets[0].decoded.portnum == portnums_pb2.TEXT_MESSAGE_APP
    for packet in packets[2:]:
        assert packet.to == scenario.node
        assert packet.decoded.portnum == portnums_pb2.STORE_FORWARD_APP
        legacy = storeforward_pb2.StoreAndForward.FromString(packet.decoded.payload)
        projected = ReplayText.FromString(legacy.SerializeToString())
        assert legacy.rr == 9
        assert projected.original_id not in {p.id for p in packets[2:]}
        assert legacy.text.decode().endswith("Привіт Ґґ")
    assert ReplayText.FromString(packets[2].decoded.payload).original_id == packets[1].id
    assert packets[2].decoded.payload == packets[3].decoded.payload
    assert packets[4].decoded.payload == packets[5].decoded.payload
    assert ReplayText.FromString(packets[2].decoded.payload).text == packets[1].decoded.payload


def test_frames_survive_tcp_fragmentation_and_invalid_prefix():
    packet = ProbeScenario(123).packet("replay")
    encoded = frame(packet)
    decoder = FrameDecoder()
    decoded = []
    for byte in b"\0\0\0\0\x94\xc3\xff\xff" + encoded + encoded:
        decoded.extend(decoder.feed(bytes([byte])))
    assert decoded == [packet.SerializeToString()] * 2
    assert not decoder.buffer


@pytest.mark.parametrize("value", ["0.0.0.0", "8.8.8.8", "224.0.0.1", "::1"])
def test_probe_cannot_bind_wildcard_or_public_address(value):
    with pytest.raises(ValueError):
        validate_bind(value)


def test_configuration_is_synthetic_and_completes_requested_nonce():
    scenario = ProbeScenario(123)
    config = scenario.configuration(456)
    assert config[0].my_info.my_node_num == scenario.node
    assert config[-1].config_complete_id == 456
    assert len([m for m in config if m.HasField("node_info")]) == 2
    assert next(m.channel.settings.name for m in config if m.HasField("channel")) == "SFTEST"
    assert not next(m.config.lora.tx_enabled for m in config if m.config.HasField("lora"))
    for message in config:
        assert len(frame(message)) <= 516


def test_probe_handshake_with_unmodified_official_python_tcp_client():
    scenario = ProbeScenario(123)
    failures = []
    sessions = []
    with socket.create_server(("127.0.0.1", 0)) as listener:
        listener.settimeout(5)

        def accept():
            try:
                connection, _ = listener.accept()
                with connection:
                    session = ProbeSession(connection, scenario)
                    sessions.append(session)
                    session.receive()
            except Exception as exc:
                failures.append(exc)

        thread = threading.Thread(target=accept, daemon=True)
        thread.start()
        client = None
        try:
            client = TCPInterface("127.0.0.1", portNumber=listener.getsockname()[1], timeout=5)
            assert client.myInfo.my_node_num == scenario.node
            assert client.localNode.channels[0].settings.name == "SFTEST"
            assert sessions[0].ready.wait(1)
            sessions[0].send_stage("baseline")
            sessions[0].send_stage("replay")
        finally:
            if client:
                client.close()
            thread.join(timeout=5)
        assert not failures
        assert not thread.is_alive()
        assert sessions[0].error is None
