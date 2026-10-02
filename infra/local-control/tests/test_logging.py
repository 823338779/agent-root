"""真实子进程的中文输出必须原样进入界面快照与 UTF-8 日志文件。"""

import locale
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

from config import ServiceSpec
from runtime import ServiceRunner

# 同一构建可能包含 UTF-8 工具输出与系统本地编码的编译器诊断。
UTF8_MESSAGE = '前端已启动：中文日志 ✅'
NATIVE_MESSAGE = '中文编译警告：启用了注释处理'
ERROR_MESSAGE = '中文错误：请检查配置'
JAVA_SOURCE = '''public class EncodingProbe {
    public static void main(String[] args) {
        System.out.println("中文编译警告：启用了注释处理");
        System.err.println("中文错误：请检查配置");
    }
}
'''


class LogEncodingTest(unittest.TestCase):
    def capture(self, root, command, messages):
        # 使用生产启动链路与日志线程；只创建短命临时进程。
        spec = ServiceSpec(key='encoding-test', name='日志测试', cwd=root,
                           root=root, port=0, command=command)
        runner = ServiceRunner(spec, root / 'logs')
        try:
            self.assertTrue(runner.start())
            self.assertTrue(runner.wait_idle(10))
            runner._process.wait(timeout=20)
            runner._finish_reader()
            displayed = '\n'.join(runner.view().logs)
            saved = (root / 'logs/encoding-test.log').read_text(encoding='utf-8')
            for message in messages:
                self.assertIn(message, displayed)
                self.assertIn(message, saved)
        finally:
            runner.stop()
            runner.wait_idle(10)
            runner.close_logs()

    def test_mixed_utf8_and_native_stdout_stderr_are_readable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            native = locale.getencoding()
            script = root / 'emit.py'
            # 写原始字节，避免测试解释器的默认编码掩盖问题。
            script.write_text('import os\n' + '\n'.join(
                f'os.write({fd}, {data!r})' for fd, data in (
                    (1, (UTF8_MESSAGE + '\n').encode('utf-8')),
                    (1, (NATIVE_MESSAGE + '\n').encode(native)),
                    (2, (ERROR_MESSAGE + '\n').encode(native)),
                    (1, (UTF8_MESSAGE + '\n').encode('utf-8')),
                )), encoding='utf-8')
            self.capture(root, (sys.executable, str(script)),
                         (UTF8_MESSAGE, NATIVE_MESSAGE, ERROR_MESSAGE))

    @unittest.skipUnless(shutil.which('java'), '需要工作区支持的 JDK 21')
    def test_java_chinese_stdout_and_stderr_are_readable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'EncodingProbe.java'
            source.write_text(JAVA_SOURCE, encoding='utf-8')
            self.capture(root, (shutil.which('java'), str(source)),
                         (NATIVE_MESSAGE, ERROR_MESSAGE))

    @unittest.skipUnless(os.name == 'nt' and shutil.which('java'), '需要 Windows 和 JDK 21')
    def test_java_chinese_through_batch_wrapper_is_readable(self):
        # Maven 同样经 .cmd 与 PowerShell 启动，中文必须穿过完整包装链。
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'EncodingProbe.java'
            source.write_text(JAVA_SOURCE, encoding='utf-8')
            batch = root / 'compile.cmd'
            batch.write_text(f'@echo off\n"{shutil.which("java")}" "%~dp0EncodingProbe.java"\n',
                             encoding=locale.getencoding())
            self.capture(root, (str(batch),), (NATIVE_MESSAGE, ERROR_MESSAGE))
