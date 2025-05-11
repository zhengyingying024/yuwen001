FROM ghcr.io/astral-sh/uv:alpine

WORKDIR /app

COPY app app
COPY pyproject.toml version.txt .

RUN apk add --no-cache python3 && uv sync

EXPOSE 7860

CMD ["uv", "run", "--no-sync", "--no-cache", "--", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
