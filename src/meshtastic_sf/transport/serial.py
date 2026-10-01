"""Isolate the two version-pinned SDK hooks used for the local extension."""

import queue
import threading

from meshtastic.serial_interface import SerialInterface
from meshtastic.protobuf import mesh_pb2

from . import bridge_pb2
from .protocol import HEADER


class BridgeSerialInterface(SerialInterface):
    def __init__(self, device: str, timeout: int = 20):
        self._responses: queue.Queue[bytes] = queue.Queue(maxsize=4)
        self._exchange_lock = threading.Lock()
        self._write_lock = threading.RLock()
        super().__init__(devPath=device, connectNow=False, noNodes=True, timeout=timeout)
        try:
            self.connect()
        except BaseException:
            self.close()
            raise

    def _writeBytes(self, data: bytes) -> None:
        with self._write_lock:
            super()._writeBytes(data)

    def _handleFromRadio(self, fromRadioBytes):
        projection = bridge_pb2.FromRadioBridge.FromString(fromRadioBytes)
        if projection.usb_sf:
            try:
                self._responses.put_nowait(projection.usb_sf)
            except queue.Full:
                pass
            return
        super()._handleFromRadio(fromRadioBytes)

    def exchange(self, payload: bytes, timeout: float) -> bytes:
        import time

        with self._exchange_lock:
            expected = HEADER.unpack_from(payload)
            while True:
                try:
                    self._responses.get_nowait()
                except queue.Empty:
                    break
            projection = bridge_pb2.ToRadioBridge(usb_sf=payload)
            envelope = mesh_pb2.ToRadio.FromString(projection.SerializeToString())
            # Unknown protobuf fields survive; the SDK supplies serial framing.
            if not self.stream:
                raise OSError("USB stream is closed")
            self._sendToRadioImpl(envelope)
            deadline = time.monotonic() + timeout
            while True:
                try:
                    response = self._responses.get(timeout=max(0, deadline - time.monotonic()))
                except queue.Empty as exc:
                    raise TimeoutError("USB bridge response timeout") from exc
                if len(response) >= HEADER.size:
                    fields = HEADER.unpack_from(response)
                    if fields[4:6] == expected[4:6]:
                        return response
