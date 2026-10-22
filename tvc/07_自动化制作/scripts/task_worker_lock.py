"""Serialize owners of the same shot/checkpoint, including helper processes."""
import sys,time,msvcrt
from contextlib import contextmanager

@contextmanager
def checkpoint_lock(shot):
    worker=sys.argv[sys.argv.index('--worker')+1] if '--worker' in sys.argv else 'default'
    path=shot/'reports'/('.render_worker_'+worker+'.lock')
    with path.open('a+b') as stream:
        if path.stat().st_size==0:
            stream.write(b'0');stream.flush()
        while True:
            try:
                stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1);break
            except OSError:
                time.sleep(.5)
        try:
            yield
        finally:
            stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
