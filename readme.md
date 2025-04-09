# 🚀 HAJIMI Gemini API Proxy

基于某论坛上一位大佬[@Mrjwj34](https://github.com/Moonfanz)基于另一位大佬[@Moonfanzp](https://github.com/Moonfanz)的代码的修改修改而来，由于大佬好长时间没有维护，我自己也遇到些bug，就魔改了一下，求star求star求star

这是一个基于 FastAPI 构建的 Gemini API 代理，旨在提供一个简单、安全且可配置的方式来访问 Google 的 Gemini 模型。适用于在 Hugging Face Spaces 上部署，并支持openai api格式的工具集成。
###  使用文档
- [【推荐】huggingface的使用文档（手机电脑均可使用）](./wiki/huggingface.md)
- [termux部署的使用文档（手机使用）](./wiki/Termux.md)
- [docker部署的使用文档（服务器自建使用）](./wiki/docker.md)
###  更新日志
*   v0.1.0
    * 使用vue重写前端界面，适配移动端
    * 前端界面添加黑夜模式
    * 支持为多模态模型上传图片
    * 可用秘钥数量将异步更新，防止阻塞进程
    * 这次真能北京时间16点自动重置统计数据了
    * 为api秘钥使用统计新增模型使用统计，可分别统计使用不同模型的次数
    * 修改默认api可用次数为100次
    * 降低默认伪装信息长度为5，以减少对上下文的污染

*   v0.0.5beta
    * 新增“**伪装信息**功能，默认开启，可在转发消息中添加随机字符串伪装消息，防止被检测
    * 修复若干bug
    * 为前端界面新增**功能配置**栏目，可检查功能是否开启
    * 北京时间16点自动重置统计数据
    * 在环境变量中新增`RANDOM_STRING`，是否启用伪装信息，默认值为true
    * 在环境变量中新增`RANDOM_STRING_LENGTH`，伪装信息长度，默认为20
    * 为git用户提供单独的`Dockerfile_git`
* 历史版本更新日志请查看[update](./wiki/update.md)

## ✨ 主要功能：

### 🔑 API 密钥轮询和管理

### 📑 模型列表接口

### 💬 聊天补全接口：

*   提供 `/v1/chat/completions` 接口，支持流式（streaming）和非流式响应，与 OpenAI API 格式兼容。
*   自动将 OpenAI 格式的请求转换为 Gemini 格式。

### 🔒 密码保护（可选）：

*   通过 `PASSWORD` 环境变量设置密码。
*   提供默认密码 `"123"`。

### 🚦 速率限制和防滥用：

*   通过环境变量自定义限制：
    *   `MAX_REQUESTS_PER_MINUTE`：每分钟最大请求数（默认 30）。
    *   `MAX_REQUESTS_PER_DAY_PER_IP`：每天每个 IP 最大请求数（默认 600）。
*   超过速率限制时返回 429 错误。

### 🧩 服务兼容

*   提供的接口与 OpenAI API 格式兼容,便于接入各种服务

## ⚠️ 注意事项：

*   **强烈建议在生产环境中设置 `PASSWORD` 环境变量，并使用强密码。**
*   根据你的使用情况调整速率限制相关的环境变量。
*   确保你的 Gemini API 密钥具有足够的配额。
