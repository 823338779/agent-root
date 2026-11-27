"""识别监听端口的本工作区服务；显式操作时校验进程身份再终止。"""

import base64
from contextlib import contextmanager
import ctypes
from ctypes import wintypes as W
from dataclasses import dataclass
import json
import ntpath
import os
from pathlib import Path
import socket
import subprocess
import threading

from config import DATA_AGENT, ServiceSpec, split_arguments

# 只读取 TCP 监听表；进程信息按 PID 与创建时间缓存，避免反复启动 PowerShell。
WINDOWS = 'nt'
TCP_LISTENERS, INSUFFICIENT_BUFFER = 3, 122
AF_INET, AF_INET6 = 2, 23
SYNCHRONIZE_QUERY = 0x100000 | 0x1000
WAIT_TIMEOUT = 258
JAVA_NAMES = frozenset({'java.exe', 'javaw.exe'})
PYTHON_NAMES = frozenset({'python.exe', 'pythonw.exe'})
JAVA_MAIN = {'metric': 'com.metricplatform.MetricPlatformApplication',
             DATA_AGENT: 'com.datagent.DataAgentApplication'}
PROJECTS = {'metric': 'metric-platform', DATA_AGENT: DATA_AGENT}
NODE_NAME, VITE_ENTRY = 'node.exe', 'node_modules/vite/bin/vite.js'
DBT_MODULE = 'dbt_metricflow_service.main'
DBT_ENTRY = 'src/dbt_metricflow_service/main.py'
VENV_PYTHON = '.venv/Scripts/python.exe'
JAR_FLAG, MODULE_FLAG = '-jar', '-m'
ENCODING, PS_ENCODING = 'utf-8-sig', 'utf-16-le'
ARGFILE_BREAKS = str.maketrans({'\r': ' ', '\n': ' '})
TASKKILL = 'taskkill.exe'
STOP_ERROR = '外部服务身份或端口归属已改变，请等待状态刷新后重试'
PS_QUERY = '''[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$localControlPid = PID_PLACEHOLDER
$localControlResult = @()
$localControlChildCreated = [long]::MaxValue
for ($localControlDepth = 0; $localControlDepth -lt 3 -and $localControlPid -gt 0; $localControlDepth++) {
    $localControlProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$localControlPid"
    if (-not $localControlProcess) { break }
    $localControlCreated = $localControlProcess.CreationDate.ToFileTimeUtc()
    if ($localControlCreated -gt $localControlChildCreated) { break }
    $localControlResult += [pscustomobject]@{
        pid = $localControlProcess.ProcessId
        created = $localControlCreated.ToString()
        parent = $localControlProcess.ParentProcessId
        executable = $localControlProcess.ExecutablePath
        command = $localControlProcess.CommandLine
    }
    $localControlChildCreated = $localControlCreated
    $localControlPid = $localControlProcess.ParentProcessId
}
ConvertTo-Json -InputObject $localControlResult -Compress
'''
_CACHE = {}
_CACHE_LOCK = threading.Lock()


@dataclass(frozen=True)
class ProcessInfo:
    # 监听进程及父进程的系统标识。
    pid: int
    # 原生 FILETIME 创建时间，防止 PID 回收后误停其他程序。
    created: int
    # 父 PID 仅用于身份溯源，不用于终止 IDE 或终端。
    parent: int
    # 实际可执行文件路径。
    executable: str
    # 内存中使用的命令行，可能含敏感值，不输出到界面或日志。
    command: str


class TcpRow(ctypes.Structure):
    # MIB_TCPROW_OWNER_PID 的 IPv4 监听信息布局。
    _fields_ = [('state', W.DWORD), ('address', W.DWORD), ('port', W.DWORD),
                ('remote_address', W.DWORD), ('remote_port', W.DWORD), ('pid', W.DWORD)]


class Tcp6Row(ctypes.Structure):
    # MIB_TCP6ROW_OWNER_PID 的 IPv6 地址、作用域、端口和进程布局。
    _fields_ = [('address', ctypes.c_ubyte * 16), ('scope', W.DWORD), ('port', W.DWORD),
                ('remote_address', ctypes.c_ubyte * 16), ('remote_scope', W.DWORD),
                ('remote_port', W.DWORD), ('state', W.DWORD), ('pid', W.DWORD)]


def listener_pids(port: int) -> set[int]:
    # 原生查询覆盖 IPv4 和双栈 IPv6；多进程占用时不任意挑选其中一个。
    if os.name != WINDOWS:
        return set()
    api = ctypes.WinDLL('iphlpapi', use_last_error=True).GetExtendedTcpTable
    api.argtypes = (ctypes.c_void_p, ctypes.POINTER(W.DWORD), W.BOOL, W.ULONG, ctypes.c_int, W.ULONG)
    owners = set()
    for family, row_type in ((AF_INET, TcpRow), (AF_INET6, Tcp6Row)):
        size = W.DWORD()
        result = api(None, ctypes.byref(size), False, family, TCP_LISTENERS, 0)
        if result not in (0, INSUFFICIENT_BUFFER):
            raise ctypes.WinError(result)
        for _ in range(3):
            table = ctypes.create_string_buffer(size.value)
            result = api(table, ctypes.byref(size), False, family, TCP_LISTENERS, 0)
            if result != INSUFFICIENT_BUFFER:
                break
        if result:
            raise ctypes.WinError(result)
        count = W.DWORD.from_buffer_copy(table).value
        rows = (row_type * count).from_buffer_copy(table, ctypes.sizeof(W.DWORD))
        for row in rows:
            local = row.address in (0, 0x0100007F) if family == AF_INET else bytes(row.address) in (bytes(16), bytes(15) + b'\x01')
            if local and socket.ntohs(row.port & 0xFFFF) == port:
                owners.add(row.pid)
    return owners


def kernel_api():
    # 64 位进程句柄不能使用 ctypes 的默认 int 返回类型。
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = (W.DWORD, W.BOOL, W.DWORD)
    kernel.OpenProcess.restype = W.HANDLE
    kernel.GetProcessTimes.argtypes = (W.HANDLE, *([ctypes.POINTER(W.FILETIME)] * 4))
    kernel.WaitForSingleObject.argtypes = (W.HANDLE, W.DWORD)
    kernel.CloseHandle.argtypes = (W.HANDLE,)
    return kernel


@contextmanager
def pinned_process(pid: int):
    # 在识别和停止期间持有进程句柄，用创建时间核对快照，避免仅凭裸 PID 操作。
    kernel = kernel_api()
    handle = kernel.OpenProcess(SYNCHRONIZE_QUERY, False, pid)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        times = [W.FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(handle, *(ctypes.byref(value) for value in times)):
            raise ctypes.WinError(ctypes.get_last_error())
        created = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
        yield kernel, handle, created
    finally:
        kernel.CloseHandle(handle)


def process_chain(pid: int) -> tuple[ProcessInfo, ...]:
    with pinned_process(pid) as (kernel, handle, created):
        if kernel.WaitForSingleObject(handle, 0) != WAIT_TIMEOUT:
            return ()
        key = (pid, created)
        with _CACHE_LOCK:
            if key in _CACHE:
                return _CACHE[key]
        encoded = base64.b64encode(PS_QUERY.replace('PID_PLACEHOLDER', str(pid)).encode(PS_ENCODING)).decode('ascii')
        result = subprocess.run(('powershell.exe', '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded),
                                capture_output=True, timeout=10, check=True,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        values = json.loads(result.stdout.decode(ENCODING))
        chain = tuple(ProcessInfo(int(item['pid']), int(item['created']), int(item['parent']),
                                  item['executable'] or '', item['command'] or '') for item in values)
        # CIM 时间精度为微秒，原生 token 保留完整 100ns 精度。
        if not chain or chain[0].created // 10 != created // 10 or kernel.WaitForSingleObject(handle, 0) != WAIT_TIMEOUT:
            return ()
        first = chain[0]
        chain = (ProcessInfo(first.pid, created, first.parent, first.executable, first.command), *chain[1:])
        with _CACHE_LOCK:
            if len(_CACHE) >= 128:
                _CACHE.clear()
            _CACHE[key] = chain
        return chain


def normalized(path: str) -> str:
    return ntpath.normpath(path).replace('\\', '/').casefold()


def arguments(info: ProcessInfo) -> tuple[str, ...]:
    # IDEA 的 Java @argfile 存储 classpath/main；只读取绝对路径、小型参数文件。
    result = []
    for argument in split_arguments(info.command):
        if argument.startswith('@'):
            path = Path(argument[1:])
            try:
                if path.is_absolute() and path.stat().st_size <= 1024 * 1024:
                    result.extend(split_arguments(path.read_text(encoding=ENCODING).translate(ARGFILE_BREAKS)))
            except (OSError, UnicodeError, ValueError):
                pass
        else:
            result.append(argument)
    return tuple(result)


def matches_service(spec: ServiceSpec, chain: tuple[ProcessInfo, ...]) -> bool:
    if not chain:
        return False
    process = chain[0]
    name = ntpath.basename(process.executable).casefold()
    args = arguments(process)
    paths = {normalized(arg) for arg in args}
    if spec.frontend:
        return name == NODE_NAME and normalized(str(spec.cwd / VITE_ENTRY)) in paths
    if spec.key in JAVA_MAIN:
        if name not in JAVA_NAMES:
            return False
        if JAR_FLAG in args and JAR_FLAG in spec.command:
            index = args.index(JAR_FLAG) + 1
            expected = spec.command[spec.command.index(JAR_FLAG) + 1]
            if index < len(args) and normalized(args[index]) == normalized(expected):
                return True
        project = normalized(str(spec.root / PROJECTS[spec.key] / 'backend')) + '/'
        classpath = [normalized(path) for arg in args for path in arg.split(';')]
        return JAVA_MAIN[spec.key] in args and any(path.startswith(project) for path in classpath)
    if spec.key == 'dbt' and name in PYTHON_NAMES:
        if normalized(str(spec.cwd / DBT_ENTRY)) in paths:
            return True
        module = any(args[index:index + 2] == (MODULE_FLAG, DBT_MODULE) for index in range(len(args)))
        venv = normalized(str(spec.cwd / VENV_PYTHON))
        # 激活虚拟环境后 argv[0] 可仅为 python，系统可执行文件路径仍能确认身份。
        return module and any(ntpath.basename(item.executable).casefold() in PYTHON_NAMES
                              and (normalized(item.executable) == venv
                                   or venv in {normalized(arg) for arg in arguments(item)}) for item in chain)
    return False


def identify(spec: ServiceSpec) -> ProcessInfo | None:
    # 健康检查不作为产品身份凭据；端口、可执行文件和项目启动入口必须共同匹配。
    try:
        owners = listener_pids(spec.port)
        if len(owners) != 1:
            return None
        chain = process_chain(next(iter(owners)))
        return chain[0] if matches_service(spec, chain) else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def stop_external(spec: ServiceSpec, expected: ProcessInfo) -> None:
    with pinned_process(expected.pid) as (kernel, handle, created):
        if created != expected.created:
            raise RuntimeError(STOP_ERROR)
        if kernel.WaitForSingleObject(handle, 0) != WAIT_TIMEOUT:
            return
        current = identify(spec)
        if current is None or (current.pid, current.created) != (expected.pid, expected.created):
            raise RuntimeError(STOP_ERROR)
        # 只终止已确认的监听服务及其后代；IDE、终端、npm 等父进程不纳入终止范围。
        result = subprocess.run((TASKKILL, '/T', '/F', '/PID', str(expected.pid)),
                                capture_output=True, timeout=12, creationflags=subprocess.CREATE_NO_WINDOW)
        stopped = kernel.WaitForSingleObject(handle, 8000) == 0
        if not stopped:
            raise RuntimeError(f'外部服务停止失败，退出码 {result.returncode}；请检查进程权限')
