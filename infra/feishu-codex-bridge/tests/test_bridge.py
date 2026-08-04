from pathlib import Path
import unittest

from feishu_codex_bridge.bridge import Bridge
from feishu_codex_bridge.config import AppConfig, BridgeSettings, CodexSettings, FeishuConfig
from feishu_codex_bridge.constants import REPLY_ACCEPTED, REPLY_UNAUTHORIZED_TEMPLATE
from feishu_codex_bridge.message import IncomingMessage


class FakeExecutor:
    def __init__(self) -> None:
        self.prompts: list[tuple[str, str]] = []

    def execute(self, session_id: str, prompt: str) -> str:
        self.prompts.append((session_id, prompt))
        return "检查完成"

    def interrupt(self, session_id: str) -> bool:
        return False

    def reset(self, session_id: str) -> None:
        return None

    def close(self) -> None:
        return None


class FakeSender:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def send_text(self, chat_id: str, text: str) -> None:
        self.messages.append((chat_id, text))


def create_config() -> AppConfig:
    return AppConfig(
        feishu=FeishuConfig("test-app", "test-secret", frozenset({"allowed-user"})),
        codex=CodexSettings(Path("E:/IdeaProjects/agent-root"), None, "full-access", "deny_all"),
        bridge=BridgeSettings(2, 1000, 100, 10),
    )


def create_message(open_id: str = "allowed-user") -> IncomingMessage:
    return IncomingMessage(
        message_id="message-1",
        chat_id="chat-1",
        sender_open_id=open_id,
        message_type="text",
        content='{"text":"检查仓库"}',
        mention_keys=(),
    )


class BridgeTest(unittest.TestCase):
    def test_executes_allowed_message(self) -> None:
        executor = FakeExecutor()
        sender = FakeSender()
        bridge = Bridge(create_config(), executor, sender)  # type: ignore[arg-type]
        try:
            future = bridge.accept_message(create_message())
            future.result(timeout=2)
        finally:
            bridge.close()

        self.assertEqual(executor.prompts, [("chat-1", "检查仓库")])
        self.assertEqual(sender.messages, [("chat-1", REPLY_ACCEPTED), ("chat-1", "检查完成")])

    def test_rejects_user_outside_allowlist(self) -> None:
        executor = FakeExecutor()
        sender = FakeSender()
        bridge = Bridge(create_config(), executor, sender)  # type: ignore[arg-type]
        try:
            future = bridge.accept_message(create_message("blocked-user"))
            future.result(timeout=2)
        finally:
            bridge.close()

        self.assertEqual(executor.prompts, [])
        self.assertEqual(
            sender.messages,
            [
                (
                    "chat-1",
                    REPLY_UNAUTHORIZED_TEMPLATE.format(open_id="blocked-user"),
                )
            ],
        )


if __name__ == "__main__":
    unittest.main()
