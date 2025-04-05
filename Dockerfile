FROM python:3.11-slim

WORKDIR /app

# 安装 unzip 工具
RUN apt-get update && apt-get install -y unzip && rm -rf /var/lib/apt/lists/*

COPY app.zip .
COPY requirements.txt .
COPY version.txt .
RUN mkdir -p app
# 解压 app.zip 文件
RUN unzip app.zip -d app && rm app.zip

RUN pip install --no-cache-dir -r requirements.txt

# 环境变量 (在 Hugging Face Spaces 中设置)
# ENV GEMINI_API_KEYS=your_key_1,your_key_2,your_key_3

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]