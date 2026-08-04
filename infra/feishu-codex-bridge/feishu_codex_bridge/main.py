"""飞书 Codex Bridge 的命令行启动入口。"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from .bridge import Bridge
from .codex_executor import CodexExecutor
from .config import load_config
from .constants import CONFIG_FILE_NAME, LOG_CONFIG_LOADED, LOG_CONNECTION_START, LOG_FATAL
from .feishu import FeishuMessageSender, create_websocket_client

LOGGER = logging.getLogger(__name__)
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s - %(message)s"


# 配置文件路径可覆盖，默认读取模块根目录的 config.local.toml。
def parse_arguments() -> argparse.Namespace:
    default_config = Path(__file__).resolve().parent.parent / CONFIG_FILE_NAME
    parser = argparse.ArgumentParser(description="通过飞书机器人操作本地 Codex")
    parser.add_argument("--config", type=Path, default=default_config)
    return parser.parse_args()


def run() -> None:
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
    arguments = parse_arguments()
    config = load_config(arguments.config.resolve())
    LOGGER.info(LOG_CONFIG_LOADED, config.codex.workspace)

    executor = CodexExecutor(config.codex)
    sender = FeishuMessageSender(config.feishu)
    bridge = Bridge(config, executor, sender)
    websocket_client = create_websocket_client(config.feishu, bridge)
    try:
        LOGGER.info(LOG_CONNECTION_START)
        websocket_client.start()
    finally:
        bridge.close()


if __name__ == "__main__":
    try:
        run()
    except Exception:
        LOGGER.exception(LOG_FATAL)
        raise

