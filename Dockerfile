FROM python:3.12-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码
COPY . .

# 预创建数据目录（确保可写）
RUN mkdir -p /app/data

# 启动命令
CMD python app.py
