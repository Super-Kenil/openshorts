import os
from collections import namedtuple

RUSAGE_SELF = 0
RUSAGE_CHILDREN = -1

_Usage = namedtuple("struct_rusage", ["ru_utime", "ru_stime", "ru_maxrss"])


def getrusage(who):
    if who == RUSAGE_SELF:
        t = os.times()
        return _Usage(t.user, t.system, 0)
    t = os.times()
    return _Usage(t.children_user, t.children_system, 0)
