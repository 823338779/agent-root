"""日志阅读交互使用真实 Tk 文本区验证，不启动业务服务。"""

import gc
import tkinter as tk
import unittest

from log_panel import LogPanel


class LogPanelTest(unittest.TestCase):
    def setUp(self):
        self.window = tk.Tk()
        self.window.geometry('960x360')
        self.panel = LogPanel(self.window)
        self.panel.pack(fill='both', expand=True)
        self.window.update()

    def tearDown(self):
        # 在 Tk 主线程释放预览窗口的循环引用，避免后续服务线程触发 Tk 析构。
        self.window.destroy()
        self.panel = self.window = None
        gc.collect()

    def test_levels_ansi_and_copy_keep_readable_content(self):
        self.panel.update_lines((
            '14:58:16  \x1b[32m[INFO] 服务启动成功\x1b[0m',
            '14:58:17  [WARN] 配置未生效',
            '14:58:18  ERROR 请求失败',
            '    at example.Service.run(Service.java:42)',
        ))
        text = self.panel.text
        self.assertIn('服务启动成功', text.get('1.0', 'end'))
        self.assertNotIn('\x1b', text.get('1.0', 'end'))
        self.assertIn('timestamp', text.tag_names('1.0'))
        self.assertIn('warning', text.tag_names('2.20'))
        self.assertIn('error', text.tag_names('3.20'))
        self.assertIn('1 警告', self.panel.summary.get())
        self.assertIn('1 错误', self.panel.summary.get())
        text.tag_add('sel', '2.0', '2.end')
        self.panel.copy_button.invoke()
        self.assertEqual(self.window.clipboard_get(), '14:58:17  [WARN] 配置未生效')
        text.tag_remove('sel', '1.0', 'end')
        self.panel.copy_button.invoke()
        self.assertEqual(self.window.clipboard_get(), text.get('1.0', 'end-1c').rstrip('\n'))

    def test_new_logs_preserve_selection_and_reading_position(self):
        lines = tuple(f'14:58:16  [INFO] 第 {index} 条日志' for index in range(100))
        self.panel.update_lines(lines)
        self.window.update()
        self.panel.text.yview_moveto(0.25)
        self.panel.text.tag_add('sel', '30.0', '30.end')
        self.window.update()
        position = self.panel.text.index('@0,0')
        self.panel.update_lines((*lines, '14:58:17  [INFO] 新日志'))
        self.window.update()
        self.assertEqual(self.panel.text.index('@0,0'), position)
        self.assertEqual(self.panel.text.get('sel.first', 'sel.last'), lines[29])
        self.panel.latest_button.invoke()
        self.window.update()
        self.assertAlmostEqual(self.panel.text.yview()[1], 1.0, places=2)

    def test_rolling_buffer_keeps_surviving_selection_and_content(self):
        lines = tuple(f'14:58:16  [INFO] 第 {index} 条日志' for index in range(100))
        self.panel.update_lines(lines)
        self.window.update()
        self.panel.text.yview_moveto(0.5)
        self.panel.text.tag_add('sel', '55.0', '55.end')
        replacement = (*lines[20:], '14:58:17  [ERROR] 最新错误')
        self.panel.update_lines(replacement)
        self.window.update()
        self.assertEqual(self.panel.text.get('1.0', 'end-1c'), '\n'.join(replacement) + '\n')
        self.assertEqual(self.panel.text.get('sel.first', 'sel.last'), lines[54])
        self.assertIn('81 行', self.panel.summary.get())
        self.assertIn('error', self.panel.text.tag_names('81.20'))

    def test_multiline_entry_eviction_leaves_no_stale_text(self):
        self.panel.update_lines(('first\nsecond', 'third', 'fourth'))
        self.panel.update_lines(('third', 'fourth', 'fifth'))
        self.assertEqual(self.panel.text.get('1.0', 'end-1c'), 'third\nfourth\nfifth\n')
        self.panel.copy_button.invoke()
        self.assertEqual(self.window.clipboard_get(), 'third\nfourth\nfifth')

    def test_wrap_and_switch_service_do_not_keep_old_content(self):
        self.panel.update_lines(('14:58:16  [ERROR] 旧服务错误',))
        self.panel.wrap_button.invoke()
        self.assertEqual(self.panel.text.cget('wrap'), 'word')
        self.panel.wrap_button.invoke()
        self.window.update()
        self.assertEqual(self.panel.text.cget('wrap'), 'none')
        self.assertTrue(self.panel.horizontal.winfo_ismapped())
        self.panel.update_lines((), notice='请在原 IDE 查看日志', reset=True)
        self.assertNotIn('旧服务', self.panel.text.get('1.0', 'end'))
        self.assertEqual(self.panel.notice.get(), '请在原 IDE 查看日志')
        self.assertEqual(str(self.panel.copy_button.cget('state')), 'disabled')
