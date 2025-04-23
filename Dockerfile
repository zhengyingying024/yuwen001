# 使用官方 Python 3.11 瘦身镜像作为基础镜像
FROM python:3.11-slim

# 设置工作目录为 /app
WORKDIR /app

# 复制 requirements.txt 并安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制当前目录下的所有文件到工作目录
COPY . .

# 暴露端口 7860
EXPOSE 7860

# 使用 Uvicorn 启动应用
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]