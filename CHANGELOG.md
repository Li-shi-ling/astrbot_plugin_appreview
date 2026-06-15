# 更新日志

## v1.3.1

- 添加 lishining 为第二作者。

## v1.3.0

- 迁移到新版 AstrBot 事件过滤器注册方式。
- 新增独立的加群申请过滤器，专门匹配 `request/group/add` 事件。
- 调整审核处理逻辑，直接使用当前 AstrBot 的 `event.bot.api.call_action` 接口。
- 增加单元测试覆盖过滤器匹配、审核决策优先级和审核调用参数。
