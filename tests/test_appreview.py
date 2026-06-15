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
