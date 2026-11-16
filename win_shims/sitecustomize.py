import os
import subprocess

if os.name == "nt":
    _Popen = subprocess.Popen

    class _WinPopen(_Popen):
        def __init__(self, *args, **kwargs):
            kwargs.pop("preexec_fn", None)
            super().__init__(*args, **kwargs)

    subprocess.Popen = _WinPopen
