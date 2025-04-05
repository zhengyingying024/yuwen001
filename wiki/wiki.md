# hajimi使用教程

## 1. 安装
### 1.1 下载
- 从[releases](https://github.com/wyeeeee/hajimi/releases))下载最新版本。
- 下载完成后解压到任意目录。

### 1.2 使用huggingface space部署项目
- 在[huggingface](https://huggingface.co)注册账号。
- 注册完成后，进入[spaces](https://huggingface.co/spaces)如图所示，点击new spaces。<br>![spaces](https://github.com/wyeeeee/hajimi/blob/main/wiki/img/spaces.png)
- 如图所示，填入创建选项，注意space name不要使用符号，填写完成后，点击create space<br>![create_space](https://github.com/wyeeeee/hajimi/blob/main/wiki/img/create_space.png)
- 如图所示，选择upload files<br>![files](https://github.com/wyeeeee/hajimi/blob/main/wiki/img/files.png)
- 如图所示，将1.1下载并解压的文件全部拖入，上传完成后点击Commit changes to main<br>![upload_files](https://github.com/wyeeeee/hajimi/blob/main/wiki/img/upload_files.png)

### 1.2 配置环境变量
- 如图所示，进入settings界面<br>![settings](https://github.com/wyeeeee/hajimi/blob/main/wiki/img/settings.png)
- 如图所示，在settings界面中找到Variables and secrets，点击new secrets<br>![secrets](https://github.com/wyeeeee/hajimi/blob/main/wiki/img/secrets.png)
- 添加环境变量，如图所示为添加GEMINI_API_KEYS环境变量，在value中填入具体apikey<br>![KEYS](https://github.com/wyeeeee/hajimi/blob/main/wiki/img/KEYS.png)
- 等待项目部署完成，app界面显示如图界面，即完成<br>![app](https://github.com/wyeeeee/hajimi/blob/main/wiki/img/app.png)

### 1.3 环境变量说明
#### 重要环境变量
- `GEMINI_API_KEYS`：从google ai studio 获取的API密钥，支持多个API密钥，以英文逗号分隔（例:apikey1,apikey2,apikey3）。
- `PASSWORD`：用户访问所需的password，如不填写默认为123。
#### 可选环境变量
-   `MAX_REQUESTS_PER_MINUTE`：（可选）每分钟最大请求数。
-   `MAX_REQUESTS_PER_DAY_PER_IP`：（可选）每天每个 IP 最大请求数。
-   `FAKE_STREAMING`：（可选）是否启用假流式传输，默认为true。
-   `API_KEY_DAILY_LIMIT`: 单api 24小时最大使用次数，默认值为25
-   `BLOCKED_MODELS`，（可选）需要屏蔽的模型名称，多个模型用英文逗号分隔

### 1.4 在酒馆中使用
在酒馆api连接配置中，选择兼容openai格式，URL格式为`https://(huggingface用户名)-(huggingface项目名).hf.space/v1`（注意为https）。自定义 API 密钥为1.3中配置的`PASSWORD`。

### 1.5 假流式传输模式说明
- 如需使用假流式传输模式，请确保酒馆中的预设配置里的流式传输选项为打开。
- 众所周知，gemini无法使用流式传输模式输出，但酒馆在非串流模式下等待一段时间后会自动中断连接，导致请求终止，同时酒馆不支持自定义最长等待时间，因此本项目提出假串流模式，在使用非串流模式获取gemini回复的等待期间，持续向酒馆发送空包保持连接，经测试能有效避免酒馆在gemini非串流模式下的自动中断连接情况。
- 目前项目在0.0.3测试版中已默认开启假流式传输模式，如需关闭，请将环境变量`FAKE_STREAMING`设置为false。

### 1.6 问题解决
- `429报错，空回复`：内容触发了谷歌的审查机制，暂时的解决方案是在破限的最前方手动新增一栏，里面随便填点东西就不429了（或者把破线的开头那段丢给ai重新生成，意思相同，文字跟原来不同） ，或寻求破限作者/社区的帮助。
- `408报错，酒馆断开连接`：参考1.5中假流式传输模式说明，开启假流式传输模式。

### 1.7 💻 本地运行（可选,未测试但是应该能行）：

1.  安装依赖：`pip install -r requirements.txt`
2.  设置环境变量（如上所述）。
3.  运行：`uvicorn app.main:app --reload --host 0.0.0.0 --port 7860`

### 1.8 💻 手机本地运行（可选,安装耗时长）：

[Termux 安装与配置 Hajimi 项目教程](./Termux.md)

### 🔌 接入其他服务

1.  在连接中选择OpenAI
2.  在API Base URL中填入`https://(huggingface用户名)-(huggingface项目名).hf.space/v1`
3.  在API Key中填入`PASSWORD`环境变量的值,如未设置则填入`123`
