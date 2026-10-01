import os
from pathlib import Path
import subprocess

import pytest

from meshtastic_sf.transport.protocol import Operation, Response, Status, header


@pytest.fixture
def firmware():
    binary = os.environ.get("USF_BRIDGE_HARNESS")
    if not binary:
        pytest.skip("Set USF_BRIDGE_HARNESS to the compiled C++ bridge harness")
    assert Path(binary).is_file()

    def run(*commands):
        lines = [c.hex() if isinstance(c, bytes) else c for c in commands]
        process = subprocess.run([binary], input="\n".join(lines) + "\n", text=True, capture_output=True, check=True)
        return [Response.decode(bytes.fromhex(line)) if line not in ("none", "reset") else line
                for line in process.stdout.splitlines()]
    return run


def test_firmware_handshake_retry_and_disabled_replay(firmware):
    hello = header(Operation.HELLO, 123, 1)
    replies = firmware(hello, hello, header(Operation.REPLAY, 123, 2), header(Operation.ABORT, 123, 3))
    assert replies[0] == replies[1]
    replies[0].require_compatible()
    assert [r.status for r in replies] == [Status.OK, Status.OK, Status.DISABLED, Status.OK]


def test_firmware_session_conflict_stale_and_reset(firmware):
    results = firmware(header(Operation.REPLAY, 10, 1), header(Operation.HELLO, 10, 2),
                       header(Operation.ABORT, 10, 2), header(Operation.ABORT, 10, 1),
                       header(Operation.ABORT, 11, 3), "reset", header(Operation.ABORT, 10, 4))
    assert [r.status for r in results[:5]] == [Status.SESSION, Status.OK, Status.CONFLICT, Status.STALE, Status.SESSION]
    assert results[5] == "reset"
    assert results[6].status == Status.SESSION


def test_firmware_keeps_pending_response_and_ignores_malformed_input(firmware):
    hello = header(Operation.HELLO, 1, 1)
    results = firmware(b"", b"bad", b"x" * 257, "hold " + hello.hex(),
                       header(Operation.HELLO, 2, 1), header(Operation.ABORT, 2, 2))
    assert results[:4] == ["none"] * 4
    assert results[4].session == 1
    assert results[5].status == Status.SESSION
