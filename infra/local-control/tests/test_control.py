"""以临时文件和真实本地子进程验证中控行为，不操作业务数据。"""

import os
import json
from pathlib import Path
import tempfile
import unittest

from config import load_services, read_ide
from watcher import SourceWatcher, needs_restart


class WatcherTest(unittest.TestCase):
    """捕捉漏报增删改、生成物误报及错误清除提醒。"""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'src' / 'main.py'
        self.source.parent.mkdir()
        self.source.write_text('old', encoding='utf-8')
        self.watcher = SourceWatcher(self.root, (self.root,))

    def test_detects_added_modified_deleted_and_reverted_files(self):
        baseline = self.watcher.capture()
        self.source.write_text('new', encoding='utf-8')
        extra = self.root / 'extra.py'
        extra.write_text('added', encoding='utf-8')
        self.assertEqual(self.watcher.changes(baseline),
                         {'extra.py': '新增', 'src/main.py': '修改'})
        self.source.unlink()
        self.assertEqual(self.watcher.changes(baseline)['src/main.py'], '删除')
        extra.unlink()
        self.source.write_text('old', encoding='utf-8')
        self.assertEqual(self.watcher.changes(baseline), {})

    def test_ignores_generated_files_but_detects_dotenv_and_untracked_source(self):
        baseline = self.watcher.capture()
        for directory in ('target', '.git', 'node_modules', '.venv', '__pycache__'):
            generated = self.root / directory / 'generated.py'
            generated.parent.mkdir()
            generated.write_text('ignored', encoding='utf-8')
        (self.root / '.env.local').write_text('LOCAL=1', encoding='utf-8')
        self.assertEqual(self.watcher.changes(baseline), {'.env.local': '新增'})

    def test_touching_source_without_content_change_does_not_prompt(self):
        baseline = self.watcher.capture()
        os.utime(self.source, None)
        self.assertEqual(self.watcher.changes(baseline), {})

    def test_same_size_and_timestamp_edit_is_still_detected(self):
        baseline = self.watcher.capture()
        timestamp = self.source.stat()
        self.source.write_text('new', encoding='utf-8')
        os.utime(self.source, ns=(timestamp.st_atime_ns, timestamp.st_mtime_ns))
        self.assertEqual(self.watcher.changes(baseline), {'src/main.py': '修改'})

    def test_frontend_config_needs_restart_while_components_use_hmr(self):
        self.assertFalse(needs_restart({'src/App.tsx': '修改'}, frontend=True))
        for path in ('vite.config.ts', 'package.json', '.env.local', 'package-lock.json',
                     'tmp/local-control/settings.json'):
            self.assertTrue(needs_restart({path: '修改'}, frontend=True), path)
        self.assertTrue(needs_restart({'src/main.py': '修改'}, frontend=False))
        self.assertFalse(needs_restart({}, frontend=False))


class ConfigurationTest(unittest.TestCase):
    """验证实际启动参数边界而不是配置文件文本。"""

    def test_ide_macros_resolve_against_workspace_and_parent_environment(self):
        with tempfile.TemporaryDirectory(prefix='中控 space ') as directory:
            root = Path(directory)
            config = root / 'run.xml'
            config.write_text('''<component><configuration>
              <option name="WORKING_DIRECTORY" value="$PROJECT_DIR$/service"/>
              <option name="VM_PARAMETERS" value="-Xmx512m"/>
              <option name="PROGRAM_PARAMETERS" value="--server.port=9000"/>
              <envs><env name="Path" value="$PROJECT_DIR$/venv;$Path$"/>
              <env name="CONFIG" value="$PROJECT_DIR$/config.yml"/></envs>
            </configuration></component>''', encoding='utf-8')
            ide = read_ide(config, root)
            self.assertEqual(ide.cwd, root / 'service')
            self.assertEqual(ide.vm_args, ('-Xmx512m',))
            self.assertEqual(ide.args, ('--server.port=9000',))
            self.assertEqual(ide.env['CONFIG'], str(root / 'config.yml').replace('\\', '/'))
            self.assertNotIn('$Path$', ide.env['Path'])

    @unittest.skipUnless(os.name == 'nt', 'Windows IDE 参数')
    def test_windows_ide_arguments_preserve_backslashes_and_expand_macros(self):
        with tempfile.TemporaryDirectory(prefix='space ') as directory:
            root = Path(directory)
            config = root / 'run.xml'
            config.write_text(r'''<component><configuration>
              <option name="VM_PARAMETERS" value="-Dconfig=C:\work\config.yml"/>
              <option name="PROGRAM_PARAMETERS" value="--config=&quot;$PROJECT_DIR$/config file.yml&quot;"/>
            </configuration></component>''')
            ide = read_ide(config, root)
            self.assertEqual(ide.vm_args, (r'-Dconfig=C:\work\config.yml',))
            self.assertEqual(ide.args, ('--config=' + root.as_posix() + '/config file.yml',))

    def test_workspace_definitions_use_distinct_ports_and_existing_projects(self):
        root = Path(__file__).resolve().parents[3]
        services = load_services(root)
        self.assertEqual(len(services), 5)
        self.assertEqual(len({service.port for service in services}), 5)
        for service in services:
            self.assertTrue(service.cwd.is_dir(), service.name)
            self.assertTrue(service.watch_paths, service.name)

    def test_port_override_updates_launch_command_and_probe_together(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for project in ('metric-platform', 'data-agent-v2'):
                path = root / project / 'pom.xml'
                path.parent.mkdir()
                path.write_text('<project xmlns="http://maven.apache.org/POM/4.0.0"><version>1</version></project>')
            settings = root / 'tmp/local-control/settings.json'
            settings.parent.mkdir(parents=True)
            settings.write_text(json.dumps({'agent-web': {'port': 5200}, 'agent': {'port': 8200},
                                            'dbt': {'port': 8300}}))
            services = {spec.key: spec for spec in load_services(root)}
            self.assertIn('5200', services['agent-web'].command)
            self.assertIn('--server.port=8200', services['agent'].command)
            self.assertEqual(services['dbt'].env['SERVICE_PORT'], '8300')
            self.assertIn(':5200/', services['agent-web'].health_url)


if __name__ == '__main__':
    unittest.main()
