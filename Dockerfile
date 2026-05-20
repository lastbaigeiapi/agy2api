# 使用轻量级 Python 镜像
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 安装必要的系统工具
RUN apt-get update && apt-get install -y \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 复制网关代码和授权脚本
COPY main.py .
COPY auth /usr/local/bin/auth
RUN chmod +x /usr/local/bin/auth

# 暴露网关端口
EXPOSE 8789

# 启动命令
CMD ["python", "main.py"]
