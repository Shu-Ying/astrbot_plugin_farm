"""跨进程发布/缓存锁；进程退出由操作系统释放，不使用永久锁标记。"""

from contextlib import contextmanager
import os
from pathlib import Path
import time


@contextmanager
def release_lock(path, timeout=180):
    path = Path(path)
    with path.open('a+b') as stream:
        if stream.seek(0, os.SEEK_END) == 0:
            stream.write(b'0')
            stream.flush()
        deadline = time.monotonic() + timeout
        if os.name == 'nt':
            import msvcrt
            def acquire():
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            def unlock():
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            def acquire():
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            def unlock():
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        while True:
            try:
                acquire()
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError('Catalogue cache is busy') from None
                time.sleep(0.05)
        try:
            yield
        finally:
            unlock()
