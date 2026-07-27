FROM python:3.11-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制所有代码
COPY . .

# Hugging Face Spaces 默认端口
ENV PORT=7860

# 启动 FastAPI 服务
CMD uvicorn api:app --host 0.0.0.0 --port $PORT
