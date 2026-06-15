from astrbot.api.event import AstrMessageEvent
from astrbot.core.config import AstrBotConfig
from astrbot.core.star.filter import HandlerFilter
from astrbot.core.star.register.star_handler import get_handler_or_create
from astrbot.core.star.star_handler import EventType


class GroupAddRequestFilter(HandlerFilter):
    """检查 OneBot 加群申请请求事件。"""

    def filter(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        raw_message = getattr(event.message_obj, "raw_message", None)
        if not isinstance(raw_message, dict):
            return False
        return (
            raw_message.get("post_type") == "request"
            and raw_message.get("request_type") == "group"
            and raw_message.get("sub_type") == "add"
        )


def register_group_add_request(**kwargs):
    """注册一个 GroupAddRequestFilter。"""

    def decorator(awaitable):
        handler_md = get_handler_or_create(awaitable, EventType.AdapterMessageEvent)
        handler_md.event_filters.append(GroupAddRequestFilter())
        return awaitable

    return decorator
