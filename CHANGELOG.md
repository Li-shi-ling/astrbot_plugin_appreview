# 更新日志

## v1.3.3

- 参考 `astrbot_plugin_util` 的配置处理方式，直接保存 AstrBot 配置对象并解析为实例属性。

## v1.3.2

- 移除代码内 `_default_config()`，默认配置交由 AstrBot 插件配置系统处理。

## v1.3.1

- 添加 lishining 为第二作者。

## v1.3.0

- 迁移到新版 AstrBot 事件过滤器注册方式。
- 新增独立的加群申请过滤器，专门匹配 `request/group/add` 事件。
- 调整审核处理逻辑，直接使用当前 AstrBot 的 `event.bot.api.call_action` 接口。
- 增加单元测试覆盖过滤器匹配、审核决策优先级和审核调用参数。
