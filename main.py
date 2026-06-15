from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)

try:
    from .core.Filter import register_group_add_request
except ImportError:
    from core.Filter import register_group_add_request


@dataclass(slots=True)
class ReviewDecision:
    approve: bool
    reason: str = ""
    matched_keyword: str = ""


@register(
    "astrbot_plugin_appreview",
    "qiqi, lishining",
    "一个可以通过关键词来同意或拒绝进入群聊的插件",
    "1.3.3",
)
class AppReviewPlugin(Star):
    def __init__(self, context: Context, config: Mapping[str, Any] | None = None):
        super().__init__(context)
        self.config = config if config is not None else self._load_config()
        self.accept_keywords = self._config_keywords("accept_keywords")
        self.reject_keywords = self._config_keywords("reject_keywords")
        self.auto_accept = bool(self._config_value("auto_accept", False))
        self.auto_reject = bool(self._config_value("auto_reject", False))
        self.reject_reason = str(self._config_value("reject_reason", ""))
        self.delay_seconds = max(0, int(self._config_value("delay_seconds", 0) or 0))
        logger.info("群聊申请审核插件配置加载成功: %s", self.config)

    def _load_config(self) -> Mapping[str, Any]:
        """加载 AstrBot 提供的插件配置。"""
        try:
            return self.context.get_config() or {}
        except Exception as exc:
            logger.error("群聊申请审核插件配置加载失败: %s", exc)
            return {}

    def _config_value(self, key: str, default: Any) -> Any:
        return self.config.get(key, default)

    def _config_keywords(self, key: str) -> list[str]:
        value = self._config_value(key, [])
        if not isinstance(value, list):
            return []
        return [str(item) for item in value if str(item)]

    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    @register_group_add_request()
    async def handle_group_join_request(self, event: AiocqhttpMessageEvent) -> None:
        """处理 OneBot 加群申请事件。"""
        request_data = self._raw_request_data(event)
        flag = str(request_data.get("flag", ""))
        user_id = str(request_data.get("user_id", ""))
        group_id = str(request_data.get("group_id", ""))
        comment = str(request_data.get("comment", ""))

        logger.info(
            "收到加群请求: 用户ID=%s, 群ID=%s, 验证信息=%s",
            user_id,
            group_id,
            comment,
        )

        decision = self.decide_review(comment)
        if decision is None:
            logger.info(
                "用户 %s 加入群 %s 的请求未匹配到自动审核规则，等待手动审核",
                user_id,
                group_id,
            )
            return

        if self.delay_seconds > 0:
            logger.info(
                "将在 %s 秒后%s用户 %s 加入群 %s 的请求",
                self.delay_seconds,
                "同意" if decision.approve else "拒绝",
                user_id,
                group_id,
            )
            await asyncio.sleep(self.delay_seconds)

        ok = await self.approve_request(
            event,
            flag=flag,
            approve=decision.approve,
            reason=decision.reason,
        )
        if not ok:
            logger.warning("处理用户 %s 加入群 %s 的请求失败", user_id, group_id)
            return

        if decision.matched_keyword:
            logger.info(
                "根据关键词 '%s' %s用户 %s 加入群 %s 的请求",
                decision.matched_keyword,
                "同意" if decision.approve else "拒绝",
                user_id,
                group_id,
            )
        else:
            logger.info(
                "自动%s用户 %s 加入群 %s 的请求",
                "同意" if decision.approve else "拒绝",
                user_id,
                group_id,
            )

    def decide_review(self, comment: str) -> ReviewDecision | None:
        """根据配置和申请验证信息生成审核决策。"""
        if self.auto_accept:
            return ReviewDecision(approve=True)

        if self.auto_reject:
            return ReviewDecision(approve=False, reason=self.reject_reason)

        normalized_comment = comment.lower()
        for keyword in self.reject_keywords:
            if keyword.lower() in normalized_comment:
                return ReviewDecision(
                    approve=False,
                    reason=self.reject_reason,
                    matched_keyword=keyword,
                )

        for keyword in self.accept_keywords:
            if keyword.lower() in normalized_comment:
                return ReviewDecision(approve=True, matched_keyword=keyword)

        return None

    async def approve_request(
        self,
        event: AstrMessageEvent,
        flag: str,
        approve: bool = True,
        reason: str = "",
    ) -> bool:
        """调用 OneBot API 同意或拒绝加群申请。"""
        if not flag:
            logger.warning("加群申请缺少 flag，无法处理")
            return False

        call_action = self._resolve_call_action(event)
        if call_action is None:
            logger.warning("当前事件不支持 OneBot call_action，无法处理加群申请")
            return False

        payload = {
            "flag": flag,
            "sub_type": "add",
            "approve": approve,
            "reason": reason if reason else "",
        }

        try:
            await call_action("set_group_add_request", **payload)
            return True
        except Exception as exc:
            logger.error("处理群聊申请失败: %s", exc)
            return False

    @staticmethod
    def _resolve_call_action(event: AstrMessageEvent):
        bot = getattr(event, "bot", None)
        api = getattr(bot, "api", None)
        call_action = getattr(api, "call_action", None)
        if callable(call_action):
            return call_action
        call_action = getattr(bot, "call_action", None)
        if callable(call_action):
            return call_action
        return None

    @staticmethod
    def _raw_request_data(event: AstrMessageEvent) -> dict[str, Any]:
        raw_message = getattr(event.message_obj, "raw_message", None)
        if isinstance(raw_message, dict):
            return raw_message
        return {}

    async def terminate(self) -> None:
        """插件被卸载或停用时调用。"""
        logger.info("群聊申请审核插件已停用")
