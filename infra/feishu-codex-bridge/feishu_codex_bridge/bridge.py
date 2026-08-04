"""处理鉴权、命令路由、任务并发和消息去重。"""

from __future__ import annotations

from collections import OrderedDict
from concurrent.futures import Future, ThreadPoolExecutor
import logging
from threading import RLock
from typing import Protocol

from .codex_executor import CodexExecutor
from .config import AppConfig
from .constants import (
    COMMAND_HELP,
    COMMAND_NEW,
    COMMAND_STATUS,
    COMMAND_STOP,
    LOG_MESSAGE_FAILURE,
    REPLY_ACCEPTED,
    REPLY_BUSY,
    REPLY_EMPTY,
    REPLY_FAILED_PREFIX,
    REPLY_HELP,
    REPLY_IDLE,
    REPLY_NEW_THREAD,
    REPLY_NEW_THREAD_BUSY,
    REPLY_NO_RESPONSE,
    REPLY_RUNNING,
    REPLY_STOPPED,
    REPLY_UNAUTHORIZED_TEMPLATE,
    REPLY_UNSUPPORTED,
    TEXT_MESSAGE_TYPE,
)
from .message import IncomingMessage, extract_prompt, normalize_event, split_reply

LOGGER = logging.getLogger(__name__)


class MessageSender(Protocol):
    """飞书文本发送能力的最小接口。"""

    def send_text(self, chat_id: str, text: str) -> None: ...


class Bridge:
    """把通过白名单校验的飞书文本任务交给 Codex。"""

    def __init__(
        self,
        config: AppConfig,
        executor: CodexExecutor,
        sender: MessageSender,
    ) -> None:
        self._config = config
        self._executor = executor
        self._sender = sender
        self._pool = ThreadPoolExecutor(
            max_workers=config.bridge.max_workers,
            thread_name_prefix="feishu-codex",
        )
        self._processed_ids: OrderedDict[str, None] = OrderedDict()
        self._active_sessions: set[str] = set()
        self._lock = RLock()

    # 事件线程只做轻量解析并提交后台任务，保证飞书回调能在三秒内返回。
    def accept_event(self, event: object) -> Future[None] | None:
        message = normalize_event(event)
        if message is None or not self._remember_message(message.message_id):
            return None
        return self.accept_message(message)

    def accept_message(self, message: IncomingMessage) -> Future[None]:
        return self._pool.submit(self._handle_message_safely, message)

    def close(self) -> None:
        self._pool.shutdown(wait=True, cancel_futures=False)
        self._executor.close()

    # 所有后台异常集中记录，避免异常逃出飞书 SDK 回调导致事件重推。
    def _handle_message_safely(self, message: IncomingMessage) -> None:
        try:
            self._handle_message(message)
        except Exception:
            LOGGER.exception(LOG_MESSAGE_FAILURE)

    def _handle_message(self, message: IncomingMessage) -> None:
        if message.sender_open_id not in self._config.feishu.allowed_open_ids:
            sender_open_id = message.sender_open_id or "<missing>"
            self._sender.send_text(
                message.chat_id,
                REPLY_UNAUTHORIZED_TEMPLATE.format(open_id=sender_open_id),
            )
            return
        if message.message_type != TEXT_MESSAGE_TYPE:
            self._sender.send_text(message.chat_id, REPLY_UNSUPPORTED)
            return

        prompt = extract_prompt(message, self._config.bridge.max_prompt_length)
        if not prompt:
            self._sender.send_text(message.chat_id, REPLY_EMPTY)
            return
        if self._handle_command(message.chat_id, prompt.lower()):
            return
        self._run_task(message.chat_id, prompt)

    # 控制命令不进入 Codex，确保会话管理与停止行为不受模型解释影响。
    def _handle_command(self, chat_id: str, command: str) -> bool:
        if command == COMMAND_HELP:
            self._sender.send_text(chat_id, REPLY_HELP)
            return True
        if command == COMMAND_STATUS:
            reply = REPLY_RUNNING if self._is_active(chat_id) else REPLY_IDLE
            self._sender.send_text(chat_id, reply)
            return True
        if command == COMMAND_STOP:
            stopped = self._executor.interrupt(chat_id)
            self._sender.send_text(chat_id, REPLY_STOPPED if stopped else REPLY_IDLE)
            return True
        if command == COMMAND_NEW:
            if self._is_active(chat_id):
                self._sender.send_text(chat_id, REPLY_NEW_THREAD_BUSY)
            else:
                self._executor.reset(chat_id)
                self._sender.send_text(chat_id, REPLY_NEW_THREAD)
            return True
        return False

    # 同一飞书会话只允许一个在途回合，避免破坏 Codex Thread 的顺序。
    def _run_task(self, chat_id: str, prompt: str) -> None:
        if not self._activate(chat_id):
            self._sender.send_text(chat_id, REPLY_BUSY)
            return
        try:
            self._sender.send_text(chat_id, REPLY_ACCEPTED)
            response = self._executor.execute(chat_id, prompt)
            chunks = split_reply(response, self._config.bridge.max_reply_length)
            for chunk in chunks or [REPLY_NO_RESPONSE]:
                self._sender.send_text(chat_id, chunk)
        except Exception as error:
            self._sender.send_text(chat_id, f"{REPLY_FAILED_PREFIX}{error}")
        finally:
            with self._lock:
                self._active_sessions.discard(chat_id)

    # 消息 ID 使用有界 LRU 集合去重，避免长连接重推造成重复系统操作。
    def _remember_message(self, message_id: str) -> bool:
        with self._lock:
            if message_id in self._processed_ids:
                return False
            self._processed_ids[message_id] = None
            if len(self._processed_ids) > self._config.bridge.processed_message_cache_size:
                self._processed_ids.popitem(last=False)
            return True

    def _activate(self, chat_id: str) -> bool:
        with self._lock:
            if chat_id in self._active_sessions:
                return False
            self._active_sessions.add(chat_id)
            return True

    def _is_active(self, chat_id: str) -> bool:
        with self._lock:
            return chat_id in self._active_sessions
