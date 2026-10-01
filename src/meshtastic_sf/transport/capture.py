"""Ordered, bounded PhoneAPI capture. This adapter cannot transmit mesh packets."""

import queue
import threading
import time

from meshtastic.protobuf import mesh_pb2
from meshtastic.serial_interface import SerialInterface


class CaptureSerialInterface(SerialInterface):
    def __init__(self, device: str, *, timeout: int = 20):
        # connect() finishes before the archive worker can drain configuration.
        # Leave bounded room for the node database as well as channels/config.
        self.frames: queue.Queue[tuple[bytes, int]] = queue.Queue(maxsize=2048)
        self.failed = threading.Event()
        self._write_lock = threading.RLock()
        super().__init__(devPath=device, connectNow=False, noNodes=False, timeout=timeout)
        try:
            self.connect()
        except BaseException:
            self.close()
            raise

    def _writeBytes(self, data):
        with self._write_lock:
            super()._writeBytes(data)

    def _sendToRadioImpl(self, message):
        if message.HasField("packet"):
            raise RuntimeError("Mesh transmission is disabled in capture mode")
        super()._sendToRadioImpl(message)

    def _handleFromRadio(self, data):
        try:
            frame = mesh_pb2.FromRadio.FromString(data)
            kind = frame.WhichOneof("payload_variant")
            if kind in {"my_info", "channel", "config", "config_complete_id", "rebooted", "packet", "metadata", "node_info"}:
                self.frames.put_nowait((bytes(data), int(time.time())))
            # Archival packets must not trigger SDK handlers, automatic responses or payload logging.
            if kind != "packet":
                super()._handleFromRadio(data)
        except Exception:
            self.failed.set()

    def next_frame(self, timeout: float = 0.5) -> tuple[bytes, int] | None:
        if self.failed.is_set():
            raise RuntimeError("Capture stopped: malformed input or queue overflow; archive may have a gap")
        try:
            return self.frames.get(timeout=timeout)
        except queue.Empty:
            if not self._rxThread.is_alive():
                raise OSError("USB connection ended; reconnect to resume capture")
            return None
