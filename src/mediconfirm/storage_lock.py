"""Serialize local JSON transactions across the Notebook and web processes."""
import fcntl
import hashlib
import tempfile
import threading
from pathlib import Path


class StorageLock:
    def __init__(self):
        self.mutex = threading.RLock()
        self.local = threading.local()
        key = hashlib.sha256(str(Path(__file__).resolve().parent).encode()).hexdigest()[:20]
        self.path = Path(tempfile.gettempdir()) / ('mediconfirm-' + key + '.lock')

    def __enter__(self):
        self.mutex.acquire()
        try:
            depth = getattr(self.local, 'depth', 0)
            if not depth:
                self.local.file = self.path.open('a')
                fcntl.flock(self.local.file.fileno(), fcntl.LOCK_EX)
            self.local.depth = depth + 1
        except BaseException:
            if getattr(self.local, 'file', None):
                self.local.file.close()
            self.mutex.release()
            raise
        return self

    def __exit__(self, *args):
        self.local.depth -= 1
        if not self.local.depth:
            try:
                fcntl.flock(self.local.file.fileno(), fcntl.LOCK_UN)
            finally:
                self.local.file.close()
        self.mutex.release()

LOCK = StorageLock()
