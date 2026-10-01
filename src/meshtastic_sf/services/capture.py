"""Run a single archive owner; no replay scheduler is enabled here."""

import logging

from ..storage.repository import HistoryRepository
from ..transport.capture import CaptureSerialInterface
from .ingestion import Ingestor
from .ownership import ArchiveOwner


def capture(device: str, database: str, *, max_records: int) -> dict:
    with ArchiveOwner(database):
        return _capture(device, database, max_records=max_records)


def _capture(device: str, database: str, *, max_records: int) -> dict:
    # SDK debug output can contain keys in configuration frames. Only our counters are emitted.
    for name, logger in logging.Logger.manager.loggerDict.items():
        if name == "meshtastic" or name.startswith("meshtastic."):
            if isinstance(logger, logging.Logger):
                logger.disabled = True
    repository = HistoryRepository(database, max_records=max_records)
    radio = None
    stats = {"stored": 0, "duplicates": 0, "collisions": 0}
    try:
        ingestor = Ingestor(repository)
        radio = CaptureSerialInterface(device)
        print("USB capture connected. Private broadcast text only; replay disabled. Ctrl+C to stop.", flush=True)
        try:
            while True:
                frame = radio.next_frame()
                if frame is not None:
                    result = ingestor.accept(*frame)
                    if result:
                        stats["duplicates" if result.duplicate else "stored"] += 1
                        if result.collision:
                            stats["collisions"] += 1
        except KeyboardInterrupt:
            radio.close()
            # Retain queued, received frames on an orderly operator stop.
            while not radio.frames.empty() and not radio.failed.is_set():
                result = ingestor.accept(*radio.frames.get_nowait())
                if result:
                    stats["duplicates" if result.duplicate else "stored"] += 1
                    if result.collision:
                        stats["collisions"] += 1
            if radio.failed.is_set():
                raise RuntimeError("Capture queue failed; some frames were not archived")
        return stats
    finally:
        if radio is not None:
            radio.close()
        repository.close()
