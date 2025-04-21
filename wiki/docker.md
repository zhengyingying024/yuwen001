# 使用 Docker 部署 Gemini 轮询魔改版教程 由 **北极星星** 编写

## 一、准备工作

### 1.1 下载项目

从 releases 下载最新版本，并解压到任意目录。

### 1.2 配置环境变量

在项目根目录下创建 `.env` 文件，配置必要环境变量，示例如下：

```
GEMINI_API_KEYS=key1,key2,key3
PASSWORD=your_password
TZ=Asia/Shanghai
```

按需修改上述值，注意⚠️key必须使用英文逗号间隔。

## 二、构建并运行 Docker 容器

### 2.1 构建镜像

在项目根目录打开终端，执行命令构建 Docker 镜像：

```bash
cd 项目文件夹完整路径（例如：cd /volume3/docker/hagemi）
docker build -t hajimi-app .
```

此过程可能需一些时间，取决于网络和系统性能。

### 2.2 运行容器

镜像构建完成后，执行命令启动 Docker 容器，如端口被占用需修改左侧端口号：

```bash
docker run -d -p 7860:7860 --env-file .env --name hajimi-app hajimi-app
```

## 三、验证部署

### 3.1 检查容器状态

打开 docker 查看 hajimi-app 容器运行状态，确认正常启动。

### 3.2 访问应用

打开浏览器，访问 http://localhost:7860，若看到应用界面，则部署成功。

API 地址：http://localhost:7860/v1  
key：PASSWORD=your_password

## 四、容器更新

### 4.1 更新脚本

将下面 gemini_docker_update.sh 脚本按需修改保存为一个 .sh 文件：

```bash
# 停止容器
docker stop hajimi-app
# 删除容器
docker rm hajimi-app
# 进入项目所在目录
cd /volume3/docker/hagemi
# 使用以下命令拉取最新代码
git pull origin main
# 构建新的 Docker 镜像
docker build -t hajimi-app .
# 运行新容器
docker run -d -p 7860:7860 --env-file .env hajimi-app
# 查看容器状态
docker ps -a | grep hajimi-app    
```

### 4.2 脚本存放位置

把 gemini_docker_update.sh 脚本存放在项目根目录，例如项目文件路径是 /volume3/docker/hagemi，便将脚本存放在 /volume3/docker/hagemi。

### 4.3 执行更新

进入终端输入命令，执行更新脚本：

```bash
cd /volume3/docker/hagemi
./gemini_docker_update.sh
```

通过以上步骤，即可使用 Docker 成功部署 Gemini 轮询魔改版应用。
