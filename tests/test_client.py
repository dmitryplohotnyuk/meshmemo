import pytest

from meshtastic_sf.transport.client import BridgeClient, BridgeRejected, BridgeUnavailable
from meshtastic_sf.transport.protocol import HEADER, Operation, ReplayMessage, Status
from test_protocol import response


def test_timeout_retries_identical_request_then_succeeds():
    requests = []

    def exchange(payload, timeout):
        requests.append(payload)
        if len(requests) == 1:
            raise TimeoutError
        return response(payload)

    client = BridgeClient(exchange)
    client.connect()
    assert client.ready
    assert requests[0] == requests[1]
    client.abort()
    assert HEADER.unpack_from(requests[2])[5] == 2


def test_stock_firmware_timeout_fails_closed():
    requests = []

    def exchange(payload, timeout):
        requests.append(payload)
        raise TimeoutError

    client = BridgeClient(exchange)
    with pytest.raises(BridgeUnavailable, match="outcome unknown"):
        client.connect()
    assert len(requests) == 2
    assert not client.ready


def test_replay_cannot_reach_transport_even_after_handshake():
    requests = []

    def exchange(payload, timeout):
        requests.append(payload)
        return response(payload)

    client = BridgeClient(exchange)
    client.connect()
    with pytest.raises(BridgeUnavailable, match="Replay disabled"):
        client.replay(ReplayMessage(1, 2, 3, 0, b"test"))
    assert [HEADER.unpack_from(p)[1] for p in requests] == [Operation.HELLO]


@pytest.mark.parametrize("kind", ["session", "token", "profile", "malformed", "stale"])
def test_invalid_response_invalidates_session(kind):
    def exchange(payload, timeout):
        if kind == "profile":
            return response(payload, profile=1)
        if kind == "malformed":
            return b"no"
        if kind == "stale":
            return response(payload, status=Status.STALE)
        changed = bytearray(response(payload))
        changed[8 if kind == "session" else 12] ^= 1
        return bytes(changed)

    client = BridgeClient(exchange)
    with pytest.raises((BridgeUnavailable, BridgeRejected)):
        client.connect()
    assert not client.ready
