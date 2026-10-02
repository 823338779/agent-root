"""从 pythonw 入口验证真实 Windows 进程链不显示控制台，且保留输出。"""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

# 探针同时检查服务本身与它再次启动的子进程，不能只验证中控的创建标志。
PROBE = '''import ctypes, json, pathlib, subprocess, sys
kernel = ctypes.WinDLL('kernel32')
user = ctypes.WinDLL('user32')
kernel.GetConsoleWindow.restype = ctypes.c_void_p
user.IsWindowVisible.argtypes = (ctypes.c_void_p,)
handle = kernel.GetConsoleWindow()
result = {'visible': bool(handle and user.IsWindowVisible(handle))}
if len(sys.argv) == 1:
    child = subprocess.run([sys.executable, __file__, 'child'], capture_output=True, text=True, check=True)
    result['child'] = json.loads(child.stdout)
    pathlib.Path('console.json').write_text(json.dumps(result))
    print('stdout-ready', flush=True)
    print('stderr-ready', file=sys.stderr, flush=True)
else:
    print(json.dumps(result), flush=True)
'''

# 独立 pythonw 进程模拟 PowerShell 脚本打开桌面客户端的真实入口。
LAUNCHER = '''import json, pathlib, sys
sys.path.insert(0, sys.argv[1])
from config import ServiceSpec
from runtime import spawn, terminate_tree
folder = pathlib.Path.cwd()
spec = ServiceSpec(key='console', name='console', cwd=folder, command=tuple(sys.argv[2:]), port=1)
process = spawn(spec.command, spec)
try:
    output, _ = process.communicate(timeout=20)
    folder.joinpath('output.json').write_text(json.dumps({'code': process.returncode, 'output': output.decode('utf-8')}))
finally:
    terminate_tree(process)
'''


@unittest.skipUnless(sys.platform == 'win32', 'Windows 控制台可见性')
class HiddenConsoleTest(unittest.TestCase):
    def assert_hidden_chain(self, batch):
        with tempfile.TemporaryDirectory(prefix='local-control console ') as directory:
            folder = Path(directory)
            probe = folder / 'probe.py'
            probe.write_text(PROBE, encoding='utf-8')
            launcher = folder / 'launcher.pyw'
            launcher.write_text(LAUNCHER, encoding='utf-8')
            command = (sys.executable, str(probe))
            if batch:
                script = folder / 'launch probe.cmd'
                script.write_text('@echo off\n"' + sys.executable + '" "%~dp0probe.py"\n', encoding='utf-8')
                command = (str(script),)
            app_dir = Path(__file__).resolve().parents[1]
            subprocess.run((str(Path(sys.executable).with_name('pythonw.exe')),
                            str(launcher), str(app_dir), *command), cwd=folder,
                           check=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
            result = json.loads((folder / 'console.json').read_text())
            output = json.loads((folder / 'output.json').read_text())
            self.assertFalse(result['visible'], '实际服务显示了控制台')
            self.assertFalse(result['child']['visible'], '服务子进程显示了控制台')
            self.assertEqual(output['code'], 0)
            self.assertIn('stdout-ready', output['output'])
            self.assertIn('stderr-ready', output['output'])

    def test_program_and_descendant_console_stay_hidden_from_pythonw(self):
        self.assert_hidden_chain(batch=False)

    def test_batch_and_descendant_console_stay_hidden_from_pythonw(self):
        self.assert_hidden_chain(batch=True)
