# 基础镜像
FROM python:3.9-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖：mktorrent, mediainfo 和 ffmpeg
# 这一步会下载比较多的包，请耐心等待
RUN apt-get update && \
    apt-get install -y mktorrent mediainfo ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
RUN pip install --no-cache-dir flask

# 复制当前目录代码
COPY . .

# 暴露端口
EXPOSE 5000

# 启动命令
CMD ["python", "app.py"]