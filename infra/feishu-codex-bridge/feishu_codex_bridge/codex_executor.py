"""使用 OpenAI Python Codex SDK 管理会话和执行任务。"""

from __future__ import annotations

from threading import RLock
from typing import Any

from openai_codex import ApprovalMode, Codex, Sandbox, TurnHandle

from .config import CodexSettings


class CodexExecutor:
    """为每个飞书会话维护一个可连续对话的 Codex Thread。"""

    def __init__(self, settings: CodexSettings) -> None:
        self._settings = settings
        self._codex = Codex()
        self._threads: dict[str, Any] = {}
        self._active_handles: dict[str, TurnHandle] = {}
        self._lock = RLock()

    # 每一轮都重复传入 full_access 和 deny_all，防止后续会话配置偏离用户要求。
    def execute(self, session_id: str, prompt: str) -> str:
        thread = self._get_or_create_thread(session_id)
        handle = thread.turn(
            prompt,
            approval_mode=ApprovalMode.deny_all,
            cwd=str(self._settings.workspace),
            model=self._settings.model,
            sandbox=Sandbox.full_access,
        )
        with self._lock:
            self._active_handles[session_id] = handle
        try:
            result = handle.run()
            return result.final_response or ""
        finally:
            with self._lock:
                self._active_handles.pop(session_id, None)

    # /stop 通过 App Server 的 turn interrupt 立即中止当前回合。
    def interrupt(self, session_id: str) -> bool:
        with self._lock:
            handle = self._active_handles.get(session_id)
        if handle is None:
            return False
        handle.interrupt()
        return True

    def reset(self, session_id: str) -> None:
        with self._lock:
            self._threads.pop(session_id, None)

    def close(self) -> None:
        self._codex.close()

    # 新线程固定使用系统完全访问与拒绝审批模式，模型为空时沿用本机 Codex 默认值。
    def _get_or_create_thread(self, session_id: str) -> Any:
        with self._lock:
            existing_thread = self._threads.get(session_id)
            if existing_thread is not None:
                return existing_thread
            new_thread = self._codex.thread_start(
                approval_mode=ApprovalMode.deny_all,
                cwd=str(self._settings.workspace),
                model=self._settings.model,
                sandbox=Sandbox.full_access,
            )
            self._threads[session_id] = new_thread
            return new_thread

