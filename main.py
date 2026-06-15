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


@dataclass(slots=True)
class ReviewSettings:
    accept_keywords: list[str]
    reject_keywords: list[str]
    auto_accept: bool
    auto_reject: bool
    reject_reason: str
    delay_seconds: int


@register(
    "astrbot_plugin_appreview",
    "qiqi, lishining",
    "一个可以通过关键词来同意或拒绝进入群聊的插件",
    "1.4.2",
)
class AppReviewPlugin(Star):
    def __init__(self, context: Context, config: Mapping[str, Any] | None = None):
        super().__init__(context)
        self.config = config if config is not None else self._load_config()
        global_config = self._config_section("global_review")
        self.review_settings = self._settings_from_config(global_config)
        self.group_review_settings = self._load_group_review_settings()
        logger.info("群聊申请审核插件配置加载成功: %s", self.config)

    def _load_config(self) -> Mapping[str, Any]:
        """加载 AstrBot 提供的插件配置。"""
        try:
            return self.context.get_config() or {}
        except Exception as exc:
            logger.error("群聊申请审核插件配置加载失败: %s", exc)
            return {}

    def _config_section(self, key: str) -> dict[str, Any]:
        value = self.config.get(key, {})
        return dict(value) if isinstance(value, Mapping) else {}

    def _config_value(self, section_config: Mapping[str, Any], key: str, default: Any) -> Any:
        if key in section_config:
            return section_config.get(key, default)
        return self.config.get(key, default)

    def _config_keywords(self, section_config: Mapping[str, Any], key: str) -> list[str]:
        value = self._config_value(section_config, key, [])
        if not isinstance(value, list):
            return []
        return [keyword for item in value if (keyword := str(item).strip())]

    def _settings_from_config(self, section_config: Mapping[str, Any]) -> ReviewSettings:
        return ReviewSettings(
            accept_keywords=self._config_keywords(section_config, "accept_keywords"),
            reject_keywords=self._config_keywords(section_config, "reject_keywords"),
            auto_accept=bool(self._config_value(section_config, "auto_accept", False)),
            auto_reject=bool(self._config_value(section_config, "auto_reject", False)),
            reject_reason=str(self._config_value(section_config, "reject_reason", "")),
            delay_seconds=max(
                0,
                int(self._config_value(section_config, "delay_seconds", 0) or 0),
            ),
        )

    def _load_group_review_settings(self) -> dict[str, ReviewSettings]:
        raw_rules = self.config.get("group_review_rules", [])
        if not isinstance(raw_rules, list):
            return {}

        rules: dict[str, ReviewSettings] = {}
        for raw_rule in raw_rules:
            if not isinstance(raw_rule, Mapping):
                continue
            group_id = str(raw_rule.get("group_id", "")).strip()
            if not group_id:
                continue
            rules[group_id] = self._settings_from_config(raw_rule)
        return rules

    def settings_for_group(self, group_id: str) -> ReviewSettings:
        return self.group_review_settings.get(str(group_id), self.review_settings)

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

        settings = self.settings_for_group(group_id)
        decision = self.decide_review(comment, settings)
        if decision is None:
            logger.info(
                "用户 %s 加入群 %s 的请求未匹配到自动审核规则，等待手动审核",
                user_id,
                group_id,
            )
            return

        if settings.delay_seconds > 0:
            logger.info(
                "将在 %s 秒后%s用户 %s 加入群 %s 的请求",
                settings.delay_seconds,
                "同意" if decision.approve else "拒绝",
                user_id,
                group_id,
            )
            await asyncio.sleep(settings.delay_seconds)

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

    def decide_review(
        self,
        comment: str,
        settings: ReviewSettings | None = None,
    ) -> ReviewDecision | None:
        """根据配置和申请验证信息生成审核决策。"""
        settings = settings or self.review_settings

        if settings.auto_accept:
            return ReviewDecision(approve=True)

        if settings.auto_reject:
            return ReviewDecision(approve=False, reason=settings.reject_reason)

        normalized_comment = comment.lower()
        for keyword in settings.reject_keywords:
            if keyword.lower() in normalized_comment:
                return ReviewDecision(
                    approve=False,
                    reason=settings.reject_reason,
                    matched_keyword=keyword,
                )

        for keyword in settings.accept_keywords:
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
