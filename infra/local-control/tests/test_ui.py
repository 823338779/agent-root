"""在真实 Tk 窗口中验证服务按钮与无弹窗变更提示。"""

from pathlib import Path
import socket
import sys
import tempfile
import time
import tkinter as tk
import unittest
from unittest.mock import patch

from app import ControlApp, START
from config import ServiceSpec
from runtime import ServiceRunner, RUNNING


class WindowTest(unittest.TestCase):
    def test_buttons_change_badge_and_close_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            source = folder / 'source.py'
            source.write_text('before', encoding='utf-8')
            with socket.socket() as listener:
                listener.bind(('127.0.0.1', 0))
                port = listener.getsockname()[1]
            spec = ServiceSpec(key='ui-test', name='交互测试服务', cwd=folder,
                               command=(sys.executable, '-m', 'http.server', str(port),
                                        '--bind', '127.0.0.1'),
                               port=port, root=folder, watch_paths=(source,), frontend=True)
            runner = ServiceRunner(spec, folder / 'logs')
            window = tk.Tk()
            app = ControlApp(window, folder, [runner])

            def pump_until(predicate, timeout=10):
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    window.update()
                    if predicate():
                        return
                    time.sleep(0.05)
                self.fail('窗口未达到预期状态')

            try:
                pump_until(lambda: app._selected_key == spec.key)
                window.geometry('960x640')
                window.update()
                self.assertLessEqual(app.footer_label.winfo_rooty() + app.footer_label.winfo_height(),
                                     window.winfo_rooty() + window.winfo_height())
                app.act(START)
                pump_until(lambda: runner.view().status == RUNNING)
                # 浏览器是外部边界；实际 Tk 点击事件必须传递所选前端的真实端口。
                with patch('app.webbrowser.open') as browser:
                    x, y, width, height = app.tree.bbox(spec.key, 'port')
                    app.tree.event_generate('<ButtonRelease-1>', x=x + width // 2, y=y + height // 2)
                    window.update()
                    browser.assert_called_once_with(f'http://127.0.0.1:{port}/')
                source.write_text('after', encoding='utf-8')
                pump_until(lambda: '代码已变更' in app.tree.item(spec.key)['values'][-1])
                self.assertIn('source.py', app.changes.get('1.0', 'end'))
                self.assertEqual(len(window.winfo_children()), 1)
                app.close()
                pump_until(lambda: app._shutdown.is_set())
                self.assertIsNone(runner.view().pid)
            finally:
                app._shutdown.set()
                runner.stop()
                runner.wait_idle(10)
                runner.close_logs()
                try:
                    if app._after_id:
                        window.after_cancel(app._after_id)
                    window.destroy()
                except tk.TclError:
                    pass
