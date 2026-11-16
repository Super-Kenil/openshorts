import msvcrt
import os
import time

LOCK_SH = 1
LOCK_EX = 2
LOCK_NB = 4
LOCK_UN = 8


def flock(fd, op):
    fileno = fd if isinstance(fd, int) else fd.fileno()
    pos = os.lseek(fileno, 0, os.SEEK_CUR)
    os.lseek(fileno, 0, os.SEEK_SET)
    try:
        if op & LOCK_UN:
            try:
                msvcrt.locking(fileno, msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
            return
        if op & LOCK_NB:
            msvcrt.locking(fileno, msvcrt.LK_NBLCK, 1)
            return
        while True:
            try:
                msvcrt.locking(fileno, msvcrt.LK_NBLCK, 1)
                return
            except OSError:
                time.sleep(0.05)
    finally:
        os.lseek(fileno, pos, os.SEEK_SET)
