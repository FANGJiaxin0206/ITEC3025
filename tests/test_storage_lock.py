import threading
import unittest
from unittest.mock import patch
from mediconfirm.storage_lock import StorageLock


class StorageLockTests(unittest.TestCase):
    def test_nested_acquisition_is_reentrant(self):
        lock=StorageLock()
        with lock:
            with lock:
                self.assertTrue(lock.file_lock.is_locked)
                self.assertEqual(lock.file_lock.lock_counter,2)
            self.assertTrue(lock.file_lock.is_locked)
        self.assertFalse(lock.file_lock.is_locked)

    def test_exception_does_not_leave_lock_held(self):
        lock=StorageLock()
        with self.assertRaises(ValueError):
            with lock:raise ValueError('test')
        self.assertFalse(lock.file_lock.is_locked)
        with lock:self.assertTrue(lock.file_lock.is_locked)

    def test_failed_acquisition_releases_thread_mutex(self):
        lock=StorageLock()
        with patch.object(lock.file_lock,'acquire',side_effect=OSError('test')):
            with self.assertRaises(OSError):
                with lock:pass
        acquired=[]
        def worker():
            with lock:acquired.append(True)
        thread=threading.Thread(target=worker,daemon=True);thread.start();thread.join(timeout=3)
        self.assertEqual(acquired,[True])

    def test_other_thread_cannot_enter_until_outer_exit(self):
        lock=StorageLock();entered=threading.Event();attempting=threading.Event()
        def worker():
            attempting.set()
            with lock:entered.set()
        with lock:
            with lock:
                thread=threading.Thread(target=worker,daemon=True);thread.start()
                self.assertTrue(attempting.wait(2))
                self.assertFalse(entered.wait(.1))
            self.assertFalse(entered.is_set())
        thread.join(timeout=3)
        self.assertTrue(entered.is_set())
