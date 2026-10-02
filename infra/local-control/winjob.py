"""Windows Job Object：启动器先入组，随后创建的完整进程树由中控持有。"""

import ctypes
from ctypes import wintypes as W
from pathlib import Path
import subprocess
import sys
import time
import uuid

# Windows 原生常量与结构体遵循 Job Objects API 布局。
KERNEL = ctypes.WinDLL('kernel32', use_last_error=True)
EXTENDED_LIMIT_CLASS, BASIC_ACCOUNTING_CLASS = 9, 1
KILL_ON_CLOSE, JOB_ALL_ACCESS = 0x2000, 0x1F003F
JOB_PREFIX = 'LocalControl-'
HOST_MODE = '--host'


class BasicLimits(ctypes.Structure):
    # 原生时间、标志、工作集、进程数、亲和性和调度字段。
    _fields_ = [('process_time', ctypes.c_int64), ('job_time', ctypes.c_int64),
                ('flags', W.DWORD), ('minimum_ws', ctypes.c_size_t),
                ('maximum_ws', ctypes.c_size_t), ('active_limit', W.DWORD),
                ('affinity', ctypes.c_size_t), ('priority', W.DWORD), ('scheduling', W.DWORD)]


class ExtendedLimits(ctypes.Structure):
    # 六个 IO 计数和四个内存计数按系统结构排列；本程序只设置 flags。
    _fields_ = [('basic', BasicLimits), ('io', ctypes.c_uint64 * 6),
                ('memory', ctypes.c_size_t * 4)]


class Accounting(ctypes.Structure):
    # 活动进程计数用于确认整组已退出，不能仅等待根进程。
    _fields_ = [('times', ctypes.c_int64 * 4), ('page_faults', W.DWORD),
                ('total', W.DWORD), ('active', W.DWORD), ('terminated', W.DWORD)]


# 明确 64 位 HANDLE 参数和返回值，避免 ctypes 默认截断指针。
KERNEL.CreateJobObjectW.argtypes = (ctypes.c_void_p, W.LPCWSTR)
KERNEL.CreateJobObjectW.restype = W.HANDLE
KERNEL.OpenJobObjectW.argtypes = (W.DWORD, W.BOOL, W.LPCWSTR)
KERNEL.OpenJobObjectW.restype = W.HANDLE
KERNEL.SetInformationJobObject.argtypes = (W.HANDLE, ctypes.c_int, ctypes.c_void_p, W.DWORD)
KERNEL.QueryInformationJobObject.argtypes = (W.HANDLE, ctypes.c_int, ctypes.c_void_p, W.DWORD, ctypes.c_void_p)
KERNEL.AssignProcessToJobObject.argtypes = (W.HANDLE, W.HANDLE)
KERNEL.TerminateJobObject.argtypes = (W.HANDLE, W.UINT)
KERNEL.GetCurrentProcess.restype = W.HANDLE
KERNEL.CloseHandle.argtypes = (W.HANDLE,)


def checked(result):
    if not result:
        raise ctypes.WinError(ctypes.get_last_error())
    return result


class ProcessJob:
    def __init__(self):
        # 随机名称只用于本机启动器握手，不保存 PID 或复用旧任务。
        self.name = JOB_PREFIX + uuid.uuid4().hex
        self.handle = checked(KERNEL.CreateJobObjectW(None, self.name))
        limits = ExtendedLimits()
        limits.basic.flags = KILL_ON_CLOSE
        try:
            checked(KERNEL.SetInformationJobObject(self.handle, EXTENDED_LIMIT_CLASS,
                                                   ctypes.byref(limits), ctypes.sizeof(limits)))
        except Exception:
            KERNEL.CloseHandle(self.handle)
            self.handle = None
            raise

    def command(self, arguments):
        # host 自身加入组后才运行实际命令，避免“先 spawn 后入组”的竞态。
        return [sys.executable, str(Path(__file__).resolve()), HOST_MODE, self.name, *arguments]

    def close(self):
        if self.handle is None:
            return
        checked(KERNEL.TerminateJobObject(self.handle, 1))
        deadline = time.monotonic() + 8
        while True:
            accounting = Accounting()
            checked(KERNEL.QueryInformationJobObject(self.handle, BASIC_ACCOUNTING_CLASS,
                    ctypes.byref(accounting), ctypes.sizeof(accounting), None))
            if not accounting.active:
                break
            if time.monotonic() >= deadline:
                raise TimeoutError('仍有受管子进程未退出，请重试停止')
            time.sleep(0.05)
        checked(KERNEL.CloseHandle(self.handle))
        self.handle = None


def host(name, command):
    # 仅在组存在且成功加入时启动服务；主客户端先退出则握手失败并安全退出。
    handle = checked(KERNEL.OpenJobObjectW(JOB_ALL_ACCESS, False, name))
    try:
        checked(KERNEL.AssignProcessToJobObject(handle, KERNEL.GetCurrentProcess()))
    finally:
        KERNEL.CloseHandle(handle)
    return subprocess.call(command)


if __name__ == '__main__':
    if len(sys.argv) < 4 or sys.argv[1] != HOST_MODE:
        raise SystemExit('此文件仅由中控内部启动')
    raise SystemExit(host(sys.argv[2], sys.argv[3:]))
