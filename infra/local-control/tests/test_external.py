"""验证外部服务身份匹配及按显式操作停止，不触碰工作区业务服务。"""

from dataclasses import replace
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from config import DATA_AGENT, DATA_AGENT_WEB, ServiceSpec, load_services
from external import ProcessInfo, matches_service, identify, stop_external
from runtime import ServiceRunner, RUNNING_EXTERNAL, STOPPED, RUNNING, FAILED

# 临时 Node 服务使用与 Vite 相同的入口路径，健康检查由真实监听端口提供。
NODE_SERVER = "require('http').createServer((req,res)=>res.end('ok')).listen(Number(process.argv[2]),'127.0.0.1')"


class IdentityTest(unittest.TestCase):
    def info(self, executable, command):
        return ProcessInfo(42, 123, 7, executable, command)

    def test_java_jar_and_idea_argfile_require_this_project(self):
        root = Path(__file__).resolve().parents[3]
        spec = next(spec for spec in load_services(root) if spec.key == DATA_AGENT)
        jar = spec.command[spec.command.index('-jar') + 1]
        self.assertTrue(matches_service(spec, [self.info('java.exe', f'java -jar "{jar}"')]))
        self.assertFalse(matches_service(spec, [self.info('java.exe', 'java -jar C:/elsewhere/app.jar')]))
        with tempfile.TemporaryDirectory() as directory:
            args = Path(directory) / 'idea_args.txt'
            args.write_text(f'-classpath "{root / "data-agent/backend/app/target/classes"}"\ncom.datagent.DataAgentApplication', encoding='utf-8')
            self.assertTrue(matches_service(spec, [self.info('java.exe', f'java "@{args}"')]))

    def test_frontend_normalizes_vite_bin_path_and_rejects_other_workspace(self):
        root = Path(__file__).resolve().parents[3]
        spec = next(spec for spec in load_services(root) if spec.key == DATA_AGENT_WEB)
        command = f'node "{spec.cwd}/node_modules/.bin/../vite/bin/vite.js"'
        self.assertTrue(matches_service(spec, [self.info('node.exe', command)]))
        self.assertFalse(matches_service(spec, [self.info('node.exe', command.replace('frontend', 'frontend-copy'))]))
        self.assertFalse(matches_service(spec, [self.info('node.exe', 'node other.js')]))

    def test_dbt_redirected_python_uses_verified_venv_parent(self):
        root = Path(__file__).resolve().parents[3]
        spec = next(spec for spec in load_services(root) if spec.key == 'dbt')
        child = self.info('C:/uv/python.exe', 'python.exe -m dbt_metricflow_service.main')
        parent = self.info(str(spec.cwd / '.venv/Scripts/python.exe'),
                           f'"{spec.cwd}/.venv/Scripts/python.exe" -m dbt_metricflow_service.main')
        self.assertTrue(matches_service(spec, [child, parent]))
        activated_parent = replace(parent, command='python -m dbt_metricflow_service.main')
        self.assertTrue(matches_service(spec, [child, activated_parent]))
        self.assertFalse(matches_service(spec, [child]))
        self.assertFalse(matches_service(spec, [self.info('python.exe', 'python.exe other.py'), parent]))


@unittest.skipUnless(os.name == 'nt' and shutil.which('node'), '需要 Windows 和工作区已有的 Node')
class ExternalLifecycleTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='external service ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.script = self.root / 'node_modules/vite/bin/vite.js'
        self.script.parent.mkdir(parents=True)
        self.script.write_text(NODE_SERVER, encoding='utf-8')
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            self.port = listener.getsockname()[1]
        self.spec = ServiceSpec(key='fixture-web', name='外部前端', cwd=self.root,
            command=(shutil.which('node'), str(self.script), str(self.port)),
            port=self.port, root=self.root, frontend=True)
        self.process = subprocess.Popen(self.spec.command, cwd=self.root,
            creationflags=subprocess.CREATE_NO_WINDOW, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(self.cleanup_process)
        self.runner = ServiceRunner(self.spec, self.root / 'logs')
        self.addCleanup(self.cleanup_runner)

    def cleanup_process(self):
        if self.process.poll() is None:
            self.process.terminate()
        self.process.wait(timeout=10)

    def cleanup_runner(self):
        self.runner.stop(managed_only=True)
        self.runner.wait_idle(10)
        self.runner.close_logs()

    def wait_for(self, predicate):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            self.runner.refresh()
            if predicate(self.runner.view()):
                return self.runner.view()
            time.sleep(0.1)
        self.fail(str(self.runner.view()))

    def test_recognizes_external_pid_and_stops_only_on_request(self):
        view = self.wait_for(lambda view: view.status == RUNNING_EXTERNAL)
        self.assertEqual(view.pid, self.process.pid)
        self.assertTrue(view.external)
        self.assertFalse(self.runner.start())
        self.assertTrue(self.runner.stop())
        self.assertTrue(self.runner.wait_idle(10))
        self.process.wait(timeout=10)
        self.runner.refresh()
        self.assertEqual(self.runner.view().status, STOPPED)

    def test_restart_replaces_external_service_with_managed_service(self):
        self.wait_for(lambda view: view.status == RUNNING_EXTERNAL)
        self.assertTrue(self.runner.restart())
        view = self.wait_for(lambda view: view.status == RUNNING)
        self.assertFalse(view.external)
        self.assertNotEqual(view.pid, self.process.pid)
        self.assertIsNotNone(self.process.poll())

    def test_close_cleanup_preserves_external_service(self):
        self.wait_for(lambda view: view.status == RUNNING_EXTERNAL)
        self.runner.stop(managed_only=True)
        self.runner.wait_idle(10)
        self.assertIsNone(self.process.poll())

    def test_close_during_discovery_preserves_external_service(self):
        self.check_close_during_discovery(restart=False)

    def test_close_during_restart_discovery_preserves_external_service(self):
        self.check_close_during_discovery(restart=True)

    def check_close_during_discovery(self, restart):
        # 启动期间才识别到外部服务时，关闭请求仍不得终止它。
        self.wait_for(lambda view: view.status == RUNNING_EXTERNAL)
        fresh = ServiceRunner(self.spec, self.root / 'fresh-logs')
        entered, release = threading.Event(), threading.Event()
        inspect = fresh._inspect_external

        def delayed_inspect():
            entered.set()
            release.wait(10)
            return inspect()

        try:
            with patch.object(fresh, '_inspect_external', side_effect=delayed_inspect):
                self.assertTrue(fresh.restart() if restart else fresh.start())
                self.assertTrue(entered.wait(10))
                fresh.stop(managed_only=True)
                release.set()
                self.assertTrue(fresh.wait_idle(10))
                self.assertIsNone(self.process.poll())
        finally:
            release.set()
            fresh.wait_idle(10)
            fresh.close_logs()

    def test_failed_build_then_external_service_can_be_stopped(self):
        # 失败构建遗留的 Popen 不得覆盖随后识别到的外部服务。
        self.process.terminate()
        self.process.wait(timeout=10)
        self.runner.spec = replace(self.spec, build=(sys.executable, '-c', 'raise SystemExit(1)'))
        self.assertTrue(self.runner.start())
        self.assertTrue(self.runner.wait_idle(10))
        self.assertEqual(self.runner.view().status, FAILED)
        self.process = subprocess.Popen(self.spec.command, cwd=self.root,
            creationflags=subprocess.CREATE_NO_WINDOW, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.wait_for(lambda view: view.status == RUNNING_EXTERNAL)
        self.runner.refresh()
        self.assertEqual(self.runner.view().status, RUNNING_EXTERNAL)
        self.runner.stop()
        self.assertTrue(self.runner.wait_idle(10))
        self.process.wait(timeout=10)

    def test_window_controls_external_and_close_preserves_it(self):
        # 真实窗口必须开放显式停止/重启，关闭窗口仍保留外部进程。
        import tkinter as tk
        from app import ControlApp, START, STOP, RESTART
        self.wait_for(lambda view: view.status == RUNNING_EXTERNAL)
        window = tk.Tk()
        app = ControlApp(window, self.root, [self.runner])
        try:
            window.update()
            app._render()
            self.assertEqual(str(app.navigation.items[self.spec.key]['buttons'][START]['state']), 'disabled')
            self.assertEqual(str(app.navigation.items[self.spec.key]['buttons'][STOP]['state']), 'normal')
            self.assertEqual(str(app.navigation.items[self.spec.key]['buttons'][RESTART]['state']), 'normal')
            app.close()
            deadline = time.monotonic() + 10
            while not app._shutdown.is_set() and time.monotonic() < deadline:
                window.update()
                time.sleep(0.05)
            self.assertTrue(app._shutdown.is_set())
            self.assertIsNone(self.process.poll())
        finally:
            app._shutdown.set()
            try:
                if app._after_id:
                    window.after_cancel(app._after_id)
                window.destroy()
            except tk.TclError:
                pass

    def test_stale_process_identity_is_rejected_before_termination(self):
        self.wait_for(lambda view: view.status == RUNNING_EXTERNAL)
        found = identify(self.spec)
        self.assertIsNotNone(found)
        stale = replace(found, created=found.created - 10000000)
        with self.assertRaises(RuntimeError):
            stop_external(self.spec, stale)
        self.assertIsNone(self.process.poll())

    def test_unhealthy_external_is_still_stoppable(self):
        self.runner.spec = replace(self.spec, health_path='/not-ready')
        self.script.write_text("require('http').createServer((req,res)=>{res.statusCode=503;res.end()}).listen(Number(process.argv[2]),'127.0.0.1')")
        # 已运行进程代码不会被此修改替换；通过健康端口旁的错误路径不能造假，另起真实进程。
        self.process.terminate()
        self.process.wait(timeout=10)
        self.process = subprocess.Popen(self.spec.command, cwd=self.root,
            creationflags=subprocess.CREATE_NO_WINDOW, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        view = self.wait_for(lambda view: view.external and '不健康' in view.status)
        self.assertEqual(view.pid, self.process.pid)
        self.runner.stop()
        self.assertTrue(self.runner.wait_idle(10))
        self.process.wait(timeout=10)
