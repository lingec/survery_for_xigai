FROM python:3.12-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码
COPY . .

# 预创建数据目录（确保可写）
RUN mkdir -p /app/data

EXPOSE 5000

# 启动命令（直接用 Flask 自带服务器）
CMD python app.py
