import json
import unittest

from feishu_codex_bridge.message import IncomingMessage, extract_prompt, split_reply


class MessageTest(unittest.TestCase):
    def test_extracts_prompt_and_removes_mention(self) -> None:
        message = IncomingMessage(
            message_id="message-1",
            chat_id="chat-1",
            sender_open_id="allowed-user",
            message_type="text",
            content=json.dumps({"text": "@_user_1 检查仓库"}),
            mention_keys=("@_user_1",),
        )

        self.assertEqual(extract_prompt(message, 100), "检查仓库")

    def test_splits_long_reply_on_newline(self) -> None:
        self.assertEqual(split_reply("第一段内容\n第二段内容", 8), ["第一段内容", "第二段内容"])


if __name__ == "__main__":
    unittest.main()

