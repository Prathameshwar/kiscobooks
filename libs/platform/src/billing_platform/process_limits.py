"""Hard memory limits for expendable child processes, before expensive imports.

Call only inside a dedicated child. The Windows job handle stays alive for the
process lifetime; Linux uses an address-space limit. Neither mutates its parent.
"""

import ctypes
import sys
from typing import Any, ClassVar

_JOB: int | None = None


def memory_limit(maximum_bytes: int) -> None:
    global _JOB
    if maximum_bytes < 16 * 1024 * 1024:
        raise ValueError("process memory limit is too small")
    if sys.platform != "win32":
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (maximum_bytes, maximum_bytes))
        return

    class Basic(ctypes.Structure):
        _fields_: ClassVar[list[tuple[str, Any]]] = [
            ("process_time", ctypes.c_longlong),
            ("job_time", ctypes.c_longlong),
            ("flags", ctypes.c_ulong),
            ("minimum_working_set", ctypes.c_size_t),
            ("maximum_working_set", ctypes.c_size_t),
            ("active_processes", ctypes.c_ulong),
            ("affinity", ctypes.c_size_t),
            ("priority", ctypes.c_ulong),
            ("scheduling", ctypes.c_ulong),
        ]

    class Io(ctypes.Structure):
        _fields_: ClassVar[list[tuple[str, Any]]] = [
            (name, ctypes.c_ulonglong)
            for name in (
                "read_operations",
                "write_operations",
                "other_operations",
                "read_bytes",
                "write_bytes",
                "other_bytes",
            )
        ]

    class Extended(ctypes.Structure):
        _fields_: ClassVar[list[tuple[str, Any]]] = [
            ("basic", Basic),
            ("io", Io),
            ("process_memory", ctypes.c_size_t),
            ("job_memory", ctypes.c_size_t),
            ("peak_process_memory", ctypes.c_size_t),
            ("peak_job_memory", ctypes.c_size_t),
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True, winmode=0x00000800)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
    kernel.CreateJobObjectW.restype = ctypes.c_void_p
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    kernel.SetInformationJobObject.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_ulong,
    ]
    kernel.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.CreateJobObjectW(None, None)
    if not handle:
        raise OSError("cannot create render process memory boundary")
    limits = Extended()
    limits.basic.flags = 0x00000100  # JOB_OBJECT_LIMIT_PROCESS_MEMORY
    limits.process_memory = maximum_bytes
    if not kernel.SetInformationJobObject(
        handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)
    ) or not kernel.AssignProcessToJobObject(handle, kernel.GetCurrentProcess()):
        kernel.CloseHandle(handle)
        raise OSError("cannot enforce render process memory boundary")
    _JOB = handle
