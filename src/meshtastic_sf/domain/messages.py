"""Archive records retain host time independently of radio time."""

from dataclasses import dataclass


@dataclass(frozen=True)
class IncomingText:
    scope: str
    sender: int
    packet_id: int
    channel_index: int
    payload: bytes
    decoded_data: bytes
    raw_envelope: bytes
    received_at: int
    rx_time: int
    reply_id: int = 0
    emoji: int = 0

    @property
    def time_quality(self) -> str:
        if self.rx_time == 0:
            return "missing"
        return "plausible" if abs(self.rx_time - self.received_at) <= 86400 else "suspect"


@dataclass(frozen=True)
class SaveResult:
    row_id: int
    duplicate: bool
    collision: bool
