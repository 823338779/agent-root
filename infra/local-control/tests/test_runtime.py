"""使用隔离端口和临时 Python 服务验证真实进程生命周期。"""

from dataclasses import replace
from pathlib import Path
import socket
import json
import subprocess
import sys
import tempfile
import time
import unittest

from config import ServiceSpec
from runtime import ServiceRunner, RUNNING, STOPPED, EXTERNAL, FAILED, EXITED

# 测试服务只有健康端点，可根据临时文件返回不健康或主动退出。
SERVER = '''import http.server, pathlib, sys, subprocess
if len(sys.argv) > 2:
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])
    pathlib.Path('child.pid').write_text(str(child.pid))
class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(503 if pathlib.Path('unhealthy').exists() else 200)
        self.end_headers()
        self.wfile.write(b'{"status":"UP"}')
    def log_message(self, *args): pass
http.server.HTTPServer(('127.0.0.1', int(sys.argv[1])), Handler).serve_forever()
'''


class RuntimeTest(unittest.TestCase):
    """每例只操作自己创建的临时服务，结束后清理。"""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='中控 space ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.script = self.root / 'server.py'
        self.script.write_text(SERVER, encoding='utf-8')
        self.source = self.root / 'source.py'
        self.source.write_text('old', encoding='utf-8')
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            self.port = listener.getsockname()[1]
        self.spec = ServiceSpec(key='test', name='测试服务', cwd=self.root,
                                command=(sys.executable, str(self.script), str(self.port)),
                                port=self.port, watch_paths=(self.source,), root=self.root,
                                startup_timeout=0.5)
        self.runner = ServiceRunner(self.spec, self.root / 'logs')
        self.addCleanup(self.cleanup_runner)

    def cleanup_runner(self):
        self.runner.stop()
        self.runner.wait_idle(10)
        self.runner.close_logs()

    def wait_for(self, predicate, timeout=8):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.runner.refresh()
            if predicate(self.runner.view()):
                return self.runner.view()
            time.sleep(0.05)
        self.fail(str(self.runner.view()))

    def test_start_duplicate_stop_and_change_baseline(self):
        self.assertTrue(self.runner.start())
        running = self.wait_for(lambda view: view.status == RUNNING)
        self.assertFalse(self.runner.start())
        self.source.write_text('new', encoding='utf-8')
        changed = self.wait_for(lambda view: bool(view.changes))
        self.assertEqual(changed.pid, running.pid)
        self.assertEqual(changed.changes, {'source.py': '修改'})
        self.assertTrue(self.runner.restart())
        restarted = self.wait_for(lambda view: view.status == RUNNING and not view.changes)
        self.assertNotEqual(restarted.pid, running.pid)
        self.runner.stop()
        self.runner.wait_idle(8)
        self.runner.refresh()
        self.assertEqual(self.runner.view().status, STOPPED)

    def test_external_port_is_never_taken_over_or_stopped(self):
        external = subprocess.Popen(self.spec.command, cwd=self.root,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(external.wait, 8)
        self.addCleanup(external.terminate)
        self.wait_for(lambda view: view.status == EXTERNAL)
        self.assertFalse(self.runner.start())
        self.assertFalse(self.runner.restart())
        self.runner.stop()
        self.runner.wait_idle(5)
        self.assertIsNone(external.poll())

    def test_build_failure_preserves_change_notification(self):
        self.source.write_text('new', encoding='utf-8')
        self.runner.spec = replace(self.spec, build=(sys.executable, '-c', 'raise SystemExit(7)'))
        self.runner.start()
        view = self.wait_for(lambda view: view.status == FAILED)
        self.assertIn('source.py', view.changes)
        self.assertIn('7', view.detail)

    def test_changes_during_build_survive_successful_restart(self):
        self.source.write_text('first', encoding='utf-8')
        marker = self.root / 'building'
        self.runner.spec = replace(self.spec, build=(sys.executable, '-c',
            "import pathlib,time; pathlib.Path('building').touch(); time.sleep(0.6)"))
        self.runner.start()
        self.wait_for(lambda view: marker.exists())
        self.source.write_text('during build', encoding='utf-8')
        view = self.wait_for(lambda view: view.status == RUNNING)
        self.assertEqual(view.changes, {'source.py': '修改'})

    def test_cancel_build_never_runs_service(self):
        self.runner.spec = replace(self.spec, build=(sys.executable, '-c', 'import time; time.sleep(90)'))
        self.runner.start()
        self.wait_for(lambda view: view.pid is not None)
        self.runner.stop()
        self.assertTrue(self.runner.wait_idle(8))
        self.runner.refresh()
        self.assertEqual(self.runner.view().status, STOPPED)
        with socket.socket() as connection:
            self.assertNotEqual(connection.connect_ex(('127.0.0.1', self.port)), 0)

    def test_stop_interrupts_build_started_by_restart(self):
        self.runner.spec = replace(self.spec, build=(sys.executable, '-c', 'import time; time.sleep(90)'))
        self.runner.restart()
        self.wait_for(lambda view: view.pid is not None)
        self.assertTrue(self.runner.stop())
        self.assertTrue(self.runner.wait_idle(8))
        self.assertIsNone(self.runner.view().pid)

    def test_restart_reloads_configuration(self):
        self.source.write_text('new', encoding='utf-8')
        self.runner.spec_loader = lambda: replace(self.spec,
            command=(sys.executable, '-c', 'raise SystemExit(23)'))
        self.runner.start()
        view = self.wait_for(lambda view: view.status == EXITED)
        self.assertIn('23', view.detail)
        self.assertIn('source.py', view.changes)

    def test_unhealthy_launch_does_not_accept_new_baseline(self):
        self.source.write_text('new', encoding='utf-8')
        (self.root / 'unhealthy').touch()
        self.runner.start()
        view = self.wait_for(lambda view: view.status == '不健康')
        self.assertIn('source.py', view.changes)

    def test_unexpected_process_exit_is_not_reported_as_stopped(self):
        self.runner.spec = replace(self.spec, command=(sys.executable, '-c', 'raise SystemExit(9)'))
        self.runner.start()
        view = self.wait_for(lambda view: view.status == EXITED)
        self.assertIn('9', view.detail)

    @unittest.skipUnless(sys.platform == 'win32', 'Windows 批处理参数边界')
    def test_batch_command_preserves_unicode_and_spaces(self):
        capture = self.root / 'capture.py'
        capture.write_text("import json,pathlib,sys; pathlib.Path('args.json').write_text(json.dumps(sys.argv[1:]))",
                           encoding='utf-8')
        batch = self.root / 'launch service.cmd'
        batch.write_text('@echo off\n"' + sys.executable + '" "%~dp0capture.py" %*\n', encoding='utf-8')
        self.runner.spec = replace(self.spec, command=(str(batch), 'two words', '中文参数'))
        self.runner.start()
        self.wait_for(lambda view: view.status == EXITED)
        self.assertEqual(json.loads((self.root / 'args.json').read_text()), ['two words', '中文参数'])

    def test_stop_cleans_up_spawned_child_process(self):
        self.runner.spec = replace(self.spec, command=(*self.spec.command, 'child'))
        self.runner.start()
        self.wait_for(lambda view: view.status == RUNNING)
        child_pid = int((self.root / 'child.pid').read_text())
        self.runner.stop()
        self.assertTrue(self.runner.wait_idle(8))
        if sys.platform == 'win32':
            import ctypes
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.OpenProcess.restype = ctypes.c_void_p
            kernel.CloseHandle.argtypes = (ctypes.c_void_p,)
            handle = kernel.OpenProcess(0x100000, False, child_pid)
            if handle:
                kernel.WaitForSingleObject.argtypes = (ctypes.c_void_p, ctypes.c_ulong)
                self.assertEqual(kernel.WaitForSingleObject(handle, 1000), 0)
                kernel.CloseHandle(handle)

    @unittest.skipUnless(sys.platform == 'win32', 'Windows 进程组')
    def test_parent_exit_does_not_orphan_child(self):
        script = "import subprocess,sys,pathlib; child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); pathlib.Path('child.pid').write_text(str(child.pid))"
        self.runner.spec = replace(self.spec, command=(sys.executable, '-c', script))
        self.runner.start()
        self.wait_for(lambda view: view.status == EXITED)
        child_pid = int((self.root / 'child.pid').read_text())
        self.runner.stop()
        self.assertTrue(self.runner.wait_idle(8))
        import ctypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.CloseHandle.argtypes = (ctypes.c_void_p,)
        kernel.WaitForSingleObject.argtypes = (ctypes.c_void_p, ctypes.c_ulong)
        handle = kernel.OpenProcess(0x100000, False, child_pid)
        if handle:
            try:
                self.assertEqual(kernel.WaitForSingleObject(handle, 1000), 0)
            finally:
                kernel.CloseHandle(handle)


if __name__ == '__main__':
    unittest.main()
