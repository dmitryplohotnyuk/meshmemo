"""USF1 local command codec; no serial framing or mesh protocol here."""

from dataclasses import dataclass
from enum import IntEnum
import struct

MAGIC = b"USF1"
BASE_COMMIT = "54e0d8d0ab2ff56b3a9ce967e53f79e49af560fb"
MAX_TEXT = 216
HEADER = struct.Struct("<4sBBHII")
REPLAY = struct.Struct("<IIIIII")
CAPABILITIES = struct.Struct("<HBBII40s")
MAGIC_V2 = b"USF2"
CAPABILITIES_V2 = struct.Struct("<IHHHH32s")


class Operation(IntEnum):
    HELLO = 1
    REPLAY = 2
    ABORT = 3
    CONTROL = 4
    ENCRYPTED_REPLY = 5


def operation_mask(*operations: Operation) -> int:
    return sum(1 << (int(op) - 1) for op in set(operations))


class Status(IntEnum):
    OK = 0
    INVALID = 1
    UNSUPPORTED = 2
    SESSION = 3
    STALE = 4
    CONFLICT = 5
    BUSY = 6
    DISABLED = 7
    RADIO_ERROR = 8


def uint32(value: int, name: str, *, nonzero: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not (int(nonzero) <= value <= 0xFFFFFFFF):
        raise ValueError(f"Invalid {name}")
    return value


def header(op: Operation, session: int, token: int) -> bytes:
    return HEADER.pack(MAGIC, op, 0, 0, uint32(session, "session", nonzero=True), uint32(token, "token", nonzero=True))


@dataclass(frozen=True)
class ReplayMessage:
    sender: int
    packet_id: int
    requester: int
    channel: int
    text: bytes
    reply_id: int = 0
    emoji: bool = False

    def encode(self, session: int, token: int) -> bytes:
        for name in ("sender", "packet_id", "requester"):
            uint32(getattr(self, name), name, nonzero=True)
        if self.sender == 0xFFFFFFFF or self.requester == 0xFFFFFFFF or self.sender == self.requester:
            raise ValueError("Replay requires distinct unicast sender and requester")
        uint32(self.channel, "channel")
        if self.channel >= 8:
            raise ValueError("Invalid local channel index")
        uint32(self.reply_id, "reply_id")
        if not isinstance(self.emoji, bool):
            raise ValueError("emoji must be boolean")
        if not isinstance(self.text, bytes) or not 1 <= len(self.text) <= MAX_TEXT:
            raise ValueError(f"Replay text must contain 1..{MAX_TEXT} bytes")
        self.text.decode("utf-8", errors="strict")
        return header(Operation.REPLAY, session, token) + REPLAY.pack(
            self.sender, self.packet_id, self.requester, self.channel, self.reply_id, self.emoji
        ) + self.text


@dataclass(frozen=True)
class Response:
    operation: Operation
    status: Status
    session: int
    token: int
    max_text: int
    profile: int
    patch_revision: int
    hardware_model: int
    queue_free: int
    base_commit: str
    protocol_version: int = 1
    operations: int = 0
    max_request: int = 256
    max_control: int = 0
    max_encrypted: int = 0
    transport: int = 0
    build_id: str = ""

    @classmethod
    def decode(cls, payload: bytes) -> "Response":
        version = 2 if payload[:4] == MAGIC_V2 else 1
        expected_size = HEADER.size + CAPABILITIES.size + (CAPABILITIES_V2.size if version == 2 else 0)
        if len(payload) != expected_size:
            raise ValueError("Malformed bridge response length")
        magic, op, status, reserved, session, token = HEADER.unpack_from(payload)
        if magic not in (MAGIC, MAGIC_V2) or reserved or not op & 0x80 or not session or not token:
            raise ValueError("Malformed bridge response header")
        values = CAPABILITIES.unpack_from(payload, HEADER.size)
        extra = {}
        if version == 2:
            operations, request, control, encrypted, transport, build = CAPABILITIES_V2.unpack_from(payload, 68)
            extra = dict(protocol_version=2, operations=operations, max_request=request,
                         max_control=control, max_encrypted=encrypted, transport=transport, build_id=build.hex())
        return cls(Operation(op & 0x7F), Status(status), session, token, *values[:-1], values[-1].decode("ascii"), **extra)

    @property
    def supported_operations(self) -> int:
        if self.protocol_version == 2:
            return self.operations
        operations = [Operation.HELLO, Operation.ABORT]
        if self.profile == 1 and self.patch_revision in (2, 3):
            operations += [Operation.REPLAY, Operation.CONTROL]
            if self.patch_revision == 3:
                operations.append(Operation.ENCRYPTED_REPLY)
        return operation_mask(*operations)

    @property
    def capability_identity(self) -> tuple:
        return (self.protocol_version, self.profile, self.patch_revision, self.hardware_model,
                self.base_commit, self.max_text, self.supported_operations, self.max_request,
                self.max_control, self.max_encrypted, self.transport, self.build_id)

    def supports(self, operation: Operation) -> bool:
        return bool(self.supported_operations & operation_mask(operation))

    def require_portable(self, profile: int) -> None:
        required = operation_mask(Operation.HELLO, Operation.ABORT)
        if profile == 1:
            required |= operation_mask(Operation.REPLAY, Operation.CONTROL)
        limits = (192, 100, 208) if profile == 1 else (0, 0, 0)
        if (self.protocol_version != 2 or self.base_commit != BASE_COMMIT or self.profile != profile
                or self.patch_revision != 4 or not 0 < self.hardware_model < 0xFFFFFFFF
                or self.transport not in (1, 2) or self.max_request != 256
                or (self.max_text, self.max_control, self.max_encrypted) != limits
                or self.operations & required != required or self.operations & ~31
                or (profile == 0 and self.operations != required)
                or len(self.build_id) != 64 or any(c not in "0123456789abcdef" for c in self.build_id)
                or not self.build_id.strip("0")):
            raise ValueError("Unsupported portable MeshMemo capability profile")

    def require_compatible(self) -> None:
        if self.protocol_version == 2:
            self.require_portable(0)
            return
        if self.protocol_version != 1 or self.base_commit != BASE_COMMIT or self.profile != 0 or self.patch_revision != 1 or self.max_text != 0:
            raise ValueError("Unsupported firmware bridge capability profile")
