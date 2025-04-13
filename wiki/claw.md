## 使用 Claw Cloud 免费部署 Gemini 反向代理教程

本教程将指导您如何利用 Claw Cloud 的免费额度部署一个 Gemini API 的反向代理服务。

**✨ 优势:**

1.  **完全免费:** 利用平台的免费额度，无需支付费用。
2.  **操作简单:** 部署过程直观，易于上手。
3.  **国内友好:** 部分节点（如日本）对中国大陆访问速度较好。
4.  **流量充足:** 每月提供 10GB 免费流量，对于个人使用 Gemini API 来说通常绰绰有余。

**🔑 前置条件 (满足其一即可):**

*   拥有一个注册时间超过 180 天的 GitHub 账号 (每月可获得 $5 赠金)。
*   使用 Gmail 账号登录 (可获得一个月有效期 $5 赠金)。

**🚀 部署步骤:**

1.  **登录 Claw Cloud 控制台**
    访问 [https://console.run.claw.cloud/signin](https://console.run.claw.cloud/signin) 并使用您的 GitHub 或 Gmail 账号登录。
    ![登录界面](https://i.111666.best/image/Jkwm8sYhiIPBXRSAaKoWjm.png)

2.  **选择区域 (首次登录)**
    首次登录时会提示选择服务器区域。此选择后续可以更改，这里以选择 `日本 (Japan)` 为例。
    ![选择区域](https://i.111666.best/image/XqQa4QQT3vFCrQX71E4fbY.png)

3.  **进入 APP Launchpad**
    在控制台主界面，找到并点击 **APP Launchpad**。
    ![进入 APP Launchpad](https://i.111666.best/image/iheeV6544UTWLrF4X1Eciz.png)

4.  **创建新应用**
    点击 **Create APP** 按钮开始创建。
    ![创建APP](https://i.111666.best/image/J6zOMjnvdiCNRLeZ8XEZ8W.png)

5.  **配置应用信息**
    *   **Application Name:** 填写一个应用名称（必须是**英文**，且以**小写字母**开头）。
    *   **Image Name:** 输入镜像地址 `beijixingxing/hajimi:latest`。
    ![填写应用信息](https://i.111666.best/image/OspzRLDv3AjdwYbyds1sdW.png)

6.  **找到环境变量设置**
    向下滚动页面，找到 **Environment Variables** 部分。
    ![环境变量部分](https://i.111666.best/image/E1vwi9qaMJDEXRXbTuvkcM.png)

7.  **填写环境变量**
    点击 **Add environment variable** 添加以下三个环境变量：
    *   `GEMINI_API_KEYS`: 填入你的 Gemini API Key。如果**有多个 Key**，请用英文逗号 `,` 分隔，例如 `key1,key2,key3`。 **(请务必替换成你自己的有效 Key)**
    *   `PASSWORD`: 设置一个访问此反向代理的密码。**（这不是你的 Gemini Key，而是自定义的访问密码）**
    *   `TZ`: 设置时区，建议填 `Asia/Shanghai`。

    ```env
    GEMINI_API_KEYS=key1,key2,key3
    PASSWORD=设置一个你自己的访问密码
    TZ=Asia/Shanghai
    ```
    ![填写环境变量](https://i.111666.best/image/xTWRoA9mXKNLkLBhqeDq5s.png)

8.  **部署应用**
    返回页面顶部，点击 **Deploy application** 按钮。
    ![部署应用](https://i.111666.best/image/I07hAtm4ZvMwiP0wUxdzTi.png)

9.  **等待部署完成**
    等待应用状态 (`Status`) 变为 **Running**，这表示部署已成功。
    ![部署成功状态](https://i.111666.best/image/Wmrk5Gcx8MFs7SzZv7N7dt.png)

10. **获取反代地址并使用**
    *   切换到 **Network** 标签页。
    *   在右侧会看到一个 URL 地址，这就是你的反向代理地址。点击 **Copy** 复制它。
    *   **重要:** 在你的客户端（如 SillyTavern、OpenCat 等）使用此地址时，需要在**末尾加上 `/v1`**。
        例如，如果复制的地址是 `https://your-app-name.jp.run.claw.cloud`，那么你应该填入客户端的地址是 `https://your-app-name.jp.run.claw.cloud/v1`。同时，填入你在第 7 步设置的 `PASSWORD` 作为 API Key 或密码（具体取决于客户端设置）。

    ![获取反代地址](https://i.111666.best/image/75V3DYZNqaLbA2H4iq8vwo.png)

---

🎉 恭喜！你现在拥有了一个免费的 Gemini 反向代理服务。
