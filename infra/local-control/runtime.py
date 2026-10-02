"""后台管理本客户端创建的服务进程，UI 只读取快照。"""

import base64
from collections import deque
from dataclasses import dataclass
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import signal
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request

from config import ServiceSpec, UTF8
from watcher import SourceWatcher, compare, needs_restart

# 窗口状态为文字与颜色的共同依据，不能仅凭端口就标记为运行中。
STOPPED, BUILDING, STARTING = '已停止', '构建中', '启动中'
RUNNING, UNHEALTHY, STOPPING = '运行中', '不健康', '停止中'
EXTERNAL, FAILED, EXITED = '外部运行 / 端口占用', '启动失败', '异常退出'
LOCAL_HOST = '127.0.0.1'
WINDOWS = 'nt'
PS_ENCODING = 'utf-16-le'
POWERSHELL = 'powershell.exe'
BATCH_SUFFIXES = ('.cmd', '.bat')
TASKKILL = 'taskkill.exe'
TERMINATE_FLAGS = ('/T', '/F', '/PID')
READ_ERROR = 'replace'
LINE_ENDINGS = '\r\n'
EMPTY = ''
LOG_FORMAT = '%(asctime)s %(message)s'
TIME_FORMAT = '%H:%M:%S'
SUCCESS_STATUS = frozenset({'up', 'ok', 'healthy', 'ready'})
HTTP_MESSAGE = 'HTTP {status}'
MESSAGE_START = '启动服务'
MESSAGE_BUILD = '构建最新源码'
MESSAGE_STOPPED = '服务已停止'
MESSAGE_EXTERNAL = '端口已被占用；请在原 IDE 或终端中管理该进程'
MESSAGE_EXIT = '进程退出，退出码 {code}'
MESSAGE_BUILD_FAILED = '构建失败，退出码 {code}；请查看日志'
MESSAGE_SCAN_FAILED = '源码扫描失败：{error}'
MESSAGE_STOP_FAILED = '停止失败：{error}'
MESSAGE_CANCELLED = '构建或启动已取消'
MESSAGE_TIMEOUT = '等待健康检查超时：{detail}'
MESSAGE_READY = '健康检查通过'
MESSAGE_NOT_READY = '应用报告未就绪'
LOG_SUFFIX = '.log'
PIPE_MODE = 'r'


@dataclass(frozen=True)
class ServiceView:
    # 当前运行状态，来源于进程与健康检查。
    status: str
    # 仅显示本客户端创建的进程 PID。
    pid: int | None
    # 最近一次启动、健康检查或失败原因。
    detail: str
    # 相对路径到增删改类型的映射。
    changes: dict[str, str]
    # 变化是否需要手动重启。
    restart_needed: bool
    # 是否正在执行构建、启停操作。
    busy: bool
    # 有界日志尾部，避免窗口长期运行后内存膨胀。
    logs: tuple[str, ...]
    # 文件监视失败时单独告警，不覆盖进程健康状态。
    scan_error: str


def port_open(port: int) -> bool:
    # 本地连接具有短超时；占用检测不会向服务发送业务请求。
    try:
        with socket.create_connection((LOCAL_HOST, port), timeout=0.3):
            return True
    except OSError:
        return False


def probe(spec: ServiceSpec) -> tuple[bool, str]:
    # 绕开系统 HTTP 代理，健康检查只访问本地服务。
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(spec.health_url, timeout=1) as response:
            body = response.read(65536)
            if not spec.frontend:
                try:
                    payload = json.loads(body)
                    status = payload.get('status') if isinstance(payload, dict) else None
                    if status is not None and str(status).lower() not in SUCCESS_STATUS:
                        return False, MESSAGE_NOT_READY
                except (ValueError, UnicodeError):
                    # 未返回 JSON 的 HTTP 服务仍以 HTTP 状态作为基础可用性检查。
                    pass
            return 200 <= response.status < 300, HTTP_MESSAGE.format(status=response.status)
    except urllib.error.HTTPError as error:
        error.close()
        return False, HTTP_MESSAGE.format(status=error.code)
    except (OSError, urllib.error.URLError, ValueError) as error:
        return False, str(error)


def spawn(command: tuple[str, ...], spec: ServiceSpec) -> subprocess.Popen:
    # Windows 批处理通过 PowerShell 的参数数组调用；路径里的空格及引号保持原义。
    arguments = list(command)
    if os.name == WINDOWS and arguments[0].lower().endswith(BATCH_SUFFIXES):
        quoted = ["'" + argument.replace("'", "''") + "'" for argument in arguments]
        script = '& ' + ' '.join(quoted) + '; exit $LASTEXITCODE'
        encoded = base64.b64encode(script.encode(PS_ENCODING)).decode('ascii')
        arguments = [POWERSHELL, '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded]
    job = None
    if os.name == WINDOWS:
        from winjob import ProcessJob
        job = ProcessJob()
        arguments = job.command(arguments)
    try:
        process = subprocess.Popen(
            arguments, cwd=spec.cwd, env=os.environ | spec.env,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == WINDOWS else 0,
            start_new_session=os.name != WINDOWS,
        )
        # Job 生命周期跟随本次 Popen，即使根进程先退出仍可清理子孙进程。
        process.control_job = job
        return process
    except Exception:
        if job:
            job.close()
        raise


def terminate_tree(process: subprocess.Popen) -> None:
    # 只对持有 Popen 句柄且尚在运行的进程操作，绝不按端口查找并杀进程。
    job = getattr(process, 'control_job', None)
    if job:
        job.close()
        if process.poll() is None:
            # 握手前停止时 host 可能尚未入组；该 host 不会再启动实际服务。
            process.terminate()
        process.wait(timeout=8)
        return
    if process.poll() is not None:
        return
    if os.name == WINDOWS:
        result = subprocess.run((TASKKILL, *TERMINATE_FLAGS, str(process.pid)),
                                capture_output=True, timeout=12,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode and process.poll() is None:
            raise RuntimeError(result.stderr.decode(UTF8, errors=READ_ERROR))
    else:
        os.killpg(process.pid, signal.SIGTERM)
    process.wait(timeout=8)


class ServiceRunner:
    """每个服务独立串行操作；状态、日志和源码快照由锁保护。"""

    def __init__(self, spec: ServiceSpec, log_dir: Path, spec_loader=None):
        # 稳定配置与文件基线在服务首次加入时建立。
        self.spec = spec
        # 可选配置加载器使每次重启重新读取 IDE 与本地覆盖参数。
        self.spec_loader = spec_loader
        self.watcher = SourceWatcher(spec.root, spec.watch_paths)
        self._baseline = self.watcher.capture()
        self._candidate = None
        self._changes = {}
        self._scan_error = EMPTY
        # 操作锁约束构建/启停；取消事件允许构建期间立即响应停止。
        self._lock = threading.RLock()
        self._operation = threading.Lock()
        self._refresh_lock = threading.Lock()
        self._cancel = threading.Event()
        self._stopping = False
        self._restart_requested = False
        self._process = None
        self._reader = None
        self._status = STOPPED
        self._detail = EMPTY
        self._started_at = 0.0
        # 内存和磁盘日志均设置上限，磁盘文件位于被 Git 忽略的 tmp。
        self._logs = deque(maxlen=800)
        log_dir.mkdir(parents=True, exist_ok=True)
        self._logger = logging.Logger(spec.key)
        handler = RotatingFileHandler(log_dir / (spec.key + LOG_SUFFIX),
                                      maxBytes=2 * 1024 * 1024, backupCount=1, encoding=UTF8)
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        self._logger.addHandler(handler)

    def _log(self, message: str) -> None:
        with self._lock:
            self._logs.append(time.strftime(TIME_FORMAT) + '  ' + message)
            self._logger.info(message)

    def _state(self, status: str, detail: str = EMPTY) -> None:
        with self._lock:
            self._status, self._detail = status, detail

    def view(self) -> ServiceView:
        # 返回复制快照，窗口不持有内部可变容器。
        with self._lock:
            process = self._process
            pid = process.pid if process and process.poll() is None else None
            return ServiceView(self._status, pid, self._detail, dict(self._changes),
                               needs_restart(self._changes, frontend=self.spec.frontend),
                               self._operation.locked() or self._stopping, tuple(self._logs),
                               self._scan_error)

    def _run_action(self, action) -> None:
        try:
            action()
        except Exception as error:
            self._state(FAILED, str(error))
            self._log(str(error))
        finally:
            self._operation.release()

    def start(self) -> bool:
        # 重复点击和外部端口占用均不创建第二份进程。
        with self._lock:
            if self._stopping or (self._process and self._process.poll() is None):
                return False
            if self._status == EXTERNAL or not self._operation.acquire(blocking=False):
                return False
            self._cancel.clear()
            self._state(STARTING)
            threading.Thread(target=self._run_action, args=(self._launch,), daemon=True).start()
            return True

    def _launch(self) -> None:
        if self._cancel.is_set():
            self._state(STOPPED, MESSAGE_CANCELLED)
            return
        if self.spec_loader:
            updated = self.spec_loader()
            with self._lock:
                self.spec = updated
                self.watcher = SourceWatcher(updated.root, updated.watch_paths)
        if self._process and self._process.poll() is not None:
            terminate_tree(self._process)
            self._finish_reader()
            with self._lock:
                self._process = None
        if port_open(self.spec.port):
            self._state(EXTERNAL, MESSAGE_EXTERNAL)
            return
        # 记录的是构建前源码，构建途中又保存的修改不会被成功启动吞掉。
        candidate = self.watcher.capture()
        if self.spec.build:
            self._state(BUILDING, MESSAGE_BUILD)
            self._log(MESSAGE_BUILD)
            process = self._spawn(self.spec.build)
            while process.poll() is None:
                if self._cancel.wait(0.1):
                    terminate_tree(process)
                    self._state(STOPPED, MESSAGE_CANCELLED)
                    return
            terminate_tree(process)
            self._finish_reader()
            if process.returncode:
                self._state(FAILED, MESSAGE_BUILD_FAILED.format(code=process.returncode))
                self._log(self._detail)
                return
        if self._cancel.is_set():
            self._state(STOPPED, MESSAGE_CANCELLED)
            return
        if port_open(self.spec.port):
            self._state(EXTERNAL, MESSAGE_EXTERNAL)
            return
        self._log(MESSAGE_START)
        self._spawn(self.spec.command)
        with self._lock:
            self._candidate = candidate
            self._started_at = time.monotonic()
            self._state(STARTING, MESSAGE_START)

    def _spawn(self, command: tuple[str, ...]) -> subprocess.Popen:
        if self._process and self._process.poll() is not None:
            terminate_tree(self._process)
            self._finish_reader()
        process = spawn(command, self.spec)
        with self._lock:
            self._process = process

        def consume():
            # 二进制管道以 UTF-8 容错解码；单行和累计日志均有界。
            with process.stdout:
                for line in iter(lambda: process.stdout.readline(16384), b''):
                    self._log(line.decode(UTF8, errors=READ_ERROR).rstrip(LINE_ENDINGS))

        self._reader = threading.Thread(target=consume, daemon=True)
        self._reader.start()
        return process

    def _finish_reader(self) -> None:
        if self._reader:
            self._reader.join(timeout=2)

    def _stop(self) -> None:
        with self._lock:
            process = self._process
        if process:
            terminate_tree(process)
            self._finish_reader()
        with self._lock:
            self._process = None
            self._candidate = None
            self._state(STOPPED, MESSAGE_STOPPED)
        self._log(MESSAGE_STOPPED)

    def _queue_stop(self, restart: bool) -> bool:
        # 先置取消标记，再等待当前构建退出；防止排队的重启越过停止。
        with self._lock:
            if self._stopping:
                if not restart:
                    self._restart_requested = False
                    self._cancel.set()
                    self._state(STOPPING)
                    return True
                return False
            if restart and self._status == EXTERNAL:
                return False
            self._stopping = True
            self._restart_requested = restart
            self._cancel.set()
            self._state(STOPPING)

        def action():
            with self._operation:
                try:
                    self._stop()
                    with self._lock:
                        launch = self._restart_requested
                        if launch:
                            self._cancel.clear()
                    if launch:
                        self._launch()
                        if self._cancel.is_set():
                            self._stop()
                except Exception as error:
                    self._state(FAILED, MESSAGE_STOP_FAILED.format(error=error))
                    self._log(self._detail)
                finally:
                    with self._lock:
                        self._stopping = False

        threading.Thread(target=action, daemon=True).start()
        return True

    def stop(self) -> bool:
        return self._queue_stop(False)

    def restart(self) -> bool:
        return self._queue_stop(True)

    def wait_idle(self, timeout: float = 30) -> bool:
        # 只供关闭流程与测试等待，Tk 主线程不调用此阻塞接口。
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self.view().busy:
                return True
            time.sleep(0.05)
        return False

    def refresh(self) -> None:
        # 探测和文件扫描不持状态锁，慢磁盘和失败 HTTP 不会卡住窗口。
        if not self._refresh_lock.acquire(blocking=False):
            return
        try:
            try:
                current = self.watcher.capture()
                with self._lock:
                    self._changes = compare(self._baseline, current)
                    self._scan_error = EMPTY
            except OSError as error:
                with self._lock:
                    self._scan_error = MESSAGE_SCAN_FAILED.format(error=error)
                current = None
            with self._lock:
                if self._operation.locked() or self._stopping:
                    return
                process = self._process
                status = self._status
            if process and process.poll() is None:
                healthy, detail = probe(self.spec)
                with self._lock:
                    if (self._process is not process or process.poll() is not None
                            or self._operation.locked() or self._stopping):
                        return
                    if healthy:
                        if self._candidate is not None and current is not None:
                            self._baseline = self._candidate
                            self._candidate = None
                            self._changes = compare(self._baseline, current)
                            self._log(MESSAGE_READY)
                        self._state(RUNNING, detail)
                    elif time.monotonic() - self._started_at < self.spec.startup_timeout:
                        self._state(STARTING, detail)
                    else:
                        self._state(UNHEALTHY, MESSAGE_TIMEOUT.format(detail=detail))
            elif process and status not in (FAILED, STOPPED):
                # 意外退出的清理与用户启停共用操作锁，避免同时释放 Job 句柄。
                if not self._operation.acquire(blocking=False):
                    return
                try:
                    if self._process is process and not self._stopping:
                        terminate_tree(process)
                        self._finish_reader()
                        self._state(EXITED, MESSAGE_EXIT.format(code=process.returncode))
                finally:
                    self._operation.release()
            else:
                occupied = port_open(self.spec.port)
                detail = EMPTY
                if occupied:
                    _, health_detail = probe(self.spec)
                    detail = MESSAGE_EXTERNAL + '；' + health_detail
                with self._lock:
                    if self._process is not process or self._operation.locked() or self._stopping:
                        return
                    if occupied:
                        self._state(EXTERNAL, detail)
                    elif status == EXTERNAL:
                        self._state(STOPPED)
        finally:
            self._refresh_lock.release()

    def close_logs(self) -> None:
        # 进程停止后释放日志文件，允许清理目录和再次打开客户端。
        self._finish_reader()
        for handler in self._logger.handlers:
            handler.close()
