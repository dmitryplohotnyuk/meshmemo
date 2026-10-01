"""Cross-process ownership for a capture/server using one local archive.

The OS releases the lock on exit, including crashes. Keep the lock file in place:
unlinking it while another process waits could create two independently locked files.
Readers and the backup command do not need ownership. Use a local filesystem.
"""

import os
from pathlib import Path


class ArchiveInUse(RuntimeError):
    pass


class ArchiveOwner:
    def __init__(self, database):
        self.path = Path(str(Path(database).resolve()) + ".lock")
        self.fd = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            if os.name == "nt":
                import msvcrt

                if os.fstat(fd).st_size == 0:
                    os.write(fd, b"\0")
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            os.close(fd)
            raise ArchiveInUse("Archive is already in use by another capture/server process") from exc
        self.fd = fd
        return self

    def __exit__(self, *_):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
