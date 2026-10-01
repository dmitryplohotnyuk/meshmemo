"""Wire compatibility and real firmware handshake across hardware models."""
from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess

import pytest

from meshtastic_sf.transport.client import BridgeClient, BridgeUnavailable
from meshtastic_sf.transport.protocol import (
    BASE_COMMIT, CAPABILITIES, CAPABILITIES_V2, HEADER, MAGIC_V2, Operation, Response, header,
)
from meshtastic_sf.transport.replay import ReplayBridgeClient, EncryptedReply


def portable(request, *, model=43, operations=31, transport=2, build=b"b" * 32, profile=1):
    _, op, _, _, session, token = HEADER.unpack_from(request)
    return (HEADER.pack(MAGIC_V2, op | 128, 0, 0, session, token)
            + CAPABILITIES.pack(192 if profile else 0, profile, 4, model, 0, BASE_COMMIT.encode())
            + CAPABILITIES_V2.pack(operations, 256, 100 if profile else 0, 208 if profile else 0, transport, build))


@pytest.mark.parametrize("model,transport", [(12, 1), (43, 2), (999, 1)])
def test_accepts_portable_contract_without_board_allowlist(model, transport):
    client = ReplayBridgeClient(lambda request, timeout: portable(request, model=model, transport=transport))
    response = client.connect()
    assert client.ready and response.hardware_model == model
    assert response.protocol_version == 2 and response.supports(Operation.ENCRYPTED_REPLY)
    assert response.build_id == (b"b" * 32).hex()


@pytest.mark.parametrize("changes", [
    {"hardware_model": 0}, {"hardware_model": 0xFFFFFFFF}, {"transport": 0}, {"transport": 3},
    {"protocol_version": 3}, {"patch_revision": 3}, {"patch_revision": 5}, {"profile": 0},
    {"operations": 7}, {"operations": 63}, {"max_text": 191}, {"max_control": 99},
    {"max_encrypted": 207}, {"max_request": 255}, {"build_id": "0" * 64},
    {"build_id": "g" * 64}, {"base_commit": "0" * 40},
])
def test_rejects_incompatible_portable_contract(changes):
    response = Response.decode(portable(header(Operation.HELLO, 1, 1)))
    with pytest.raises(ValueError):
        replace(response, **changes).require_portable(1)


@pytest.mark.parametrize("revision,model,accepted", [(2, 12, True), (3, 12, True), (3, 43, False), (4, 12, False)])
def test_legacy_policy_is_preserved(revision, model, accepted):
    def exchange(request, timeout):
        magic, op, _, _, session, token = HEADER.unpack_from(request)
        return HEADER.pack(magic, op | 128, 0, 0, session, token) + CAPABILITIES.pack(192, 1, revision, model, 0, BASE_COMMIT.encode())
    client = ReplayBridgeClient(exchange)
    if accepted:
        assert client.connect().patch_revision == revision
    else:
        with pytest.raises(BridgeUnavailable):
            client.connect()
        assert not client.ready


def test_missing_encrypted_operation_blocks_before_transmission():
    sent = []
    def exchange(request, timeout):
        sent.append(request)
        return portable(request, operations=15)
    client = ReplayBridgeClient(exchange)
    client.connect()
    with pytest.raises(BridgeUnavailable, match="ENCRYPTED_REPLY"):
        client.send(EncryptedReply(1, 2, 3, 4, b"c" * 16, b"ciphertext"))
    assert len(sent) == 1


@pytest.mark.parametrize("changes", [{"build": b"c" * 32}, {"model": 44}, {"operations": 15}])
def test_session_rejects_capability_drift(changes):
    calls = []
    def exchange(request, timeout):
        calls.append(request)
        return portable(request, **(changes if len(calls) > 1 else {}))
    client = ReplayBridgeClient(exchange)
    client.connect()
    with pytest.raises(BridgeUnavailable, match="changed"):
        client.abort()
    assert not client.ready


def test_new_diagnostic_profile_remains_diagnostic():
    client = BridgeClient(lambda request, timeout: portable(request, profile=0, operations=5))
    response = client.connect()
    assert response.max_text == 0 and not response.supports(Operation.REPLAY)


@pytest.mark.parametrize("mutation", [lambda p: p[:-1], lambda p: p + b"x", lambda p: b"USF1" + p[4:], lambda p: b"USF3" + p[4:]])
def test_layout_cannot_be_misread_as_legacy(mutation):
    with pytest.raises(ValueError):
        Response.decode(mutation(portable(header(Operation.HELLO, 1, 1))))


@pytest.mark.parametrize("board,model,transport", [("tbeam", 12, 1), ("heltec", 43, 2)])
def test_real_cpp_firmware_is_accepted_by_server(board, model, transport):
    root = os.environ.get("MESHMEMO_PORTABLE_NATIVE")
    if not root:
        pytest.skip("Set MESHMEMO_PORTABLE_NATIVE to both compiled firmware harnesses")
    binary = Path(root) / board / "bridge.exe"
    def exchange(request, timeout):
        result = subprocess.run([binary, "--replay"], input=request.hex() + "\n", text=True,
                                capture_output=True, check=True, timeout=10)
        return bytes.fromhex(result.stdout.strip())
    response = ReplayBridgeClient(exchange).connect()
    assert (response.hardware_model, response.transport) == (model, transport)
    assert response.patch_revision == 4 and response.supported_operations == 31
    prepared = json.loads((Path(root).parent / f"portable-{board}" / "prepare.json").read_text())
    assert response.build_id == prepared["plan"]["build_id"]


def test_diagnostic_profile_cannot_advertise_radio_operations():
    response = Response.decode(portable(header(Operation.HELLO, 1, 1), profile=0, operations=31))
    with pytest.raises(ValueError):
        response.require_compatible()


def test_portable_extension_survives_official_protobuf_bindings():
    from meshtastic.protobuf import mesh_pb2
    from meshtastic_sf.transport import bridge_pb2
    payload = portable(header(Operation.HELLO, 1, 1))
    wire = bridge_pb2.FromRadioBridge(usb_sf=payload).SerializeToString()
    official = mesh_pb2.FromRadio.FromString(wire)
    assert official.WhichOneof("payload_variant") is None
    assert bridge_pb2.FromRadioBridge.FromString(official.SerializeToString()).usb_sf == payload
