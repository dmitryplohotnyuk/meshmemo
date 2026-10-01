"""Exercise real bridge C++ with injected radio-adapter outcomes, without RF.

These tests validate the bridge boundary, not the board adapter's admission result
or the proposed upstream API, which has not been agreed with maintainers.
"""

import os
from pathlib import Path
import struct
import subprocess

import pytest

from meshtastic_sf.transport.protocol import Operation, Response, Status, header
from meshtastic_sf.transport.replay import FreshReplay


@pytest.fixture
def bridge():
    binary = os.environ.get("USF_BRIDGE_HARNESS")
    if not binary:
        pytest.skip("Set USF_BRIDGE_HARNESS to the rebuilt native harness")
    assert Path(binary).is_file()

    def run(*commands):
        inputs = [c.hex() if isinstance(c, bytes) else c for c in commands]
        result = subprocess.run([binary, "--replay"], input="\n".join(inputs) + "\n",
                                text=True, capture_output=True, check=True, timeout=10)
        return result.stdout.splitlines()

    return run


def packet(token=2):
    return FreshReplay(1, 2, 3, 0, b"Synthetic archive text", 4, b"c" * 16).encode(7, token)


def status(line):
    return Response.decode(bytes.fromhex(line)).status


@pytest.mark.parametrize("failure", [Status.BUSY, Status.DISABLED, Status.RADIO_ERROR, Status.INVALID])
def test_rejected_submission_is_cached_and_new_attempt_is_explicit(bridge, failure):
    # A lost error reply followed by USB retry must not submit again, even if
    # the underlying condition has recovered in the meantime.
    lines = bridge(header(Operation.HELLO, 7, 1), f"result {failure.value}", packet(),
                   "result 0", packet(), "count", packet(3), "count")
    assert status(lines[0]) == Status.OK
    assert status(lines[2]) == failure
    assert lines[2] == lines[4]
    assert lines[5] == "1"
    assert status(lines[6]) == Status.OK
    assert lines[7] == "2"


def test_conflicting_retry_does_not_overwrite_cached_outcome(bridge):
    different = bytearray(packet())
    different[-1] ^= 1
    lines = bridge(header(Operation.HELLO, 7, 1), packet(), bytes(different), packet(), "count")
    assert status(lines[1]) == Status.OK
    assert status(lines[2]) == Status.CONFLICT
    assert lines[1] == lines[3]
    assert lines[4] == "1"


def test_reset_rejects_old_operation_with_unknown_outcome(bridge):
    lines = bridge(header(Operation.HELLO, 7, 1), "hold " + packet().hex(),
                   "reset", packet(), "count")
    assert lines[1:3] == ["none", "reset"]
    assert status(lines[3]) == Status.SESSION
    assert lines[4] == "1"


def test_full_response_slot_does_not_admit_another_operation(bridge):
    lines = bridge(header(Operation.HELLO, 7, 1), "hold " + packet().hex(),
                   packet(3), "count", packet(3), "count")
    assert lines[1] == "none"
    assert Response.decode(bytes.fromhex(lines[2])).token == 2
    assert lines[3] == "1"
    assert Response.decode(bytes.fromhex(lines[4])).token == 3
    assert lines[5] == "2"


@pytest.mark.parametrize("offset,value", [
    (16, 0), (16, 0xFFFFFFFF), (16, 3),  # invalid/original sender equals requester
    (20, 0),                          # missing original packet ID
    (24, 0), (24, 0xFFFFFFFF),         # invalid/broadcast requester
    (28, 8),                          # out-of-range local channel
    (36, 2),                          # invalid boolean emoji representation
    (40, 0), (40, 2),                 # missing outer ID / intentional original-ID reuse
])
def test_invalid_wire_identity_never_reaches_radio_adapter(bridge, offset, value):
    malformed = bytearray(packet())
    struct.pack_into("<I", malformed, offset, value)
    lines = bridge(header(Operation.HELLO, 7, 1), bytes(malformed), "count")
    assert status(lines[1]) == Status.INVALID
    assert lines[2] == "0"


@pytest.mark.parametrize("text_size", [0, 193])
def test_text_boundary_is_checked_before_submission(bridge, text_size):
    malformed = packet()[:60] + b"x" * text_size
    lines = bridge(header(Operation.HELLO, 7, 1), malformed, "count")
    assert status(lines[1]) == Status.INVALID
    assert lines[2] == "0"
