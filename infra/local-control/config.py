"""五个服务的启动定义与 JetBrains 运行配置适配。"""

from dataclasses import dataclass, field, replace
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import xml.etree.ElementTree as ET

# 协议、IDE 宏及文件名集中定义；服务配置使用具名默认值。
UTF8 = 'utf-8'
PROJECT_MACRO = '$PROJECT_DIR$'
MACRO_PATTERN = r'\$([^$]+)\$'
OPTION_SELECTOR = './/configuration/option'
ENV_SELECTOR = './/configuration/envs/env'
NAME_ATTRIBUTE, VALUE_ATTRIBUTE = 'name', 'value'
MAVEN_NAMESPACE = '{http://maven.apache.org/POM/4.0.0}'
VERSION_ELEMENT = MAVEN_NAMESPACE + 'version'
PATH_KEY, PYTHONPATH_KEY = 'PATH', 'PYTHONPATH'
OVERRIDES_PATH = 'tmp/local-control/settings.json'
STATUS_URL = 'http://127.0.0.1:{port}{path}'
WINDOWS = 'nt'
PORT_ARGUMENT = '--port'
SERVER_PORT_ARGUMENT = '--server.port='
SERVER_PORT_VM_ARGUMENT = '-Dserver.port='


def split_arguments(value: str) -> tuple[str, ...]:
    # Windows 使用系统参数解析规则，保留反斜杠以及双引号包围的空格。
    if not value:
        return ()
    if os.name != WINDOWS:
        return tuple(shlex.split(value))
    import ctypes
    from ctypes import wintypes
    shell = ctypes.WinDLL('shell32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    shell.CommandLineToArgvW.argtypes = (wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int))
    shell.CommandLineToArgvW.restype = ctypes.POINTER(wintypes.LPWSTR)
    kernel.LocalFree.argtypes = (ctypes.c_void_p,)
    count = ctypes.c_int()
    arguments = shell.CommandLineToArgvW('program ' + value, ctypes.byref(count))
    if not arguments:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return tuple(arguments[index] for index in range(1, count.value))
    finally:
        kernel.LocalFree(arguments)


@dataclass(frozen=True)
class IdeConfig:
    # IDE 中的工作目录，路径宏已解析。
    cwd: Path
    # 仅包含运行配置显式声明的环境变量。
    env: dict[str, str] = field(default_factory=dict)
    # 传给 JVM 的参数。
    vm_args: tuple[str, ...] = ()
    # 传给应用入口的参数。
    args: tuple[str, ...] = ()


@dataclass(frozen=True)
class ServiceSpec:
    # 稳定标识，用于日志文件及本地覆盖配置。
    key: str
    # 窗口显示的名称。
    name: str
    # 子进程的工作目录。
    cwd: Path
    # 正式服务命令，以参数数组保存，避免 shell 拼接。
    command: tuple[str, ...]
    # 本地服务端口，同时用于占用检测。
    port: int
    # 健康检查路径，HTTP 失败不能标记为健康。
    health_path: str = '/'
    # 浏览器打开的路径。
    open_path: str = '/'
    # 可选构建命令；失败时不会执行正式服务命令。
    build: tuple[str, ...] = ()
    # 子进程环境变量增量，继承启动客户端的环境。
    env: dict[str, str] = field(default_factory=dict)
    # 源码与配置监视范围。
    watch_paths: tuple[Path, ...] = ()
    # 用于显示变更文件的工作区根目录。
    root: Path = Path('.')
    # 前端普通代码变化使用 Vite HMR 提示。
    frontend: bool = False
    # 启动等待健康检查成功的秒数；超时显示不健康。
    startup_timeout: float = 120.0

    @property
    def health_url(self) -> str:
        return STATUS_URL.format(port=self.port, path=self.health_path)

    @property
    def open_url(self) -> str:
        return STATUS_URL.format(port=self.port, path=self.open_path)


def read_ide(path: Path, root: Path) -> IdeConfig:
    # 不存在的可选运行配置使用工作区目录和继承环境。
    if not path.exists():
        return IdeConfig(root)
    document = ET.parse(path)
    options = {node.get(NAME_ATTRIBUTE): node.get(VALUE_ATTRIBUTE, '')
               for node in document.findall(OPTION_SELECTOR)}

    def expand(value: str) -> str:
        value = value.replace(PROJECT_MACRO, root.as_posix())
        parent = {key.upper(): item for key, item in os.environ.items()}
        return re.sub(MACRO_PATTERN, lambda match: parent.get(match[1].upper(), match[0]), value)

    env = {node.get(NAME_ATTRIBUTE): expand(node.get(VALUE_ATTRIBUTE, ''))
           for node in document.findall(ENV_SELECTOR)}
    return IdeConfig(Path(expand(options.get('WORKING_DIRECTORY') or root.as_posix())), env,
                     tuple(expand(item) for item in split_arguments(options.get('VM_PARAMETERS', ''))),
                     tuple(expand(item) for item in split_arguments(options.get('PROGRAM_PARAMETERS', ''))))


def load_services(root: Path) -> list[ServiceSpec]:
    # 使用已安装工具；找不到时保留名称，让启动错误明确指出缺失项。
    maven = shutil.which('mvn.cmd') or shutil.which('mvn') or 'mvn.cmd'
    java = shutil.which('java') or 'java'
    npm = shutil.which('npm.cmd') or shutil.which('npm') or 'npm.cmd'
    services = []
    for key, name, project, module, port, run_file in (
        ('metric', 'Metric Platform', 'metric-platform', 'metric-app', 8090,
         '.run/MetricPlatformApplication.run.xml'),
        ('agent', 'Agent V2', 'data-agent-v2', 'agent-server', 8080,
         '.run/AgentV2Application.run.xml'),
    ):
        folder = root / project
        ide = read_ide(root / run_file, root)
        port = int(ide.env.get('SERVER_PORT', os.environ.get('SERVER_PORT', port)))
        for argument in (*ide.vm_args, *ide.args):
            if argument.startswith((SERVER_PORT_ARGUMENT, SERVER_PORT_VM_ARGUMENT)):
                port = int(argument.split('=', 1)[1])
        version = ET.parse(folder / 'pom.xml').findtext(VERSION_ELEMENT)
        jar = folder / 'backend' / module / 'target' / f'{module}-{version}.jar'
        # 通过各自 reactor 编译依赖；jar 名称随产品 POM 版本解析。
        services.append(ServiceSpec(
            key=key, name=name, cwd=ide.cwd, port=port,
            command=(java, *ide.vm_args, '-jar', str(jar), *ide.args),
            build=(maven, '-f', str(folder / 'pom.xml'), '-pl', f'backend/{module}',
                   '-am', '-Dmaven.test.skip=true', 'package'),
            env=ide.env, health_path='/actuator/health', root=root,
            watch_paths=(folder / 'backend', folder / 'pom.xml', root / run_file),
        ))

    # Python 使用 PyCharm 指定的项目虚拟环境及相同配置文件。
    dbt = root / 'dbt-metricflow-service'
    run_file = root / '.run/dbt-metricflow-service.run.xml'
    ide = read_ide(run_file, root)
    scripts = dbt / '.venv' / 'Scripts'
    env = dict(ide.env)
    env[PATH_KEY] = str(scripts) + os.pathsep + env.pop('Path', os.environ.get(PATH_KEY, ''))
    env[PYTHONPATH_KEY] = str(dbt / 'src') + os.pathsep + os.environ.get(PYTHONPATH_KEY, '')
    dbt_port = int(env.get('SERVICE_PORT', os.environ.get('SERVICE_PORT', 8000)))
    config_file = Path(env.get('SERVICE_CONFIG_FILE', str(dbt / 'config/service.yaml')))
    if config_file.exists() and 'SERVICE_PORT' not in env and 'SERVICE_PORT' not in os.environ:
        match = re.search(r'^SERVICE_PORT:\s*[\"\x27]?(\d+)',
                          config_file.read_text(encoding=UTF8), re.MULTILINE)
        if match:
            dbt_port = int(match[1])
    services.insert(0, ServiceSpec(
        key='dbt', name='dbt-service', cwd=ide.cwd if run_file.exists() else dbt,
        command=(str(scripts / 'python.exe'), '-m', 'dbt_metricflow_service.main'),
        port=dbt_port, health_path='/health/ready', open_path='/docs', env=env, root=root,
        watch_paths=(dbt / 'src', dbt / 'config', dbt / 'pyproject.toml', dbt / 'uv.lock',
                     dbt / 'vendor', run_file, dbt / '.run'),
    ))
    for key, name, project, port in (
        ('agent-web', 'Agent V2 · 前端', 'data-agent-v2', 5173),
        ('metric-web', 'Metric Platform · 前端', 'metric-platform', 5174),
    ):
        folder = root / project / 'frontend'
        services.append(ServiceSpec(
            key=key, name=name, cwd=folder, port=port, frontend=True, root=root,
            command=(npm, 'run', 'dev', '--', '--host', '127.0.0.1',
                     '--port', str(port), '--strictPort'),
            watch_paths=(folder,),
        ))

    # 本地覆盖仅存于 gitignored tmp；配置值不输出到界面或仓库。
    settings = root / OVERRIDES_PATH
    overrides = json.loads(settings.read_text(encoding=UTF8)) if settings.exists() else {}
    for index, service in enumerate(services):
        values = overrides.get(service.key, {})
        allowed = {'port', 'health_path', 'open_path', 'cwd', 'command', 'build',
                   'env', 'startup_timeout'}
        unknown = values.keys() - allowed
        if unknown:
            raise ValueError(f'{service.name} 包含未知配置项：{sorted(unknown)}')
        values = dict(values)
        if 'cwd' in values:
            values['cwd'] = root / values['cwd']
        for name in ('command', 'build'):
            if name in values:
                values[name] = tuple(values[name])
        if 'env' in values:
            values['env'] = service.env | values['env']
        updated = replace(service, **values)
        if 'port' in values:
            if updated.frontend and 'command' not in values:
                command = list(updated.command)
                command[command.index(PORT_ARGUMENT) + 1] = str(updated.port)
                updated = replace(updated, command=tuple(command))
            elif updated.key == 'dbt':
                updated = replace(updated, env=updated.env | {'SERVICE_PORT': str(updated.port)})
            elif 'command' not in values:
                updated = replace(updated, command=(*updated.command, SERVER_PORT_ARGUMENT + str(updated.port)))
        services[index] = replace(updated, watch_paths=(*updated.watch_paths, settings))
    return services
