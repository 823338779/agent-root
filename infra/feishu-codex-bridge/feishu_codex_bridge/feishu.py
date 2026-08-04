"""封装飞书 Python SDK 的消息发送和长连接入口。"""

from __future__ import annotations

import json
import logging

import lark_oapi as lark
from lark_oapi.api.im.v1 import (
    CreateMessageRequest,
    CreateMessageRequestBody,
    P2ImMessageReceiveV1,
)

from .bridge import Bridge, MessageSender
from .config import FeishuConfig
from .constants import CHAT_ID_TYPE, LOG_SEND_FAILURE, TEXT_MESSAGE_TYPE

LOGGER = logging.getLogger(__name__)
CLIENT_SOURCE = "feishu-codex-bridge"


class FeishuMessageSender(MessageSender):
    """使用应用机器人身份向指定飞书会话发送文本。"""

    def __init__(self, config: FeishuConfig) -> None:
        self._client = (
            lark.Client.builder()
            .app_id(config.app_id)
            .app_secret(config.app_secret)
            .build()
        )

    # 飞书 SDK 不会对所有业务错误抛异常，因此显式检查响应状态。
    def send_text(self, chat_id: str, text: str) -> None:
        body = (
            CreateMessageRequestBody.builder()
            .receive_id(chat_id)
            .msg_type(TEXT_MESSAGE_TYPE)
            .content(json.dumps({"text": text}, ensure_ascii=False))
            .build()
        )
        request = (
            CreateMessageRequest.builder()
            .receive_id_type(CHAT_ID_TYPE)
            .request_body(body)
            .build()
        )
        response = self._client.im.v1.message.create(request)
        if not response.success():
            error_message = (
                f"{LOG_SEND_FAILURE}: code={response.code}, "
                f"msg={response.msg}, log_id={response.get_log_id()}"
            )
            raise RuntimeError(error_message)


# 长连接事件处理器只把事件交给 Bridge；实际 Codex 执行发生在后台线程池。
def create_websocket_client(config: FeishuConfig, bridge: Bridge) -> lark.ws.Client:
    def handle_message(event: P2ImMessageReceiveV1) -> None:
        bridge.accept_event(event)

    event_handler = (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_im_message_receive_v1(handle_message)
        .build()
    )
    return lark.ws.Client(
        config.app_id,
        config.app_secret,
        log_level=lark.LogLevel.INFO,
        event_handler=event_handler,
        auto_reconnect=True,
        source=CLIENT_SOURCE,
    )

