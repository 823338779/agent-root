"""从本地 TOML 文件加载桥接服务配置。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib
from typing import Any

from .constants import CONFIG_APPROVAL_DENY_ALL, CONFIG_SANDBOX_FULL_ACCESS


@dataclass(frozen=True, slots=True)
class FeishuConfig:
    """飞书应用身份与允许使用机器人的用户集合。"""

    app_id: str
    app_secret: str
    allowed_open_ids: frozenset[str]


@dataclass(frozen=True, slots=True)
class CodexSettings:
    """Codex 的固定工作目录、模型和系统权限策略。"""

    workspace: Path
    model: str | None
    sandbox: str
    approval_mode: str


@dataclass(frozen=True, slots=True)
class BridgeSettings:
    """消息并发、输入长度、输出分片和去重缓存限制。"""

    max_workers: int
    max_prompt_length: int
    max_reply_length: int
    processed_message_cache_size: int


@dataclass(frozen=True, slots=True)
class AppConfig:
    """桥接服务的完整运行配置。"""

    feishu: FeishuConfig
    codex: CodexSettings
    bridge: BridgeSettings


# TOML 字段读取集中校验类型和空值，避免连接建立后才暴露配置错误。
def _required_string(section: dict[str, Any], key: str) -> str:
    value = section.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"配置项 {key} 必须是非空字符串")
    return value.strip()


def _positive_integer(section: dict[str, Any], key: str) -> int:
    value = section.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"配置项 {key} 必须是正整数")
    return value


# 完整配置加载时强制验证用户要求的 full-access 与无审批模式。
def load_config(config_path: Path) -> AppConfig:
    with config_path.open("rb") as config_file:
        document = tomllib.load(config_file)

    feishu_section = document.get("feishu", {})
    codex_section = document.get("codex", {})
    bridge_section = document.get("bridge", {})
    allowed_open_ids = feishu_section.get("allowed_open_ids")
    if not isinstance(allowed_open_ids, list) or not all(
        isinstance(item, str) and item.strip() for item in allowed_open_ids
    ):
        raise ValueError("配置项 allowed_open_ids 必须是非空字符串数组")

    sandbox = _required_string(codex_section, "sandbox")
    approval_mode = _required_string(codex_section, "approval_mode")
    if sandbox != CONFIG_SANDBOX_FULL_ACCESS:
        raise ValueError(f"sandbox 必须配置为 {CONFIG_SANDBOX_FULL_ACCESS}")
    if approval_mode != CONFIG_APPROVAL_DENY_ALL:
        raise ValueError(f"approval_mode 必须配置为 {CONFIG_APPROVAL_DENY_ALL}")

    workspace = Path(_required_string(codex_section, "workspace")).resolve()
    if not workspace.is_dir():
        raise ValueError(f"Codex 工作目录不存在：{workspace}")
    model_value = codex_section.get("model", "")
    if not isinstance(model_value, str):
        raise ValueError("配置项 model 必须是字符串")

    return AppConfig(
        feishu=FeishuConfig(
            app_id=_required_string(feishu_section, "app_id"),
            app_secret=_required_string(feishu_section, "app_secret"),
            allowed_open_ids=frozenset(item.strip() for item in allowed_open_ids),
        ),
        codex=CodexSettings(
            workspace=workspace,
            model=model_value.strip() or None,
            sandbox=sandbox,
            approval_mode=approval_mode,
        ),
        bridge=BridgeSettings(
            max_workers=_positive_integer(bridge_section, "max_workers"),
            max_prompt_length=_positive_integer(bridge_section, "max_prompt_length"),
            max_reply_length=_positive_integer(bridge_section, "max_reply_length"),
            processed_message_cache_size=_positive_integer(
                bridge_section, "processed_message_cache_size"
            ),
        ),
    )

