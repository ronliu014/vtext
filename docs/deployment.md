# vtext 部署指南

---

## 1. 本地开发

```sh
# 完整安装（含 server 和开发依赖）
pip install -e ".[full,dev]"

# 启动 server
vtext-server --model tiny

# 另一个终端使用客户端
vtext video.mp4
```

---

## 2. Docker 部署

### Dockerfile.server

```dockerfile
FROM python:3.11-slim

# 安装系统依赖（仅 whisper.cpp 编译需要）
RUN apt-get update && apt-get install -y \
    git build-essential cmake && \
    rm -rf /var/lib/apt/lists/*

# 编译 whisper.cpp
RUN git clone https://github.com/ggerganov/whisper.cpp.git /opt/whisper.cpp && \
    cd /opt/whisper.cpp && make

# 安装 vtext server
COPY . /app
WORKDIR /app
RUN pip install --no-cache-dir ".[server]"

ENV WHISPER_CPP_BIN=/opt/whisper.cpp/main

# 预下载默认模型
RUN python -m vtext_server.models download base

EXPOSE 8000
CMD ["vtext-server", "--host", "0.0.0.0", "--port", "8000"]
```

### docker-compose.yml

```yaml
version: '3.8'

services:
  vtext-server:
    build:
      context: .
      dockerfile: Dockerfile.server
    ports:
      - "8000:8000"
    volumes:
      - ./models:/root/.cache/vtext/models
    environment:
      - WHISPER_CPP_MODEL=/root/.cache/vtext/models/ggml-base.bin
    restart: unless-stopped
```

```sh
docker compose up -d
```

---

## 3. Systemd 服务（Linux）

```ini
# /etc/systemd/system/vtext-server.service
[Unit]
Description=vtext Transcription Server
After=network.target

[Service]
Type=simple
User=vtext
WorkingDirectory=/opt/vtext
ExecStart=/usr/local/bin/vtext-server --host 0.0.0.0 --port 8000 --model base
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```sh
sudo systemctl daemon-reload
sudo systemctl enable vtext-server
sudo systemctl start vtext-server
```

---

## 4. 配置文件参考

### 服务端（~/.config/vtext/server.toml）

```toml
[server]
host = "127.0.0.1"
port = 8000
workers = 4          # 默认等于 CPU 核心数
queue_max = 16       # 队列上限，超出返回 429

[whisper]
binary = "/opt/whisper.cpp/main"
model = "base"
threads = 4

[models]
cache_dir = "~/.cache/vtext/models"

[logging]
level = "INFO"
file = "/var/log/vtext/server.log"
```

### 客户端（~/.config/vtext/client.toml）

```toml
[client]
server_url = "http://127.0.0.1:8000"
timeout = 300
retry_max = 3        # 连接失败/超时最多重试次数

[output]
default_format = "txt"
default_dir = "./transcripts"
```

---

## 5. 典型使用场景

### 场景 1：单机本地使用

```sh
# 终端 1
vtext-server --model tiny

# 终端 2
vtext video.mp4 -o output.txt
```

### 场景 2：远程服务器

```sh
# 服务器端
vtext-server --host 0.0.0.0 --model large-v3

# 本地客户端
export VTEXT_SERVER_URL=http://192.168.1.100:8000
vtext video.mp4
vtext folder/ -j 4 -f srt   # 批量处理
```

### 场景 3：团队共享 server

```sh
# 管理员在公司服务器部署
docker compose up -d

# 团队成员配置
export VTEXT_SERVER_URL=http://team-server.local:8000
vtext my-meeting.mp4
```

---

## 6. 安全配置

### API Key 认证（可选）

```python
# server 启动时设置
vtext-server --api-key your-secret-key

# 客户端携带
vtext video.mp4 --api-key your-secret-key
# 或环境变量
export VTEXT_API_KEY=your-secret-key
```

### 速率限制

server 内置基于 IP 的速率限制，可在 `server.toml` 中配置：

```toml
[rate_limit]
enabled = true
requests_per_minute = 10
```

### 文件安全

- 文件大小上限：500MB（WAV，压缩前）
- 文件类型：仅接受 WAV 和 zstd 压缩包
- 文件名清理：防止路径遍历攻击
