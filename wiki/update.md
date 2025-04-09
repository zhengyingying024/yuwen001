*   v0.0.4
    * 修改版本更新逻辑，现在为每四小时检查一次版本更新
    * 前端界面所有数据数据实现动态更新
    * 新增**单api使用次数统计**，在原API调用统计下方新增可折叠的单api使用次数统计，同时提供进度条查看剩余使用次数
    * 在环境变量中新增`API_KEY_DAILY_LIMIT`，为单api 24小时最大使用次数，默认值为25
    * 在环境变量中新增`BLOCKED_MODELS`，为需要屏蔽的模型名称，多个模型用英文逗号分隔

*   v0.0.3beta
    * 完善了客户端断开连接的处理逻辑（感谢[@warming-afternoon](https://github.com/warming-afternoon)）
    * 新增“假流式传输模式”，该模式默认开启，以解决在某些情况下客户端断开连接的问题。如需关闭，请将环境变量 `FAKE_STREAMING` 设置为 `false`。

*   v0.0.2 修复了在log中错误暴露apikey的问题，修改了客户端断开连接的处理逻辑（感谢[@warming-afternoon](https://github.com/warming-afternoon)）