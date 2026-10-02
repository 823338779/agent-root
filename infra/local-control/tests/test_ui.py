"""在真实 Tk 窗口中验证服务按钮与无弹窗变更提示。"""

from pathlib import Path
import gc
import socket
import sys
import tempfile
import time
import tkinter as tk
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app import ControlApp, START
from config import ServiceSpec
from runtime import ServiceRunner, ServiceView, RUNNING, STOPPED


class WindowTest(unittest.TestCase):
    def test_selection_context_actions_and_keyboard_stay_in_sync(self):
        window = tk.Tk()
        calls, runners = [], []
        for index in range(5):
            key = f'service-{index}'
            spec = ServiceSpec(key=key, name=f'服务 {index}', cwd=Path.cwd(), command=(), port=5100 + index)
            view = ServiceView(STOPPED, None, '已停止', {}, False, False, (f'日志 {index}',), '')
            # 只替代进程边界，窗口选择、键盘事件和操作路由均使用真实实现。
            runners.append(SimpleNamespace(spec=spec, refresh=lambda: None, view=lambda value=view: value,
                start=lambda selected=key: calls.append(selected) or True, stop=lambda: True, restart=lambda: True))
        app = ControlApp(window, Path.cwd(), runners)
        try:
            window.geometry('960x640')
            window.update()
            app.navigation.items['service-3']['name'].event_generate('<Button-1>')
            window.update()
            self.assertEqual(app.selected_name.get(), '服务 3')
            self.assertIn('5103', app.context.get())
            self.assertIn('日志 3', app.logs.get('1.0', 'end'))
            app.logs.focus_force()
            app._render()
            self.assertEqual(app.navigation.items['service-3']['marker'].cget('text'), '当前')
            self.assertEqual(sum(item['marker'].cget('text') == '当前' for item in app.navigation.items.values()), 1)
            app.navigation.select('service-0')
            app.navigation.items['service-3']['buttons'][START].invoke()
            self.assertEqual(calls, ['service-3'])
            self.assertEqual(app.selected_name.get(), '服务 3')
            self.assertIn('日志 3', app.logs.get('1.0', 'end'))
            row = app.navigation.items['service-3']['row']
            row.focus_force()
            window.update()
            row.event_generate('<Down>')
            window.update()
            self.assertEqual(app._selected_key, 'service-4')
            # 先放大再缩小，当前服务和操作不能留在裁切区域外。
            window.geometry('1180x860')
            window.update()
            window.geometry('960x640')
            window.update()
            last = app.navigation.items['service-4']['row']
            self.assertLessEqual(last.winfo_rooty() + last.winfo_height(),
                                 app.navigation.canvas.winfo_rooty() + app.navigation.canvas.winfo_height() + 1)
        finally:
            app._shutdown.set()
            window.after_cancel(app._after_id)
            window.destroy()
            del app, window
            gc.collect()

    def test_tabs_keep_equal_dimensions_when_selected(self):
        window = tk.Tk()
        app = ControlApp(window, Path.cwd(), [])
        try:
            # 使用实际命中区域测量页签，确保选中态没有偷偷覆盖内边距。
            for selected in (0, 1):
                app.notebook.select(selected)
                window.update()
                bounds = [[], []]
                for x in range(240):
                    for y in range(50):
                        try:
                            index = app.notebook.index(f'@{x},{y}')
                        except tk.TclError:
                            continue
                        bounds[index].append((x, y))
                sizes = [(max(x for x, _ in points) - min(x for x, _ in points),
                          max(y for _, y in points) - min(y for _, y in points)) for points in bounds]
                self.assertEqual(sizes[0], sizes[1])
        finally:
            app._shutdown.set()
            window.after_cancel(app._after_id)
            window.destroy()
            del app, window
            gc.collect()

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
                # 最小窗口仍可阅读日志，前端操作完整可见；专注模式扩大阅读宽度。
                item = app.navigation.items[spec.key]
                for button in item['buttons'].values():
                    self.assertLessEqual(button.winfo_rootx() + button.winfo_width(),
                                         app.navigation.canvas.winfo_rootx() + app.navigation.canvas.winfo_width())
                log_height = app.logs.winfo_height()
                log_width = app.logs.winfo_width()
                self.assertGreater(log_height, 75)
                app.log_panel.expand_button.invoke()
                window.update()
                self.assertFalse(app.sidebar.winfo_ismapped())
                self.assertGreater(app.logs.winfo_width(), log_width + 50)
                app.log_panel.expand_button.invoke()
                window.update()
                self.assertTrue(app.sidebar.winfo_ismapped())
                app.info_button.invoke()
                window.update()
                self.assertTrue(app.metadata_label.winfo_ismapped())
                self.assertIn(str(folder), app.metadata.get())
                self.assertIn(spec.health_url, app.metadata.get())
                app.info_button.invoke()
                window.update()
                self.assertFalse(app.metadata_label.winfo_ismapped())
                app.act(START)
                pump_until(lambda: runner.view().status == RUNNING)
                # 浏览器是外部边界；实际 Tk 点击事件必须传递所选前端的真实端口。
                with patch('app.webbrowser.open') as browser:
                    app.navigation.items[spec.key]['port'].event_generate('<Button-1>')
                    window.update()
                    browser.assert_called_once_with(f'http://127.0.0.1:{port}/')
                source.write_text('after', encoding='utf-8')
                pump_until(lambda: '代码已变更' in app.navigation.items[spec.key]['changes'].cget('text'))
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
