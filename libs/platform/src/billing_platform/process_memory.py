"""Own-process peak resident memory in bytes, without optional monitoring dependencies."""

import ctypes
import sys


def peak_rss() -> int:
    if sys.platform == "win32":

        class Counters(ctypes.Structure):
            PeakWorkingSetSize: int
            _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong)] + [
                (name, ctypes.c_size_t)
                for name in (
                    "PeakWorkingSetSize",
                    "WorkingSetSize",
                    "QuotaPeakPagedPoolUsage",
                    "QuotaPagedPoolUsage",
                    "QuotaPeakNonPagedPoolUsage",
                    "QuotaNonPagedPoolUsage",
                    "PagefileUsage",
                    "PeakPagefileUsage",
                )
            ]

        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True, winmode=0x00000800)
        kernel.GetCurrentProcess.restype = ctypes.c_void_p
        process = ctypes.WinDLL("psapi", use_last_error=True, winmode=0x00000800)
        process.GetProcessMemoryInfo.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(Counters),
            ctypes.c_ulong,
        ]
        if not process.GetProcessMemoryInfo(
            kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb
        ):
            raise OSError("process RSS unavailable")
        return int(counters.PeakWorkingSetSize)
    else:
        import resource

        value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        return value if sys.platform == "darwin" else value * 1024
