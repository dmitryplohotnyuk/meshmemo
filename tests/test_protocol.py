from dataclasses import replace

import pytest
from meshtastic.protobuf import mesh_pb2, storeforward_pb2, portnums_pb2

from meshtastic_sf.transport import bridge_pb2
from meshtastic_sf.transport.protocol import (
    BASE_COMMIT, CAPABILITIES, HEADER, MAX_TEXT, Operation, ReplayMessage, Response, Status, header,
)


def response(request, *, status=Status.OK, profile=0, base=BASE_COMMIT):
    magic, op, _, _, session, token = HEADER.unpack_from(request)
    return HEADER.pack(magic, op | 0x80, status, 0, session, token) + CAPABILITIES.pack(
        0, profile, 1, 12, 0, base.encode("ascii")
    )


def test_unknown_extension_survives_official_sdk_without_mesh_packet():
    data = header(Operation.HELLO, 0x11223344, 0x55667788)
    assert data.hex() == "55534631010000004433221188776655"
    wire = bridge_pb2.ToRadioBridge(usb_sf=data).SerializeToString()
    official = mesh_pb2.ToRadio.FromString(wire)
    assert official.WhichOneof("payload_variant") is None
    assert bridge_pb2.ToRadioBridge.FromString(official.SerializeToString()).usb_sf == data
    incoming = bridge_pb2.FromRadioBridge(usb_sf=response(data)).SerializeToString()
    official_response = mesh_pb2.FromRadio.FromString(incoming)
    assert official_response.WhichOneof("payload_variant") is None
    assert bridge_pb2.FromRadioBridge.FromString(official_response.SerializeToString()).usb_sf == response(data)


def test_capability_response():
    parsed = Response.decode(response(header(Operation.HELLO, 123, 1)))
    parsed.require_compatible()
    assert parsed.profile == 0
    assert parsed.max_text == 0
    assert parsed.hardware_model == 12
    for bad in [replace(parsed, base_commit="0" * 40), replace(parsed, profile=1), replace(parsed, patch_revision=2)]:
        with pytest.raises(ValueError):
            bad.require_compatible()


@pytest.mark.parametrize("payload", [b"", b"USF1", b"x" * 68, b"x" * 69])
def test_malformed_response(payload):
    with pytest.raises(ValueError):
        Response.decode(payload)


def test_reserved_replay_validates_utf8_bytes_not_character_count():
    message = ReplayMessage(1, 2, 3, 0, "ҐґПривіт".encode())
    assert message.encode(4, 5)[40:].decode() == "ҐґПривіт"
    assert len(replace(message, text=b"x" * MAX_TEXT).encode(4, 5)) == 256
    for bad in [replace(message, text=b"x" * 217), replace(message, text=b"\xff"),
                replace(message, channel=8), replace(message, sender=0xFFFFFFFF),
                replace(message, sender=True), replace(message, requester=1)]:
        with pytest.raises(ValueError):
            bad.encode(4, 5)


def test_original_id_sf_reencoding_changes_aes_plaintext():
    text = "Привіт".encode()
    original = mesh_pb2.Data(portnum=portnums_pb2.TEXT_MESSAGE_APP, payload=text)
    envelope = storeforward_pb2.StoreAndForward(rr=9, text=text)
    replay = mesh_pb2.Data(portnum=portnums_pb2.STORE_FORWARD_APP, payload=envelope.SerializeToString())
    assert original.SerializeToString() != replay.SerializeToString()
