# Termux 安装与配置 Hajimi 项目教程

## 一、切换 Termux 清华源（有“魔法”的可跳过）

```bash
sed -i 's@^\(deb.*stable main\)$@#\1\ndeb https://mirrors.tuna.tsinghua.edu.cn/termux/apt/termux-main stable main@' $PREFIX/etc/apt/sources.list
```

## 二、安装必要依赖

```bash
apt update && apt --yes upgrade && apt --yes install git python rust
```

## 三、配置 pip 使用清华源（有“魔法”的可跳过）

```bash
pip config set global.index-url https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple
```

## 四、配置 Rust 使用清华源（有“魔法”的可跳过）

```bash
export CARGO_REGISTRIES_CRATES_IO_INDEX="https://mirrors.tuna.tsinghua.edu.cn/git/crates.io-index.git"
```

## 五、克隆项目源码（有“魔法”的可去除加速链接）

```bash
git clone https://github.boki.moe/https://github.com/wyeeeee/hajimi
```

## 六、进入项目目录

```bash
cd hajimi
```

## 七、安装 Python 依赖

```bash
pip install tzdata -r requirements.txt
```

> **提示**：安装和构建过程会比较慢，请耐心等待。

---

## 八、配置 Termux Widget 启动脚本

### 1. 安装 Termux Widget 插件  
项目地址：[termux-widget](https://github.com/termux/termux-widget)

### 2. 使用 MT 管理器：
- 打开 Termux 的根目录
- 新建 `.shortcuts` 文件夹
- 在其中创建一个空白脚本文件（例如 `哈基米启动`），内容如下：

```bash
#!/data/data/com.termux/files/usr/bin/bash

HAJIMI_PATH=/data/data/com.termux/files/home/hajimi
export GEMINI_API_KEYS="key1,key2,key3"

termux-wake-lock
cd $HAJIMI_PATH
uvicorn app.main:app --reload --host 127.0.0.1 --port 7860
```

### 3. 添加桌面小部件
- 在桌面添加 Termux Widget 快捷方式
- 点击刚才创建的脚本，即可一键启动 Hajimi 服务

---

## 九、访问前端页面

启动服务后，在浏览器中访问以下地址查看前端界面：

```
http://127.0.0.1:7860
```

> **注意**：此地址只能在当前设备本地访问，如需远程访问请进行端口转发或内网穿透设置。