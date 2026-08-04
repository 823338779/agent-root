from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from openai_codex import ApprovalMode, Sandbox

from feishu_codex_bridge.codex_executor import CodexExecutor
from feishu_codex_bridge.config import CodexSettings


class CodexExecutorTest(unittest.TestCase):
    @patch("feishu_codex_bridge.codex_executor.Codex")
    def test_uses_full_access_without_approval(self, codex_type: MagicMock) -> None:
        thread = codex_type.return_value.thread_start.return_value
        handle = thread.turn.return_value
        handle.run.return_value = SimpleNamespace(final_response="完成")
        settings = CodexSettings(
            workspace=Path("E:/IdeaProjects/agent-root"),
            model=None,
            sandbox="full-access",
            approval_mode="deny_all",
        )
        executor = CodexExecutor(settings)

        response = executor.execute("chat-1", "检查仓库")

        self.assertEqual(response, "完成")
        codex_type.return_value.thread_start.assert_called_once_with(
            approval_mode=ApprovalMode.deny_all,
            cwd=str(settings.workspace),
            model=None,
            sandbox=Sandbox.full_access,
        )
        thread.turn.assert_called_once_with(
            "检查仓库",
            approval_mode=ApprovalMode.deny_all,
            cwd=str(settings.workspace),
            model=None,
            sandbox=Sandbox.full_access,
        )


if __name__ == "__main__":
    unittest.main()

