from pathlib import Path
import tempfile
import unittest

from feishu_codex_bridge.config import load_config


VALID_CONFIG = """
[feishu]
app_id = "test-app"
app_secret = "test-secret"
allowed_open_ids = ["allowed-user"]

[codex]
workspace = "{workspace}"
model = ""
sandbox = "full-access"
approval_mode = "deny_all"

[bridge]
max_workers = 2
max_prompt_length = 100
max_reply_length = 20
processed_message_cache_size = 10
"""


class ConfigTest(unittest.TestCase):
    def test_loads_full_access_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            config_path = Path(temp_directory) / "config.toml"
            config_path.write_text(
                VALID_CONFIG.format(workspace=Path(temp_directory).as_posix()),
                encoding="utf-8",
            )

            config = load_config(config_path)

        self.assertEqual(config.codex.sandbox, "full-access")
        self.assertEqual(config.codex.approval_mode, "deny_all")
        self.assertEqual(config.feishu.allowed_open_ids, frozenset({"allowed-user"}))

    def test_rejects_workspace_write_sandbox(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            config_path = Path(temp_directory) / "config.toml"
            content = VALID_CONFIG.format(workspace=Path(temp_directory).as_posix())
            config_path.write_text(
                content.replace('sandbox = "full-access"', 'sandbox = "workspace-write"'),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "full-access"):
                load_config(config_path)


if __name__ == "__main__":
    unittest.main()

