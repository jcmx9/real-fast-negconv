"""Facts about this computer: memory and the automatic number of workers."""

import os
import sys

GIB = 1024**3
MEMORY_PER_WORKER = 4 * GIB


def total_memory_bytes() -> int:
    """Physical memory, or 8 GiB when the OS does not tell us."""
    if sys.platform == "win32":
        return _windows_total_memory() or 8 * GIB
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (AttributeError, ValueError, OSError):
        return 8 * GIB


def _windows_total_memory() -> int | None:
    """Total physical memory via GlobalMemoryStatusEx, None on failure."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    class MemoryStatusEx(ctypes.Structure):
        _fields_ = (
            ("dwLength", wintypes.DWORD),
            ("dwMemoryLoad", wintypes.DWORD),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        )

    status = MemoryStatusEx()
    status.dwLength = ctypes.sizeof(MemoryStatusEx)
    try:
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return None
    except (AttributeError, OSError):
        return None
    return int(status.ullTotalPhys)


def automatic_workers() -> int:
    """parallel_jobs = 0 on this machine: min(CPUs, half the RAM / 4 GiB)."""
    by_memory = max(1, int(total_memory_bytes() * 0.5 // MEMORY_PER_WORKER))
    return max(1, min(os.cpu_count() or 1, by_memory))
