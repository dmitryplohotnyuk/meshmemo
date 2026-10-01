import queue
import threading

import pytest
from meshtastic.protobuf import mesh_pb2

from meshtastic_sf.transport import bridge_pb2
from meshtastic_sf.transport.protocol import Operation, header
from meshtastic_sf.transport.serial import BridgeSerialInterface
from test_protocol import response


def adapter():
    radio = BridgeSerialInterface.__new__(BridgeSerialInterface)
    radio._responses = queue.Queue(maxsize=4)
    radio._exchange_lock = threading.Lock()
    radio._write_lock = threading.RLock()
    radio.stream = object()
    return radio


def test_exchange_correlates_response_without_sdk_packet_queue():
    radio = adapter()
    payload = header(Operation.HELLO, 22, 1)

    def send(envelope):
        assert isinstance(envelope, mesh_pb2.ToRadio)
        assert envelope.WhichOneof("payload_variant") is None
        assert bridge_pb2.ToRadioBridge.FromString(envelope.SerializeToString()).usb_sf == payload
        for item in [response(header(Operation.HELLO, 21, 1)), response(payload)]:
            radio._handleFromRadio(bridge_pb2.FromRadioBridge(usb_sf=item).SerializeToString())

    radio._sendToRadioImpl = send
    assert radio.exchange(payload, 0.1) == response(payload)


def test_closed_transport_and_silent_firmware_fail_closed():
    radio = adapter()
    radio._sendToRadioImpl = lambda envelope: None
    with pytest.raises(TimeoutError):
        radio.exchange(header(Operation.HELLO, 1, 1), 0.01)
    radio.stream = None
    with pytest.raises(OSError):
        radio.exchange(header(Operation.HELLO, 1, 1), 0.01)
