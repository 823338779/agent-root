"""把飞书 SDK 事件转换为桥接服务内部消息。"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any


@dataclass(frozen=True, slots=True)
class IncomingMessage:
    """完成协议归一化后的飞书消息。"""

    message_id: str
    chat_id: str
    sender_open_id: str | None
    message_type: str
    content: str
    mention_keys: tuple[str, ...]


# 飞书生成模型字段可能为空；归一化阶段只保留执行所需的最小字段集合。
def normalize_event(event: Any) -> IncomingMessage | None:
    event_data = getattr(event, "event", None)
    message = getattr(event_data, "message", None)
    sender = getattr(event_data, "sender", None)
    if message is None or sender is None:
        return None

    message_id = getattr(message, "message_id", None)
    chat_id = getattr(message, "chat_id", None)
    if not isinstance(message_id, str) or not isinstance(chat_id, str):
        return None

    sender_id = getattr(sender, "sender_id", None)
    open_id = getattr(sender_id, "open_id", None)
    mentions = getattr(message, "mentions", None) or []
    mention_keys = tuple(
        key
        for mention in mentions
        if isinstance((key := getattr(mention, "key", None)), str)
    )
    return IncomingMessage(
        message_id=message_id,
        chat_id=chat_id,
        sender_open_id=open_id if isinstance(open_id, str) else None,
        message_type=str(getattr(message, "message_type", "")),
        content=str(getattr(message, "content", "")),
        mention_keys=mention_keys,
    )


# 文本解析移除群聊中的机器人 mention 占位符，并限制传给 Codex 的输入长度。
def extract_prompt(message: IncomingMessage, max_length: int) -> str | None:
    try:
        content = json.loads(message.content)
    except (json.JSONDecodeError, TypeError):
        return None
    text = content.get("text") if isinstance(content, dict) else None
    if not isinstance(text, str):
        return None

    for mention_key in message.mention_keys:
        text = text.replace(mention_key, "")
    return text.strip()[:max_length]


# 长回复按安全长度拆分，优先在换行处切断以保持可读性。
def split_reply(text: str, max_length: int) -> list[str]:
    remaining = text.strip()
    chunks: list[str] = []
    while len(remaining) > max_length:
        candidate = remaining[:max_length]
        newline_index = candidate.rfind("\n")
        split_index = newline_index if newline_index > max_length // 2 else max_length
        chunks.append(remaining[:split_index].rstrip())
        remaining = remaining[split_index:].lstrip()
    if remaining:
        chunks.append(remaining)
    return chunks

