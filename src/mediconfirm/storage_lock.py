"""Serialize local JSON transactions across Notebook/web on Windows/macOS/Linux."""
import hashlib
import tempfile
import threading
from pathlib import Path

from filelock import FileLock


class StorageLock:
    def __init__(self):
        self.mutex = threading.RLock()
        key = hashlib.sha256(str(Path(__file__).resolve().parent).encode()).hexdigest()[:20]
        self.path = Path(tempfile.gettempdir()) / ('mediconfirm-' + key + '.lock')
        self.file_lock = FileLock(str(self.path))

    def __enter__(self):
        self.mutex.acquire()
        try:
            self.file_lock.acquire()
        except BaseException:
            self.mutex.release()
            raise
        return self

    def __exit__(self, *args):
        try:
            self.file_lock.release()
        finally:
            self.mutex.release()


LOCK = StorageLock()
