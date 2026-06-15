from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from core.Filter import GroupAddRequestFilter
from main import AppReviewPlugin


class DummyContext:
    def get_config(self):
        return {}


def make_plugin(config=None) -> AppReviewPlugin:
    return AppReviewPlugin(DummyContext(), config=config or {})


def make_event(raw_message=None, call_action=None):
    api = SimpleNamespace(call_action=call_action or AsyncMock())
    bot = SimpleNamespace(api=api)
    message_obj = SimpleNamespace(raw_message=raw_message or {})
    return SimpleNamespace(bot=bot, message_obj=message_obj)


def test_plugin_uses_astrbot_config_without_local_defaults():
    plugin = make_plugin()

    assert plugin.config == {}
    assert plugin.review_settings.accept_keywords == []
    assert plugin.review_settings.reject_keywords == []
    assert plugin.review_settings.auto_accept is False
    assert plugin.review_settings.auto_reject is False
    assert plugin.review_settings.reject_reason == ""
    assert plugin.review_settings.delay_seconds == 0
    assert plugin.decide_review("三连了") is None


def test_plugin_extracts_runtime_config_values():
    config = {
        "global_review": {
            "accept_keywords": ["通过", ""],
            "reject_keywords": ["拒绝"],
            "auto_accept": False,
            "auto_reject": True,
            "reject_reason": "不符合要求",
            "delay_seconds": 3,
        }
    }

    plugin = make_plugin(config)

    assert plugin.config is config
    assert plugin.review_settings.accept_keywords == ["通过"]
    assert plugin.review_settings.reject_keywords == ["拒绝"]
    assert plugin.review_settings.auto_accept is False
    assert plugin.review_settings.auto_reject is True
    assert plugin.review_settings.reject_reason == "不符合要求"
    assert plugin.review_settings.delay_seconds == 3


def test_non_list_keyword_config_is_ignored():
    plugin = make_plugin({"global_review": {"accept_keywords": "通过", "reject_keywords": "拒绝"}})

    assert plugin.review_settings.accept_keywords == []
    assert plugin.review_settings.reject_keywords == []


def test_group_rule_overrides_global_rule():
    plugin = make_plugin(
        {
            "global_review": {
                "accept_keywords": ["通过"],
                "reject_keywords": ["拒绝"],
                "reject_reason": "全局拒绝",
            },
            "group_review_rules": [
                {
                    "group_id": "20002",
                    "accept_keywords": ["只同意"],
                    "reject_keywords": ["明确拒绝"],
                    "reject_reason": "分群拒绝",
                    "delay_seconds": 5,
                }
            ],
        }
    )

    settings = plugin.settings_for_group("20002")
    assert settings.accept_keywords == ["只同意"]
    assert settings.reject_keywords == ["明确拒绝"]
    assert settings.reject_reason == "分群拒绝"
    assert settings.delay_seconds == 5
    assert plugin.settings_for_group("99999").accept_keywords == ["通过"]


def test_group_add_request_filter_matches_add_request():
    event = make_event(
        {
            "post_type": "request",
            "request_type": "group",
            "sub_type": "add",
        }
    )

    assert GroupAddRequestFilter().filter(event, cfg=None)


@pytest.mark.parametrize(
    "raw_message",
    [
        {},
        {"post_type": "message", "request_type": "group", "sub_type": "add"},
        {"post_type": "request", "request_type": "friend", "sub_type": "add"},
        {"post_type": "request", "request_type": "group", "sub_type": "invite"},
    ],
)
def test_group_add_request_filter_rejects_other_events(raw_message):
    assert not GroupAddRequestFilter().filter(make_event(raw_message), cfg=None)


def test_auto_accept_takes_priority_over_auto_reject():
    plugin = make_plugin({"auto_accept": True, "auto_reject": True})

    decision = plugin.decide_review("拒绝")

    assert decision is not None
    assert decision.approve is True
    assert decision.reason == ""


def test_reject_keyword_takes_priority_over_accept_keyword():
    plugin = make_plugin(
        {
            "accept_keywords": ["通过"],
            "reject_keywords": ["拒绝"],
            "reject_reason": "不符合要求",
        }
    )

    decision = plugin.decide_review("通过但拒绝")

    assert decision is not None
    assert decision.approve is False
    assert decision.reason == "不符合要求"
    assert decision.matched_keyword == "拒绝"


def test_accept_keyword_approves_request():
    plugin = make_plugin({"accept_keywords": ["三连了"]})

    decision = plugin.decide_review("我已经三连了")

    assert decision is not None
    assert decision.approve is True
    assert decision.matched_keyword == "三连了"


def test_unmatched_comment_waits_for_manual_review():
    plugin = make_plugin()

    assert plugin.decide_review("你好") is None


@pytest.mark.asyncio
async def test_approve_request_uses_current_bot_api_call_action():
    plugin = make_plugin()
    call_action = AsyncMock()
    event = make_event(call_action=call_action)

    ok = await plugin.approve_request(
        event,
        flag="flag-1",
        approve=False,
        reason="不符合要求",
    )

    assert ok is True
    call_action.assert_awaited_once_with(
        "set_group_add_request",
        flag="flag-1",
        sub_type="add",
        approve=False,
        reason="不符合要求",
    )


@pytest.mark.asyncio
async def test_handle_group_join_request_skips_unmatched_comment():
    plugin = make_plugin()
    call_action = AsyncMock()
    event = make_event(
        {
            "post_type": "request",
            "request_type": "group",
            "sub_type": "add",
            "flag": "flag-1",
            "user_id": 10001,
            "group_id": 20002,
            "comment": "你好",
        },
        call_action=call_action,
    )

    await plugin.handle_group_join_request(event)

    call_action.assert_not_called()
