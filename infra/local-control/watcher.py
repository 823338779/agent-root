"""扫描源码内容；不依赖 Git 状态，也不读取构建产物。"""

import hashlib
import os
from pathlib import Path

# 生成目录在遍历入口剪枝，避免扫描大型依赖目录。
IGNORED_DIRS = frozenset({'.git', '.idea', '.venv', 'venv', 'node_modules',
                          'target', 'dist', 'build', '__pycache__', '.pytest_cache',
                          '.ruff_cache', '.mypy_cache', '.cache', '.vite', 'logs',
                          'tmp', 'coverage', '.next', '.superpowers'})
SOURCE_SUFFIXES = frozenset({'.py', '.java', '.kt', '.xml', '.yml', '.yaml',
                             '.properties', '.json', '.toml', '.lock', '.sql',
                             '.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs', '.css',
                             '.scss', '.html', '.svg', '.png', '.jpg', '.woff2',
                             '.txt', '.ps1', '.cmd'})
ENV_PREFIX = '.env'
VITE_PREFIX = 'vite.config.'
LOCAL_CONFIG_SUFFIX = 'tmp/local-control/settings.json'
RESTART_FILES = frozenset({'package.json', 'package-lock.json', 'yarn.lock',
                           'pnpm-lock.yaml', 'tsconfig.json'})
ADDED, MODIFIED, DELETED = '新增', '修改', '删除'
BINARY_MODE = 'rb'


class SourceWatcher:
    """监视指定源目录，基线由调用方在成功启动后提交。"""

    def __init__(self, root: Path, paths: tuple[Path, ...]):
        # root 用于稳定的相对路径；paths 只包含该服务实际消费的目录。
        self.root = root
        self.paths = paths

    def capture(self) -> dict[str, str]:
        # 每次读取内容摘要，可发现同大小、同时间戳的修改及保存后回滚。
        result = {}
        for source in self.paths:
            files = []
            if source.is_file():
                files.append(source)
            elif source.is_dir():
                for directory, children, names in os.walk(source, followlinks=False):
                    children[:] = [name for name in children
                                   if name not in IGNORED_DIRS
                                   and not (Path(directory) / name).is_symlink()]
                    files.extend(Path(directory) / name for name in names)
            for path in files:
                if path.is_symlink():
                    continue
                if path.suffix not in SOURCE_SUFFIXES and not path.name.startswith(ENV_PREFIX):
                    continue
                try:
                    with path.open(BINARY_MODE) as stream:
                        digest = hashlib.file_digest(stream, hashlib.sha256).hexdigest()
                    result[path.relative_to(self.root).as_posix()] = digest
                except FileNotFoundError:
                    # 编辑器原子替换或删除文件时，下次扫描再读取。
                    continue
        return result

    def changes(self, baseline: dict[str, str]) -> dict[str, str]:
        return compare(baseline, self.capture())


def compare(baseline: dict[str, str], current: dict[str, str]) -> dict[str, str]:
    # 排序使同一批变更在 UI 中保持稳定，内容恢复后自然取消标记。
    return {name: ADDED if name not in baseline else DELETED if name not in current else MODIFIED
            for name in sorted(baseline.keys() | current.keys())
            if baseline.get(name) != current.get(name)}


def needs_restart(changes: dict[str, str], *, frontend: bool) -> bool:
    # Vite 普通源码走 HMR；配置与依赖变更需要开发者主动重启。
    if not frontend:
        return bool(changes)
    return any(Path(name).name in RESTART_FILES
               or Path(name).name.startswith((ENV_PREFIX, VITE_PREFIX))
               or name.endswith((RUN_CONFIG_SUFFIX, LOCAL_CONFIG_SUFFIX)) for name in changes)


RUN_CONFIG_SUFFIX = '.run.xml'
